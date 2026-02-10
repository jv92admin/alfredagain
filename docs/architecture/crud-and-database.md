# CRUD & Database Layer

How LLM tool calls become database operations and come back as human-readable refs.

---

## Data Flow

```
LLM decides: "db_read recipes where cuisine = indian"
    │
    ▼
Act Node (graph/nodes/act.py)
    │  Parses LLM structured output into tool + params dict
    │
    ▼
execute_crud(tool, params, user_id, registry)     ← tools/crud.py:457
    │
    │  1. Read rerouting: check if refs point to generated content (gen_*)
    │  2. Input translation: refs → UUIDs (via SessionIdRegistry)
    │  3. Payload sanitization: strip NUL bytes from LLM-generated strings
    │  4. Get domain middleware: domain.get_crud_middleware()
    │
    ▼
db_read / db_create / db_update / db_delete        ← tools/crud.py:146,266,313,341
    │
    │  • Middleware pre_read() or pre_write() fires (if middleware exists)
    │  • Build query via DatabaseAdapter.table().select()/insert()/etc.
    │  • Auto-scope by user_id for user-owned tables
    │  • Apply filters via apply_filter()
    │  • Execute against database
    │
    ▼
execute_crud (post-processing)
    │
    │  5. Output translation: UUIDs → refs (via SessionIdRegistry)
    │  6. FK lazy enrichment: batch-fetch names for FK refs
    │  7. Label injection: add _recipe_id_label = "Butter Chicken" to results
    │
    ▼
Act Node receives: [{id: "recipe_1", name: "Butter Chicken", ...}]
```

---

## Pydantic Models

All tool parameters are Pydantic models. The LLM outputs JSON matching these shapes, and the Act node validates them before calling `execute_crud()`.

### FilterClause (`tools/crud.py:38`)

A single filter condition. Filters combine with AND by default.

```python
class FilterClause(BaseModel):
    field: str                          # Column name, or "_semantic" for vector search
    op: Literal["=", "!=", "neq",       # 14 supported operators
                ">", "<", ">=", "<=",
                "in", "not_in", "ilike",
                "is_null", "is_not_null",
                "contains", "similar"]
    value: Any                          # Varies by op
```

Special ops:
- `"similar"` with `field="_semantic"` — triggers domain middleware semantic search (not applied by `apply_filter()`)
- `"contains"` — PostgreSQL `@>` array containment operator
- `"ilike"` — case-insensitive LIKE pattern matching

### DbReadParams (`tools/crud.py:50`)

```python
class DbReadParams(BaseModel):
    table: str
    filters: list[FilterClause] = []       # AND-combined
    or_filters: list[FilterClause] = []    # OR-combined, then AND'd with filters
    columns: list[str] | None = None       # None = SELECT *
    limit: int | None = None
    order_by: str | None = None
    order_dir: Literal["asc", "desc"] = "asc"
```

### DbCreateParams (`tools/crud.py:68`)

```python
class DbCreateParams(BaseModel):
    table: str
    data: dict[str, Any] | list[dict[str, Any]]   # Single record or batch
```

### DbUpdateParams / DbDeleteParams (`tools/crud.py:80,88`)

Both require `filters` — no accidental full-table operations.

```python
class DbUpdateParams(BaseModel):
    table: str
    filters: list[FilterClause]     # Required
    data: dict[str, Any]

class DbDeleteParams(BaseModel):
    table: str
    filters: list[FilterClause]     # Required
```

---

## Filter System

`apply_filter()` (`tools/crud.py:100`) maps each `FilterClause.op` to a Supabase/PostgREST query builder method:

