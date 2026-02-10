"""
Alfred V3 - Ingredient Lookup Layer.

Provides multi-tier ingredient matching:
1. Exact match on name
2. Exact match on aliases
3. Fuzzy match using pg_trgm (trigram similarity)
4. Semantic match using pgvector embeddings

Threshold strategy varies by operation:
- Write operations (inventory, shopping_list): High threshold (0.85+) for auto-linking
- Read operations (search expansion): Lower threshold (0.6+) for broader matches
"""

import logging
from dataclasses import dataclass
from typing import Literal

from openai import OpenAI

from alfred_kitchen.config import settings
from alfred_kitchen.db.client import get_client

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Threshold configuration by operation type
# Tuned based on real data:
# - "chiken" → "chicken" = 0.70
# - "letuce" → "lettuce" = 0.66
# - "chicken thighs" → "chicken breasts" = < 0.40 (safe separation)
THRESHOLDS = {
    "write": 0.60,  # Catches common typos while avoiding false positives
    "read": 0.40,   # Cast wider net for search expansion
}

# Embedding model (same as generate_embeddings.py)
EMBEDDING_MODEL = "text-embedding-3-small"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class IngredientMatch:
    """Result of an ingredient lookup."""
    id: str
    name: str
    category: str | None
    match_type: Literal["exact", "fuzzy", "semantic"]
    confidence: float  # 0.0 to 1.0
    
    def __repr__(self) -> str:
        return f"IngredientMatch({self.name}, type={self.match_type}, conf={self.confidence:.2f})"


# =============================================================================
# Embedding Generation
# =============================================================================

_openai_client: OpenAI | None = None

