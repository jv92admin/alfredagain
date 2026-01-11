# Alfred V6: Semantic Search & Observability

**Status:** Planning  
**Priority:** High  
**Last Updated:** 2026-01-10

---

## Overview

V6 focuses on two foundational improvements:

1. **Semantic Recipe Search** — Enable natural language recipe discovery ("something light for summer") instead of keyword-only matching
2. **Prompt Observability** — Token counting, success tracking, and basic metrics for prompt performance

These improvements build on V5's context management without requiring architectural changes.

---

## Table of Contents

1. [Semantic Recipe Search](#1-semantic-recipe-search)
2. [Prompt Observability](#2-prompt-observability)
3. [Implementation Plan](#3-implementation-plan)
4. [Future Work (Deferred)](#4-future-work-deferred)

---

## 1. Semantic Recipe Search

### Problem

Current recipe search uses keyword matching:

```json
{"field": "name", "op": "ilike", "value": "%chicken%"}
```

This fails for:
- Conceptual queries: "something healthy", "comfort food", "quick weeknight dinner"
- Ingredient-based discovery: "what can I make with what's expiring?"
- Mood-based requests: "I'm feeling adventurous", "something warming"

### Solution

Add vector embeddings to recipes and enable semantic similarity search.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      RECIPE SEARCH FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   User: "something light for summer"                            │
│                            │                                     │
│                            ▼                                     │
│   ┌────────────────────────────────────────┐                    │
│   │         QUERY CLASSIFICATION           │                    │
│   │  Is this semantic or keyword search?   │                    │
│   └────────────────────────────────────────┘                    │
│              │                    │                              │
│         semantic              keyword                            │
│              │                    │                              │
│              ▼                    ▼                              │
│   ┌──────────────────┐   ┌──────────────────┐                   │
│   │  VECTOR SEARCH   │   │  DB SEARCH       │                   │
│   │  pgvector        │   │  ilike filters   │                   │
│   └──────────────────┘   └──────────────────┘                   │
│              │                    │                              │
│              └────────┬───────────┘                              │
│                       ▼                                          │
│              Ranked Results                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Database Changes

#### Migration: `020_recipe_embeddings.sql`

```sql
-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to recipes
ALTER TABLE recipes 
ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create index for fast similarity search
CREATE INDEX IF NOT EXISTS recipes_embedding_idx 
ON recipes USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Add embedding column to recipe descriptions (optional, for richer search)
-- We embed: name + description + cuisine + tags concatenated

-- Function to search recipes by similarity
CREATE OR REPLACE FUNCTION search_recipes_semantic(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    p_user_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    name text,
    description text,
    cuisine text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        r.id,
        r.name,
        r.description,
        r.cuisine,
        1 - (r.embedding <=> query_embedding) as similarity
    FROM recipes r
    WHERE 
        r.embedding IS NOT NULL
        AND (p_user_id IS NULL OR r.user_id = p_user_id)
        AND 1 - (r.embedding <=> query_embedding) > match_threshold
    ORDER BY r.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

### Code Changes

#### `src/alfred/tools/semantic_search.py` (new file)

```python
"""
Semantic search for recipes using embeddings.
"""

import logging
from typing import Any

from openai import AsyncOpenAI

from alfred.db.client import get_client

logger = logging.getLogger(__name__)

# OpenAI client for embeddings
_openai_client: AsyncOpenAI | None = None

def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI()
    return _openai_client


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


async def get_embedding(text: str) -> list[float]:
    """Get embedding for a text string."""
    client = get_openai_client()
    
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    
    return response.data[0].embedding


def build_recipe_text_for_embedding(recipe: dict) -> str:
    """
    Build the text representation of a recipe for embedding.
    
    Combines name, description, cuisine, and tags into a searchable string.
    """
    parts = []
    
    if recipe.get("name"):
        parts.append(recipe["name"])
    
    if recipe.get("description"):
        parts.append(recipe["description"])
    
    if recipe.get("cuisine"):
        parts.append(f"Cuisine: {recipe['cuisine']}")
    
    if recipe.get("tags"):
        tags = recipe["tags"]
        if isinstance(tags, list):
            parts.append(f"Tags: {', '.join(tags)}")
    
    # Include key characteristics
    if recipe.get("difficulty"):
        parts.append(f"Difficulty: {recipe['difficulty']}")
    
    total_time = (recipe.get("prep_time_minutes") or 0) + (recipe.get("cook_time_minutes") or 0)
    if total_time > 0:
        if total_time <= 30:
            parts.append("Quick recipe")
        elif total_time <= 60:
            parts.append("Medium time recipe")
        else:
            parts.append("Long recipe")
    
    return " | ".join(parts)


async def embed_recipe(recipe_id: str, recipe: dict) -> bool:
    """
    Generate and store embedding for a recipe.
    
    Called after recipe creation/update.
    """
    try:
        text = build_recipe_text_for_embedding(recipe)
        embedding = await get_embedding(text)
        
        client = get_client()
        client.table("recipes").update({
            "embedding": embedding
        }).eq("id", recipe_id).execute()
        
        logger.info(f"Embedded recipe {recipe_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to embed recipe {recipe_id}: {e}")
        return False


async def search_recipes_semantic(
    query: str,
    user_id: str | None = None,
    limit: int = 10,
    threshold: float = 0.7,
) -> list[dict]:
    """
    Search recipes using semantic similarity.
    
    Args:
        query: Natural language search query
        user_id: Filter to user's recipes (optional)
        limit: Max results to return
        threshold: Minimum similarity score (0-1)
    
    Returns:
        List of matching recipes with similarity scores
    """
    try:
        # Get query embedding
        query_embedding = await get_embedding(query)
        
        # Call Supabase RPC function
        client = get_client()
        
        result = client.rpc(
            "search_recipes_semantic",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit,
                "p_user_id": user_id,
            }
        ).execute()
        
        return result.data or []
        
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return []


def is_semantic_query(query: str) -> bool:
    """
    Determine if a query should use semantic search vs keyword search.
    
    Semantic queries are conceptual/mood-based.
    Keyword queries are specific names/ingredients.
    """
    query_lower = query.lower()
    
    # Semantic indicators
    semantic_patterns = [
        "something", "anything", "feeling", "mood", "like",
        "healthy", "light", "heavy", "comfort", "quick", "easy",
        "fancy", "impressive", "simple", "adventurous", "warming",
        "cooling", "summer", "winter", "fall", "spring",
        "weeknight", "weekend", "special", "everyday",
        "similar to", "kind of", "type of", "style",
    ]
    
    # If query contains semantic indicators, use semantic search
    for pattern in semantic_patterns:
        if pattern in query_lower:
            return True
    
    # If query is very short and generic, use semantic
    if len(query.split()) <= 2 and not any(c.isupper() for c in query):
        # Short generic queries like "pasta" could be semantic
        # But "Butter Chicken" (capitalized) is a specific recipe name
        return True
    
    return False
```

#### Update `src/alfred/tools/crud.py`

Add semantic search integration to `db_read`:

```python
# In execute_crud function, for recipes table reads:

async def execute_crud(
    tool: str,
    params: dict,
    user_id: str,
    registry: SessionIdRegistry,
) -> Any:
    """Execute CRUD operation with ID translation."""
    
    table = params.get("table")
    
    # Special handling for semantic recipe search
    if tool == "db_read" and table == "recipes":
        # Check if this looks like a semantic query
        semantic_query = params.get("semantic_query")
        
        if semantic_query:
            from alfred.tools.semantic_search import search_recipes_semantic
            
            results = await search_recipes_semantic(
                query=semantic_query,
                user_id=user_id,
                limit=params.get("limit", 10),
            )
            
            # Translate output (assign refs)
            return registry.translate_read_output(results, table)
    
    # ... rest of existing CRUD logic
```

#### Update recipe create to embed

In `crud.py` after successful `db_create` on recipes:

```python
# After recipe creation succeeds
if table == "recipes" and tool == "db_create":
    from alfred.tools.semantic_search import embed_recipe
    
    # Embed asynchronously (don't block response)
    for record in result:
        asyncio.create_task(embed_recipe(record["id"], record))
```

### Prompt Updates

#### Update `prompts/act/read.md`

Add semantic search guidance:

```markdown
## Semantic Recipe Search

For conceptual queries ("something healthy", "comfort food", "quick dinner"):

```json
{
  "tool": "db_read",
  "params": {
    "table": "recipes",
    "semantic_query": "light summer dinner that's easy to make",
    "limit": 5
  }
}
```

Use `semantic_query` when the user asks for:
- Mood/feeling-based: "I'm feeling adventurous"
- Conceptual: "something healthy", "comfort food"  
- Time-based: "quick weeknight dinner"
- Seasonal: "summer recipes", "warming winter dish"

Use regular `filters` when the user asks for:
- Specific recipe names: "Butter Chicken"
- Exact ingredients: "recipes with salmon"
- Specific cuisines: "Italian recipes"
```

### Backfill Script

#### `scripts/backfill_recipe_embeddings.py`

```python
"""
Backfill embeddings for existing recipes.

Usage: python scripts/backfill_recipe_embeddings.py
"""

import asyncio
import logging
from alfred.db.client import get_client
from alfred.tools.semantic_search import embed_recipe, build_recipe_text_for_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill_embeddings():
    """Backfill embeddings for all recipes without them."""
    client = get_client()
    
    # Get recipes without embeddings
    result = client.table("recipes").select("*").is_("embedding", "null").execute()
    recipes = result.data or []
    
    logger.info(f"Found {len(recipes)} recipes without embeddings")
    
    success = 0
    failed = 0
    
    for recipe in recipes:
        try:
            if await embed_recipe(recipe["id"], recipe):
                success += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Failed to embed {recipe['id']}: {e}")
            failed += 1
        
        # Rate limiting
        await asyncio.sleep(0.1)
    
    logger.info(f"Backfill complete: {success} success, {failed} failed")


if __name__ == "__main__":
    asyncio.run(backfill_embeddings())
```

---

## 2. Prompt Observability

### Problem

Currently we log prompts to files but don't track:
- Token usage per section
- Success/failure rates by prompt pattern
- Latency by node/complexity
- Prompt changes over time

### Solution

Add lightweight observability layer with token counting and structured metrics.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   LLM Call                                                       │
│       │                                                          │
│       ▼                                                          │
│   ┌────────────────────────────────────────┐                    │
│   │         PROMPT METRICS                  │                    │
│   │  - Token count (system, user, total)   │                    │
│   │  - Section breakdown                    │                    │
│   │  - Prompt hash (drift detection)        │                    │
│   └────────────────────────────────────────┘                    │
│                       │                                          │
│                       ▼                                          │
│   ┌────────────────────────────────────────┐                    │
│   │         RESPONSE METRICS                │                    │
│   │  - Latency                              │                    │
│   │  - Output tokens                        │                    │
│   │  - Success/failure                      │                    │
│   │  - Action type                          │                    │
│   └────────────────────────────────────────┘                    │
│                       │                                          │
│                       ▼                                          │
│              Structured Logs + Dashboard                         │
└─────────────────────────────────────────────────────────────────┘
```

### Code Changes

#### `src/alfred/observability/metrics.py` (new file)

```python
"""
Prompt and LLM call observability.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# Token encoder (lazy loaded)
_encoder: tiktoken.Encoding | None = None


def get_encoder() -> tiktoken.Encoding:
    """Get tiktoken encoder for token counting."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.encoding_for_model("gpt-4")
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens in a string."""
    if not text:
        return 0
    return len(get_encoder().encode(text))


def hash_prompt(text: str) -> str:
    """Generate short hash of prompt for drift detection."""
    return hashlib.md5(text.encode()).hexdigest()[:8]


@dataclass
class PromptMetrics:
    """Metrics for a single prompt."""
    node: str
    step_type: str | None = None
    subdomain: str | None = None
    
    # Token counts
    system_tokens: int = 0
    user_tokens: int = 0
    total_tokens: int = 0
    
    # Section breakdown (for user prompt)
    section_tokens: dict[str, int] = field(default_factory=dict)
    
    # Drift detection
    system_hash: str = ""
    user_hash: str = ""
    
    # Timing
    timestamp: str = ""
    
    def to_dict(self) -> dict:
        return {
            "node": self.node,
            "step_type": self.step_type,
            "subdomain": self.subdomain,
            "system_tokens": self.system_tokens,
            "user_tokens": self.user_tokens,
            "total_tokens": self.total_tokens,
            "section_tokens": self.section_tokens,
            "system_hash": self.system_hash,
            "user_hash": self.user_hash,
            "timestamp": self.timestamp,
        }


@dataclass
class ResponseMetrics:
    """Metrics for an LLM response."""
    node: str
    
    # Timing
    latency_ms: float = 0
    
    # Output
    output_tokens: int = 0
    
    # Outcome
    success: bool = True
    action_type: str | None = None  # tool_call, step_complete, etc.
    error: str | None = None
    
    # Model info
    model: str = ""
    complexity: str = ""
    
    def to_dict(self) -> dict:
        return {
            "node": self.node,
            "latency_ms": self.latency_ms,
            "output_tokens": self.output_tokens,
            "success": self.success,
            "action_type": self.action_type,
            "error": self.error,
            "model": self.model,
            "complexity": self.complexity,
        }


def analyze_prompt(
    system_prompt: str,
    user_prompt: str,
    node: str,
    step_type: str | None = None,
    subdomain: str | None = None,
) -> PromptMetrics:
    """
    Analyze a prompt and return metrics.
    
    Breaks down user_prompt by section headers (## Section).
    """
    metrics = PromptMetrics(
        node=node,
        step_type=step_type,
        subdomain=subdomain,
        system_tokens=count_tokens(system_prompt),
        user_tokens=count_tokens(user_prompt),
        system_hash=hash_prompt(system_prompt),
        user_hash=hash_prompt(user_prompt),
        timestamp=datetime.utcnow().isoformat(),
    )
    
    metrics.total_tokens = metrics.system_tokens + metrics.user_tokens
    
    # Break down user prompt by sections
    sections = _extract_sections(user_prompt)
    metrics.section_tokens = {
        name: count_tokens(content) 
        for name, content in sections.items()
    }
    
    return metrics


def _extract_sections(prompt: str) -> dict[str, str]:
    """Extract sections from a prompt by ## headers."""
    sections = {}
    current_section = "preamble"
    current_content = []
    
    for line in prompt.split("\n"):
        if line.startswith("## "):
            # Save previous section
            if current_content:
                sections[current_section] = "\n".join(current_content)
            # Start new section
            current_section = line[3:].strip()
            current_content = []
        else:
            current_content.append(line)
    
    # Save last section
    if current_content:
        sections[current_section] = "\n".join(current_content)
    
    return sections


class MetricsCollector:
    """
    Collects and aggregates metrics across calls.
    
    Thread-safe singleton for the session.
    """
    
    def __init__(self):
        self.prompt_metrics: list[PromptMetrics] = []
        self.response_metrics: list[ResponseMetrics] = []
        self._session_start = datetime.utcnow()
    
    def record_prompt(self, metrics: PromptMetrics) -> None:
        """Record prompt metrics."""
        self.prompt_metrics.append(metrics)
        
        # Log summary
        logger.info(
            f"Prompt [{metrics.node}]: "
            f"system={metrics.system_tokens}, "
            f"user={metrics.user_tokens}, "
            f"total={metrics.total_tokens}"
        )
    
    def record_response(self, metrics: ResponseMetrics) -> None:
        """Record response metrics."""
        self.response_metrics.append(metrics)
        
        # Log summary
        status = "✓" if metrics.success else "✗"
        logger.info(
            f"Response [{metrics.node}] {status}: "
            f"latency={metrics.latency_ms:.0f}ms, "
            f"action={metrics.action_type}"
        )
    
    def get_summary(self) -> dict:
        """Get aggregated metrics summary."""
        if not self.prompt_metrics:
            return {"calls": 0}
        
        total_input = sum(m.total_tokens for m in self.prompt_metrics)
        total_output = sum(m.output_tokens for m in self.response_metrics)
        total_latency = sum(m.latency_ms for m in self.response_metrics)
        success_count = sum(1 for m in self.response_metrics if m.success)
        
        # By node
        by_node = {}
        for m in self.prompt_metrics:
            if m.node not in by_node:
                by_node[m.node] = {"calls": 0, "tokens": 0}
            by_node[m.node]["calls"] += 1
            by_node[m.node]["tokens"] += m.total_tokens
        
        return {
            "calls": len(self.prompt_metrics),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_latency_ms": total_latency,
            "avg_latency_ms": total_latency / len(self.response_metrics) if self.response_metrics else 0,
            "success_rate": success_count / len(self.response_metrics) if self.response_metrics else 1.0,
            "by_node": by_node,
        }
    
    def get_section_breakdown(self) -> dict[str, dict]:
        """Get token breakdown by prompt section across all calls."""
        breakdown = {}
        
        for metrics in self.prompt_metrics:
            for section, tokens in metrics.section_tokens.items():
                if section not in breakdown:
                    breakdown[section] = {"total": 0, "count": 0}
                breakdown[section]["total"] += tokens
                breakdown[section]["count"] += 1
        
        # Calculate averages
        for section in breakdown:
            breakdown[section]["avg"] = (
                breakdown[section]["total"] / breakdown[section]["count"]
                if breakdown[section]["count"] > 0 else 0
            )
        
        return breakdown
    
    def detect_drift(self) -> list[str]:
        """
        Detect prompt drift by comparing hashes.
        
        Returns list of drift warnings.
        """
        warnings = []
        
        # Group by node
        by_node: dict[str, list[PromptMetrics]] = {}
        for m in self.prompt_metrics:
            if m.node not in by_node:
                by_node[m.node] = []
            by_node[m.node].append(m)
        
        # Check for hash changes within same node
        for node, metrics_list in by_node.items():
            system_hashes = set(m.system_hash for m in metrics_list)
            if len(system_hashes) > 1:
                warnings.append(
                    f"{node}: System prompt changed during session "
                    f"(hashes: {system_hashes})"
                )
        
        return warnings


# Global collector instance (per-process)
_collector: MetricsCollector | None = None


def get_collector() -> MetricsCollector:
    """Get or create the metrics collector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_collector() -> None:
    """Reset the collector (for testing or new sessions)."""
    global _collector
    _collector = None
```

#### Update `src/alfred/llm/client.py`

Integrate metrics collection into LLM calls:

```python
# Add imports
from alfred.observability.metrics import (
    analyze_prompt,
    get_collector,
    ResponseMetrics,
)

async def call_llm(
    response_model: type,
    system_prompt: str,
    user_prompt: str,
    complexity: str = "medium",
    node: str | None = None,  # Add node parameter
    step_type: str | None = None,
    subdomain: str | None = None,
) -> Any:
    """Call LLM with observability."""
    
    collector = get_collector()
    node = node or _current_node or "unknown"
    
    # Record prompt metrics
    prompt_metrics = analyze_prompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        node=node,
        step_type=step_type,
        subdomain=subdomain,
    )
    collector.record_prompt(prompt_metrics)
    
    # Time the call
    start_time = time.time()
    error = None
    success = True
    action_type = None
    output_tokens = 0
    
    try:
        # ... existing LLM call logic ...
        
        # Extract action type from response
        if hasattr(result, "action"):
            action_type = result.action
        
        return result
        
    except Exception as e:
        error = str(e)
        success = False
        raise
        
    finally:
        # Record response metrics
        latency_ms = (time.time() - start_time) * 1000
        
        response_metrics = ResponseMetrics(
            node=node,
            latency_ms=latency_ms,
            output_tokens=output_tokens,  # TODO: Get from API response
            success=success,
            action_type=action_type,
            error=error,
            model=model_name,
            complexity=complexity,
        )
        collector.record_response(response_metrics)
```

#### Add metrics endpoint

In `src/alfred/server.py`:

```python
from alfred.observability.metrics import get_collector

@app.get("/api/metrics")
async def get_metrics():
    """Get current session metrics."""
    collector = get_collector()
    return {
        "summary": collector.get_summary(),
        "section_breakdown": collector.get_section_breakdown(),
        "drift_warnings": collector.detect_drift(),
    }
```

### Logging Enhancements

#### Structured prompt logs

Update prompt logging to include metrics:

```python
# In prompt logging (wherever prompts are saved)
def log_prompt(
    node: str,
    system_prompt: str,
    user_prompt: str,
    response: Any,
    metrics: PromptMetrics,
):
    """Log prompt with metrics."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "node": node,
        "metrics": metrics.to_dict(),
        "prompts": {
            "system": system_prompt,
            "user": user_prompt,
        },
        "response": response,
    }
    
    # Write to structured log file
    log_path = PROMPT_LOGS_DIR / f"{node}_{datetime.utcnow().strftime('%H%M%S')}.json"
    with open(log_path, "w") as f:
        json.dump(log_entry, f, indent=2, default=str)
```

---

## 3. Implementation Plan

### Phase 1: Observability (1-2 days)

**Goal**: Get visibility into token usage and prompt performance.

| Task | Effort | Priority |
|------|--------|----------|
| Create `observability/metrics.py` | 2hr | P0 |
| Integrate into `llm/client.py` | 1hr | P0 |
| Add `/api/metrics` endpoint | 30min | P1 |
| Update prompt logging format | 1hr | P1 |
| Add `tiktoken` dependency | 5min | P0 |

**Deliverables**:
- Token counts logged for every LLM call
- Section breakdown visible
- Metrics endpoint for debugging

### Phase 2: Semantic Search (2-3 days)

**Goal**: Enable natural language recipe discovery.

| Task | Effort | Priority |
|------|--------|----------|
| Migration `020_recipe_embeddings.sql` | 30min | P0 |
| Create `tools/semantic_search.py` | 2hr | P0 |
| Update `crud.py` for semantic queries | 1hr | P0 |
| Embed on recipe create | 30min | P0 |
| Backfill script | 1hr | P1 |
| Update `read.md` prompt | 30min | P1 |
| Update Act node to detect semantic queries | 1hr | P1 |

**Deliverables**:
- Semantic search working end-to-end
- Existing recipes embedded
- New recipes auto-embedded

### Phase 3: Integration & Testing (1 day)

| Task | Effort | Priority |
|------|--------|----------|
| Test semantic search with various queries | 1hr | P0 |
| Verify token metrics accuracy | 30min | P0 |
| Add to dashboard (if exists) | 1hr | P2 |
| Documentation updates | 30min | P1 |

---

## 4. Future Work (Deferred)

### 4a. Synthetic User Testing Loop

**Concept**: Use LLM agents to simulate users with different personas for automated testing.

```
┌──────────────┐         ┌──────────────┐
│  PERSONA LLM │ ──────▶ │   ALFRED     │
│  (fake user) │         │  (your app)  │
└──────────────┘         └──────────────┘
       ▲                         │
       │                         ▼
       │                  ┌──────────────┐
       └────────────────  │   EVALUATOR  │
            next turn     │  (judge LLM) │
                          └──────────────┘
```

**Personas to test**:
- Busy Parent (terse, typos, impatient)
- Aspiring Chef (detailed, asks follow-ups)
- Chaotic Student (vague, changes mind)

**Scenarios**:
- Happy path flows
- Edge cases (reference resolution, mid-plan changes)
- Stress tests (typos, vague requests)

**When to implement**: After V6 is stable and we want systematic prompt iteration.

---

### 4b. Safe Context Deduplication

**Concept**: Avoid repeating entity IDs that appear in both step results and conversation history.

**Approach**:
```python
def format_background_entities(active_entities, step_results):
    # Extract entity IDs already shown in step results
    already_shown = extract_entity_ids(step_results)
    
    # Only show entities NOT in step results
    return {k: v for k, v in active_entities.items() if k not in already_shown}
```

**Risk**: Losing context if deduplication is too aggressive.

**When to implement**: Only if token limits become a problem.

---

### 4c. DSPy/TextGrad Integration

**Concept**: Automatic prompt optimization based on evaluation metrics.

**Prerequisites**:
- Synthetic user testing loop (provides training data)
- Stable evaluation metrics
- Enough historical data

**When to implement**: After synthetic testing proves value.

---

## Appendix: Dependencies

### New Python Dependencies

```toml
# pyproject.toml additions
[project.dependencies]
tiktoken = ">=0.5.0"      # Token counting
pgvector = ">=0.2.0"      # Vector operations (if using Python client)
```

### Database Extensions

```sql
-- Required for semantic search
CREATE EXTENSION IF NOT EXISTS vector;
```

---

*Last updated: 2026-01-10*
