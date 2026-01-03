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

from alfred.config import settings
from alfred.db.client import get_client

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
) -> IngredientMatch | None:
    """
    Look up an ingredient using chained matching strategies.
    
    Chain: exact → fuzzy → semantic
    
    Args:
        name: Ingredient name to look up
        operation: "write" uses high threshold (0.85), "read" uses lower (0.6)
        use_semantic: Whether to fall back to semantic matching
        
    Returns:
        IngredientMatch if found, None otherwise
    """
    if not name or not name.strip():
        return None
    
    threshold = THRESHOLDS.get(operation, 0.6)
    
    # 1. Try exact match (always)
    match = await lookup_ingredient_exact(name)
    if match:
        logger.debug(f"Exact match: '{name}' -> {match.name}")
        return match
    
    # 2. Try fuzzy match with operation-specific threshold
    match = await lookup_ingredient_fuzzy(name, threshold=threshold)
    if match and match.confidence >= threshold:
        logger.debug(f"Fuzzy match: '{name}' -> {match.name} (conf={match.confidence:.2f})")
        return match
    
    # 3. Try semantic match (if enabled and no fuzzy match)
    if use_semantic:
        match = await lookup_ingredient_semantic(name)
        if match:
            logger.debug(f"Semantic match: '{name}' -> {match.name} (conf={match.confidence:.2f})")
            return match
    
    logger.debug(f"No match found for: '{name}'")
    return None


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
) -> dict:
    """
    Enrich a single record with ingredient_id if it has a 'name' field.
    
    Used by db_create to auto-link inventory/shopping_list items to ingredients.
    Keeps the original 'name' field as-is (per user preference).
    
    Args:
        data: Record dict with optional 'name' field
        operation: "write" for creates, "read" for searches
        
    Returns:
        Enriched data dict with ingredient_id if match found
    """
    name = data.get("name")
    if not name:
        return data
    
    # Skip if already has ingredient_id
    if data.get("ingredient_id"):
        return data
    
    match = await lookup_ingredient(name, operation=operation, use_semantic=False)
    
    if match:
        enriched = {**data, "ingredient_id": match.id}
        logger.info(f"Linked '{name}' to ingredient '{match.name}' ({match.match_type})")
        return enriched
    
    return data


async def enrich_batch_with_ingredient_ids(
    records: list[dict],
    operation: Literal["read", "write"] = "write",
) -> list[dict]:
    """
    Enrich multiple records with ingredient_ids.
    
    Args:
        records: List of record dicts
        operation: "write" for creates, "read" for searches
        
    Returns:
        List of enriched records
    """
    return [await enrich_with_ingredient_id(r, operation) for r in records]


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