| Op | Query Builder Call | Example |
|----|--------------------|---------|
| `=` | `.eq(field, value)` | `name = "Chicken Tikka"` |
| `!=` / `neq` | `.neq(field, value)` | `status != "completed"` |
| `>` `<` `>=` `<=` | `.gt()` `.lt()` `.gte()` `.lte()` | `quantity > 0` |
| `in` | `.in_(field, value)` | `id in [uuid1, uuid2]` |
| `not_in` | `.neq(field, value[0])` for single-value lists; **no-op with warning** for multi-value (Supabase lacks native `not_in`) | `status not in ["archived"]` |
| `ilike` | `.ilike(field, value)` | `name ilike "%chicken%"` |
| `is_null` | `.is_(field, "null")` | `expiry_date IS NULL` |
| `is_not_null` | `.not_.is_(field, "null")` | `expiry_date IS NOT NULL` |
| `contains` | `.contains(field, [value])` | `tags @> ["quick"]` (array containment) |

OR filters are serialized into PostgREST `.or_()` string format (e.g., `"name.ilike.%chicken%,cuisine.eq.indian"`).

**Conscious coupling:** `apply_filter()` is coupled to the PostgREST query builder interface — 12 distinct methods (`.eq()`, `.gt()`, `.ilike()`, `.contains()`, `.is_()`, `.not_.is_()`, `.in_()`, `.or_()`, etc.). This is acceptable while all domains use Supabase. If a future domain uses a different DB, `apply_filter()` is the refactor point.

---

## Ref Translation (SessionIdRegistry Integration)

LLMs never see UUIDs. The CRUD layer translates between human-readable refs (`recipe_1`, `inv_3`) and database UUIDs at the boundary.

### Input: Refs → UUIDs

`_translate_input_params()` (`tools/crud.py:621`) runs before every CRUD operation when a registry is provided:

1. **Filter values** — If a filter says `{field: "id", op: "=", value: "recipe_1"}`, the value is replaced with the real UUID via `registry.translate_filters()`.
2. **Payload FK fields** — If a create/update payload has `{recipe_id: "recipe_1"}`, it's translated to the real UUID via `registry.translate_payload()`.

### Output: UUIDs → Refs

`_translate_output()` (`tools/crud.py:663`) runs after every CRUD operation:

- **db_read** — Calls `registry.translate_read_output(results, table)`, which registers each returned entity and replaces its UUID `id` with a ref like `recipe_3`.
- **db_create** — Registers the newly created entity via `registry.register_created()`, assigns a new ref.
- **db_update / db_delete** — Uses `translate_read_output()` to translate returned records.

### Read Rerouting for Generated Content

`_try_reroute_pending_read()` (`tools/crud.py:405`) handles a special case: when the LLM asks to read `gen_recipe_1`, which exists only in the registry (not in the database).