def _get_openai_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for a text string."""
    client = _get_openai_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


# =============================================================================
# Lookup Functions
# =============================================================================

async def lookup_ingredient_exact(name: str) -> IngredientMatch | None:
    """
    Try exact match on ingredient name or aliases.
    
    Uses the match_ingredient_exact() Postgres function.
    Falls back to Python-based matching if function not available.
    """
    client = get_client()
    normalized = name.lower().strip()
    
    try:
        # Try using the Postgres function
        result = client.rpc("match_ingredient_exact", {"query": normalized}).execute()
        if result.data:
            row = result.data[0]
            return IngredientMatch(
                id=row["id"],
                name=row["name"],
                category=row.get("category"),
                match_type="exact",
                confidence=1.0,
            )
    except Exception as e:
        # Function may not exist yet - fall back to direct query
        logger.debug(f"match_ingredient_exact RPC failed, using fallback: {e}")
        
        # Fallback: direct query
        result = client.table("ingredients").select("id, name, category, aliases").execute()
        for row in result.data:
            # Check name
            if row["name"].lower() == normalized:
                return IngredientMatch(
                    id=row["id"],
                    name=row["name"],
                    category=row.get("category"),
                    match_type="exact",
                    confidence=1.0,
                )
            # Check aliases
            aliases = row.get("aliases") or []
            if normalized in [a.lower() for a in aliases]:
                return IngredientMatch(
                    id=row["id"],
                    name=row["name"],
                    category=row.get("category"),
                    match_type="exact",
                    confidence=1.0,
                )
    
    return None


async def lookup_ingredient_fuzzy(
    name: str, 
    threshold: float = 0.6
) -> IngredientMatch | None:
    """
    Try fuzzy match using trigram similarity.
    
    Uses the match_ingredient_fuzzy() Postgres function.
    Falls back to Python-based similarity if function not available.
    """
    client = get_client()
    normalized = name.lower().strip()
    
    try:
        # Try using the Postgres function
        result = client.rpc(
            "match_ingredient_fuzzy",
            {"query": normalized, "threshold": threshold, "limit_n": 1}
        ).execute()
        
        if result.data:
            row = result.data[0]
            return IngredientMatch(
                id=row["id"],
                name=row["name"],
                category=row.get("category"),
                match_type="fuzzy",
                confidence=row["similarity"],
            )
    except Exception as e:
        # Function may not exist yet - skip fuzzy matching
        logger.debug(f"match_ingredient_fuzzy RPC failed: {e}")
    
    return None


async def lookup_ingredient_semantic(
    name: str,
    max_distance: float = 0.7  # Higher distance = more lenient (1 - 0.7 = 0.3 confidence min)
) -> IngredientMatch | None:
    """
    Try semantic match using vector similarity.
    
    Generates embedding for the query and searches against ingredient embeddings.
    """
    client = get_client()
    
    try:
        # Generate embedding for the query
        query_embedding = generate_embedding(name)
        
        # Try using the Postgres function
        result = client.rpc(
            "match_ingredient_semantic",
            {
                "query_embedding": query_embedding,
                "limit_n": 1,
                "max_distance": max_distance
            }
        ).execute()
        
        if result.data:
            row = result.data[0]
            # Convert distance to confidence (lower distance = higher confidence)
            confidence = 1.0 - row["distance"]
            return IngredientMatch(
                id=row["id"],
                name=row["name"],
                category=row.get("category"),
                match_type="semantic",
                confidence=confidence,
            )
    except Exception as e:
        logger.debug(f"Semantic lookup failed: {e}")
    
    return None


async def lookup_ingredient(
    name: str,
    operation: Literal["read", "write"] = "write",
    use_semantic: bool = True,
    limit: int = 1,
) -> IngredientMatch | list[IngredientMatch] | None:
    """
    Look up an ingredient.
    
    Args:
        name: Ingredient name to search for
        operation: "write" or "read" (affects threshold)
        use_semantic: Whether to use semantic fallback
        limit: Number of matches to return (1 = single best, >1 = top N candidates)
    
    Returns:
        If limit=1: Single IngredientMatch or None
        If limit>1: List of IngredientMatch (may be empty)
    
    Algorithm:
    1. EXACT STRING MATCH - name/alias exact match
    2. FUZZY STRING (>0.85) - high confidence whole-string match  
    3. WORD-BY-WORD - extract words, score by match count + similarity sum
    4. SEMANTIC - embedding-based fallback
    """
    if not name or not name.strip():
        return None if limit == 1 else []
    
    # For multi-match (limit > 1), collect all candidates
    if limit > 1:
        return await _lookup_ingredient_multi(name, limit, use_semantic)
    
    # Single match (original behavior)
    # 1. EXACT STRING MATCH
    match = await lookup_ingredient_exact(name)
    if match:
        return match
    
    # 2. FUZZY STRING (>0.85)
    match = await lookup_ingredient_fuzzy(name, threshold=0.85)
    if match and match.confidence >= 0.85:
        return match
    
    # 3. WORD-BY-WORD
    words = _extract_ingredient_words(name)
    if words:
        match = await _word_by_word_match(words)
        if match:
            return match
    
    # 4. SEMANTIC (fallback)
    if use_semantic:
        match = await lookup_ingredient_semantic(name)
        if match:
            return match
    
    return None


async def _lookup_ingredient_multi(
    name: str, 
    limit: int = 10,
    use_semantic: bool = True,
) -> list[IngredientMatch]:
    """
    Return multiple matching ingredients for a search term.
    
    Used for "like" searches where we want all chicken variants, etc.
    """
    from difflib import SequenceMatcher
    
    client = get_client()
    words = _extract_ingredient_words(name)
    input_words = {w.lower().rstrip('s') for w in words if len(w) >= 2}
    
    if not input_words:
        return []
    
    # Get candidates: any ingredient containing any input word
    candidates: list[dict] = []
    seen_ids: set[str] = set()
    
    for word in input_words:
        try:
            result = client.table("ingredients").select("id, name, category").ilike("name", f"%{word}%").limit(50).execute()
            for row in result.data:
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    candidates.append(row)
        except Exception:
            pass
    
    if not candidates:
        return []
    
    # Score each candidate
    scored: list[tuple[float, dict]] = []
    for cand in candidates:
        cand_name = cand["name"].lower()
        cand_words = set(cand_name.replace("-", " ").split())
        
        # Count how many input words appear in candidate
        match_count = sum(1 for w in input_words if any(w in cw or cw.startswith(w) for cw in cand_words))
        
        # Also get string similarity
        similarity = SequenceMatcher(None, name.lower(), cand_name).ratio()
        
        # Score: prioritize match count, then similarity
        score = match_count + similarity
        scored.append((score, cand))
    
    # Sort by score descending, then by name length (prefer shorter/canonical names)
    scored.sort(key=lambda x: (-x[0], len(x[1]["name"])))
    
    # Return top N as IngredientMatch objects
    results: list[IngredientMatch] = []
    for score, cand in scored[:limit]:
        if score > 0:  # Only include if there's some match
            results.append(IngredientMatch(
                id=cand["id"],
                name=cand["name"],
                category=cand.get("category"),
                match_type="multi",
                confidence=min(1.0, score / 2),  # Normalize score to 0-1
            ))
    
    return results


async def _word_by_word_match(words: list[str]) -> IngredientMatch | None:
    """
    Word-by-word matching.
    
    INPUT WORDS vs INGREDIENT NAME WORDS = SCORE
    
    Example: "fresh thai basil" → input words: ["thai", "basil"]
    
      "Thai basil" name words: ["thai", "basil"]
        → "thai" in name? YES (1.0)
        → "basil" in name? YES (1.0)
        → score = 2.0, count = 2
    
      "basil" name words: ["basil"]
        → "thai" in name? NO
        → "basil" in name? YES (1.0)
        → score = 1.0, count = 1
    
      Winner: "Thai basil" (count=2 > count=1)
    """
    if not words:
        return None
    
    input_words = {w.lower().rstrip('s') for w in words if len(w) >= 3}
    if not input_words:
        return None
    
    client = get_client()
    
    # Get candidate ingredients: any ingredient containing any input word
    candidates: list[dict] = []
    seen_ids: set[str] = set()
    
    for word in input_words:
        try:
            result = client.table("ingredients").select(
                "id, name, category"
            ).ilike("name", f"%{word}%").limit(20).execute()
            
            for row in result.data or []:
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    candidates.append(row)
        except Exception as e:
            logger.debug(f"Search for '{word}' failed: {e}")
    
    if not candidates:
        return None
    
    # Score each candidate: count matching words
    scored: list[tuple[int, int, dict]] = []  # (count, name_length, data)
    
    for cand in candidates:
        name_words = {w.lower().rstrip('s') for w in cand["name"].split()}
        
        # Count how many input words appear in ingredient name words
        matches = input_words & name_words
        count = len(matches)
        
        if count > 0:
            # Use negative name length so shorter names sort first
            scored.append((count, -len(cand["name"]), cand))
    
    if not scored:
        return None
    
    # Sort: count DESC, then shorter name (higher -len) first
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    
    best_count, _, best_data = scored[0]
    return IngredientMatch(
        id=best_data["id"],
        name=best_data["name"],
        category=best_data["category"],
        match_type="exact" if best_count == len(input_words) else "fuzzy",
        confidence=best_count / len(input_words),
    )


def _extract_ingredient_words(name: str) -> list[str]:
    """
    Extract meaningful words from an ingredient name.
    
    Filters out:
    - Brand indicators (trader, joe's, kirkland, etc.)
    - State/prep words (frozen, fresh, organic, diced, etc.)
    - Common filler words (the, a, of, with, etc.)
    
    Returns words most likely to be the actual ingredient.
    """
    # Common words to skip (not the ingredient itself)
    SKIP_WORDS = {
        # Filler words
        "a", "an", "the", "of", "with", "and", "or", "for",
        # Brand indicators
        "trader", "joe's", "joes", "kirkland", "whole", "foods", "365",
        # State/preparation (these should go in notes)
        "frozen", "fresh", "organic", "natural", "raw", "cooked",
        "diced", "minced", "chopped", "sliced", "cubed", "shredded",
        "boneless", "skinless", "bone-in", "skin-on",
        "large", "medium", "small", "extra",
        # Quality indicators
        "premium", "select", "choice", "grade",
    }
    
    # Split on spaces and common separators
    import re
    words = re.split(r'[\s,\-/]+', name.lower())
    
    # Filter and return meaningful words
    return [w for w in words if w and w not in SKIP_WORDS and len(w) >= 2]


async def lookup_ingredients_batch(
    names: list[str],
    operation: Literal["read", "write"] = "write",
    use_semantic: bool = True,
) -> dict[str, IngredientMatch | None]:
    """
    Batch lookup for multiple ingredient names.
    
    Args:
        names: List of ingredient names to look up
        operation: "write" or "read" (affects threshold)
        use_semantic: Whether to use semantic fallback
        
    Returns:
        Dict mapping each input name to its IngredientMatch (or None)
    """
    results = {}
    for name in names:
        results[name] = await lookup_ingredient(name, operation, use_semantic)
    return results


# =============================================================================
# CRUD Integration Helpers
# =============================================================================

async def enrich_with_ingredient_id(
    data: dict,
    operation: Literal["read", "write"] = "write",
    use_resolver: bool = False,
) -> dict:
    """
    Enrich a single record with ingredient_id if it has a 'name' field.

    Used by db_create to auto-link inventory/shopping_list items to ingredients.
    Keeps the original 'name' field as-is (per user preference).

    Args:
        data: Record dict with optional 'name' field
        operation: "write" for creates, "read" for searches
        use_resolver: Whether to use full resolver (parses qty/unit/modifiers)

    Returns:
        Enriched data dict with ingredient_id if match found
    """
    name = data.get("name")
    if not name:
        return data

    # Skip if already has ingredient_id
    if data.get("ingredient_id"):
        return data

    if use_resolver:
        # Use the full resolver for complex inputs (extracts modifiers, qty, unit)
        from alfred_kitchen.domain.tools.ingredient_resolver import resolve_and_enrich
        return await resolve_and_enrich(data, use_resolver=True)

    # Simple lookup (no parsing)
    match = await lookup_ingredient(name, operation=operation, use_semantic=False)

    if match:
        enriched = {**data, "ingredient_id": match.id}
        # Also copy category for grouping/filtering (if available)
        if match.category:
            enriched["category"] = match.category
        logger.info(f"Linked '{name}' to ingredient '{match.name}' ({match.match_type})")
        return enriched

    return data


async def enrich_batch_with_ingredient_ids(
    records: list[dict],
    operation: Literal["read", "write"] = "write",
    use_resolver: bool = False,
) -> list[dict]:
    """
    Enrich multiple records with ingredient_ids.

    Args:
        records: List of record dicts
        operation: "write" for creates, "read" for searches
        use_resolver: Whether to use full resolver (parses qty/unit/modifiers)

    Returns:
        List of enriched records
    """
    return [await enrich_with_ingredient_id(r, operation, use_resolver) for r in records]


async def expand_search_with_similar(
    name: str,
    threshold: float = 0.4,
) -> list[str]:
    """
    Expand a search term to include similar ingredient names.
    
    Used by db_read to broaden searches.
    
    Args:
        name: Search term
        threshold: Similarity threshold (lower = more results)
        
    Returns:
        List of ingredient names to search for (includes original)
    """
    client = get_client()
    results = [name]  # Always include original
    
    try:
        # Get fuzzy matches
        result = client.rpc(
            "match_ingredient_fuzzy",
            {"query": name.lower(), "threshold": threshold, "limit_n": 5}
        ).execute()
        
        if result.data:
            for row in result.data:
                if row["name"] not in results:
                    results.append(row["name"])
                    
    except Exception as e:
        logger.debug(f"expand_search_with_similar failed: {e}")
    
    return results

