# Ingredient Database Enrichment

> Canonical ingredient metadata for smarter kitchen management.

**Status:** Implemented (Jan 2026)
**Migration:** 027_ingredient_enrichment.sql

---

## Summary

The `ingredients` table is Alfred's canonical source for ingredient metadata. All user-facing tables (inventory, shopping_list, recipe_ingredients) link to it via `ingredient_id` foreign key.

This spec documents the enrichment of the ingredients table with structured metadata and the integration that flows this data into LLM context.

---

## Schema Changes

### New Columns on `ingredients`

| Column | Type | Description |
|--------|------|-------------|
| `parent_category` | TEXT NOT NULL | Top-level grouping: produce, protein, dairy, grains, pantry, spices, baking, specialty |
| `family` | TEXT NOT NULL | Ingredient family for substitutions (e.g., "alliums" for onion/garlic/shallot) |
| `tier` | INTEGER (1-3) | Commonality: 1=core staples, 2=standard, 3=specialty/niche |
| `cuisines` | TEXT[] | Cuisine associations (e.g., ["indian", "thai"]) |

### New Column on `preferences`

| Column | Type | Description |
|--------|------|-------------|
| `assumed_staples` | UUID[] | User-confirmed always-on-hand ingredients |

---

## Taxonomy

Defined in `config/taxonomy.yaml`:

**Parent Categories:** produce, protein, dairy, grains, pantry, spices, baking, specialty

**Tier Definitions:**
- **Tier 1 (core):** Salt, pepper, olive oil, onion, garlic, butter, eggs
- **Tier 2 (standard):** Most common ingredients found in typical grocery stores
- **Tier 3 (specialty):** Niche items, specialty stores, cuisine-specific

**Cuisine Codes:** american, mexican, italian, french, indian, thai, chinese, japanese, korean, vietnamese, mediterranean, middle_eastern, greek, spanish, caribbean, african

---

## Integration Points

### 1. CRUD Auto-Join (crud.py)

When reading `inventory`, `shopping_list`, or `recipe_ingredients`, the CRUD layer automatically joins ingredient metadata:

```python
# crud.py - auto-added to select clause
", ingredients(parent_category, family, tier, cuisines)"
```

This pulls enriched data without explicit query changes.

### 2. LLM Context Formatting (injection.py)

The `_format_record_clean()` function extracts joined ingredient data and formats it for LLM consumption:

```
frozen cauliflower (1 lb) [freezer] | produce | family:cauliflower | common
chicken breasts (2 lb) | protein | family:chicken | common
gochugaru (1 bag) | spices | family:korean chili | specialty
```

Format: `name (qty unit) [location] | parent_category | family:X | tier_label`

### 3. Semantic Search (embeddings)

Ingredient embeddings now include enriched fields for better semantic matching:

```python
# generate_embeddings.py
text = f"{name} | section: {parent_category} | family: {family} | cuisines: {cuisines}"
```

---

## What This Unlocks

| Capability | How |
|------------|-----|
| Smart grouping | Group inventory/shopping by `parent_category` |
| Substitution hints | Suggest alternatives within same `family` |
| Tier-based filtering | Show common ingredients first (tier=1) |
| Cuisine matching | "Show me Italian ingredients" via `cuisines` filter |
| Semantic similarity | Better embedding matches via enriched text |

---

## Open Question: ingredient_resolver.py

A regex-based resolver was created at `src/alfred/tools/ingredient_resolver.py` that parses strings like "2 lbs boneless chicken thighs" into structured data (qty, unit, modifiers, ingredient match).

**Current status:** Created but NOT wired up.

**Why it may be unnecessary:**
1. The LLM already extracts qty/unit/name before calling CRUD
2. Recipe import has its own LLM-based parser (`recipe_import/ingredient_parser.py`)
3. The `enrich_with_ingredient_id()` function in `ingredient_lookup.py` handles DB matching

**Recommendation:** Keep dormant. Delete if no use case emerges in 3 months. Recipe import already has its own parser that works.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/cleanup_ingredients.py` | LLM-powered batch enrichment (categories, families, tiers, cuisines) |
| `scripts/validate_taxonomy.py` | Validate ingredients against taxonomy rules |
| `scripts/generate_embeddings.py` | Regenerate embeddings with new fields |

---

## Data Stats (Jan 2026)

- Total ingredients: 2,942
- Tier 1 (core): 410 (14%)
- Tier 2 (standard): 1,177 (40%)
- Tier 3 (specialty): 1,355 (46%)
- Cuisine-tagged: 1,404 (48%)