This runs **before** input translation (the `gen_recipe_1` ref hasn't been mapped to a UUID — it has a `__pending__` placeholder). The function checks `registry.get_entity_data(ref)` and returns the in-memory data directly, bypassing the database entirely.

This enables: "read gen_recipe_1" → returns the LLM-generated recipe content so the user can review it before saving.

---

## DatabaseAdapter Protocol

`DatabaseAdapter` (`db/adapter.py:23`) is the abstraction between core CRUD and any database backend.

```python
@runtime_checkable
class DatabaseAdapter(Protocol):
    def table(self, name: str) -> Any:
        """Return a query builder for the given table.
        Must support .select(), .insert(), .update(), .delete(),
        .eq(), .execute(), and other PostgREST-style fluent methods."""
        ...

    def rpc(self, function_name: str, params: dict) -> Any:
        """Call a stored procedure / database function.
        Returns an object with .execute() that yields .data."""
        ...
```

**What a domain implements:** An object satisfying this protocol. For the kitchen domain, `get_db_adapter()` returns the raw Supabase Client directly — it natively satisfies the protocol (has `.table()` and `.rpc()` methods) so no wrapper class is needed.

**What core calls:** Only `adapter.table(name)` (in `db_read`, `db_create`, `db_update`, `db_delete`) and the returned query builder's fluent methods. The `rpc()` method is used by `tools/schema.py` for schema introspection.

---

## CRUDMiddleware

The middleware pattern separates domain intelligence from the generic CRUD executor. Core handles query building, filter application, and ref translation. Middleware transforms params before execution and records before writes.

### Protocol (`domain/base.py:97`)

```python
class CRUDMiddleware:
    async def pre_read(self, params, user_id) -> ReadPreprocessResult
    async def pre_write(self, table, records) -> list[dict]
    def deduplicate_batch(self, table, records) -> list[dict]
```

### ReadPreprocessResult (`domain/base.py:76`)

The return type of `pre_read()`. Encapsulates all modifications to apply to a read query:

| Field | Type | Purpose |
|-------|------|---------|
| `params` | `DbReadParams` | Modified params (filters may be rewritten) |
| `select_additions` | `list[str]` | Extra SELECT clauses (e.g., nested joins) |
| `pre_filter_ids` | `list[str] \| None` | Pre-computed IDs to filter by (e.g., from semantic search) |
| `or_conditions` | `list[str] \| None` | Additional OR conditions in PostgREST format |
| `short_circuit_empty` | `bool` | If True, return `[]` without querying |

### When Middleware Fires

```
execute_crud()
    ├── db_read:   middleware.pre_read()  → modify query → execute → return
    ├── db_create: middleware.pre_write() → enrich records → execute
    │              middleware.deduplicate_batch() → dedup batch → execute
    ├── db_update: (no middleware hooks)
    └── db_delete: (no middleware hooks)
```

---

## Kitchen Middleware Walkthrough

`KitchenCRUDMiddleware` (`alfred_kitchen/domain/crud_middleware.py:192`) implements 6 capabilities:

### 1. Semantic Search (pre_read)

When a filter has `field="_semantic"`, the middleware calls `_semantic_search_recipes()` which:
- Generates an embedding for the query text via OpenAI
- Calls the `match_recipe_semantic` Supabase RPC (pgvector cosine similarity)
- Returns matching recipe UUIDs as `pre_filter_ids`
- Removes the `_semantic` filter from the filter list

If no semantic matches found, returns `short_circuit_empty=True` — the query returns `[]` without hitting the database.

### 2. Auto-Include Nested Relations (pre_read)

For `recipes` reads: adds `recipe_ingredients(name, category)` to the SELECT clause via `select_additions`. This makes Supabase join the `recipe_ingredients` table automatically.

For ingredient-linked tables (`inventory`, `shopping_list`, `recipe_ingredients`): adds `ingredients(parent_category, family, tier, cuisines)` to join the ingredients catalog.

### 3. Fuzzy Name Matching (pre_read)

For recipe name filters: rewrites `{field: "name", op: "=", value: "chicken tikka"}` to `{field: "name", op: "ilike", value: "%chicken tikka%"}`. This makes recipe name searches case-insensitive partial matches.

### 4. Ingredient Catalog Lookup (pre_read)

For `inventory` and `shopping_list` name searches: looks up the ingredient name in the ingredients catalog to find canonical `ingredient_id`s. For both tables, the name filter is removed after lookup. However, OR conditions to match by `ingredient_id` are only built for `inventory` (line 281: `if ingredient_ids and table == "inventory"`). For `shopping_list`, the lookup runs but the resolved IDs are not used as filter conditions — this may be an unfinished code path.

### 5. Ingredient Enrichment (pre_write)

For writes to ingredient-linked tables: enriches records with `ingredient_id` and `category` by looking up the item name in the ingredients catalog. Uses a high confidence threshold (0.85) — only auto-links on strong matches.

### 6. Batch Deduplication (deduplicate_batch)

For batch inserts to ingredient-linked tables: deduplicates by `ingredient_id` (or name fallback). Keeps the last occurrence (later entries may have updated quantities).

---

## User Ownership & Security

Tables in `domain.get_user_owned_tables()` get automatic `user_id` scoping:

- **Reads:** `.eq("user_id", user_id)` filter auto-added
- **Creates:** `user_id` field auto-injected into records
- **Updates/Deletes:** `.eq("user_id", user_id)` filter auto-added

This enforces row-level data isolation at the application layer. Combined with Supabase's database-level RLS, it provides defense-in-depth.

Additional safety: `db_delete()` raises `ValueError` if called on a non-user-owned table with empty filters — prevents accidental full-table deletes.

---

## Payload Sanitization

Two sanitization layers protect against LLM output corruption:

1. **UUID field sanitization** (`_sanitize_uuid_fields`, `tools/crud.py:249`) — Converts empty strings `""` to `None` for UUID-type fields. LLMs sometimes output `""` instead of `null` for optional FK fields, which would fail PostgreSQL's UUID validation.

2. **NUL byte sanitization** (`_sanitize_payload`, `tools/crud.py:742`) — Strips `\x00` characters from all string values. LLMs occasionally corrupt Unicode to NULL bytes, which PostgreSQL rejects with `'\u0000 cannot be converted to text'`.

---

## FK Lazy Enrichment

When a `db_read` returns records with FK UUIDs (e.g., `meal_plans` with `recipe_id`), the output translation registers those FKs to prevent UUID leakage. But the registry only knows the UUID — not the name.

`_enrich_lazy_registrations()` (`tools/crud.py:562`) batch-fetches the actual names:

1. Gets the enrichment queue from the registry (`registry.get_lazy_enrich_queue()`)
2. Groups FKs by target table
3. Batch-queries each table for `[id, name_column]`
4. Maps UUIDs → names and calls `registry.apply_enrichment()`

After enrichment, `_add_enriched_labels()` (`tools/crud.py:529`) injects labels into the result:
```
{recipe_id: "recipe_1", _recipe_id_label: "Butter Chicken"}
```

The LLM sees both the ref and the human-readable name.

---

## Extension Point Summary

| Concern | Core Provides | Domain Provides |
|---------|--------------|-----------------|
| Query building | `apply_filter()`, SELECT/INSERT/UPDATE/DELETE construction | `DatabaseAdapter` (thin wrapper around DB client) |
| Filter operators | 14 ops mapped to PostgREST methods | — |
| User scoping | Auto-inject `user_id` filter/field | `get_user_owned_tables()` — which tables need scoping |
| UUID sanitization | Empty string → None conversion | `get_uuid_fields()` — which fields are UUIDs |
| Ref translation | `_translate_input_params()`, `_translate_output()` | — (handled by core SessionIdRegistry) |
| FK enrichment | `_enrich_lazy_registrations()`, label injection | `get_fk_enrich_map()` — FK field → (table, name_col) |
| Read pre-processing | Calls `middleware.pre_read()`, applies result | `CRUDMiddleware.pre_read()` — semantic search, auto-includes, etc. |
| Write pre-processing | Calls `middleware.pre_write()` + `deduplicate_batch()` | `CRUDMiddleware.pre_write()` — record enrichment |
| Payload safety | NUL byte stripping, UUID field sanitization | — |
| Read rerouting | `_try_reroute_pending_read()` for `gen_*` refs | — (uses SessionIdRegistry data) |

---

## Key Files

| File | Role | Lines |
|------|------|-------|
| `src/alfred/tools/crud.py` | Core CRUD executor | 768 |
| `src/alfred/db/adapter.py` | DatabaseAdapter protocol | 53 |
| `src/alfred/domain/base.py` | DomainConfig protocol (CRUD-relevant: CRUDMiddleware at line 97, ReadPreprocessResult at line 76, CRUD config methods at lines 396-443) | 1135 total |
| `src/alfred_kitchen/domain/crud_middleware.py` | Kitchen middleware implementation | 311 |
| `src/alfred_kitchen/domain/tools/ingredient_lookup.py` | Ingredient catalog lookups (used by middleware) | 587 |
| `src/alfred/core/id_registry.py` | SessionIdRegistry (ref translation, FK enrichment) | 1166 |
