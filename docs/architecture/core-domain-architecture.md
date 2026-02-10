# Core-Domain Architecture

How Alfred's core orchestration engine and domain-specific implementations relate.

---

## 1. Package Structure

Alfred is split into two Python packages in a mono-repo:

```
src/
├── alfred/                          ← core orchestration (domain-agnostic)
│   ├── agents/                      AgentProtocol, AgentRouter (2 files)
│   ├── context/                     Context builders, entity tracking, reasoning (5 files)
│   ├── core/                        SessionIdRegistry, modes, payload_compiler (4 files)
│   ├── db/                          DatabaseAdapter protocol + compat shim (2 files)
│   ├── domain/                      DomainConfig ABC + registration (2 files)
│   ├── graph/
│   │   ├── nodes/                   act, reply, router, summarize, think, understand (7 files)
│   │   ├── state.py                 AlfredState TypedDict + all data models
│   │   └── workflow.py              LangGraph construction + streaming
│   ├── llm/                         LLM client, model router, prompt logger (4 files)
│   ├── memory/                      Conversation history management (2 files)
│   ├── modes/                       Handoff protocol (2 files)
│   ├── observability/               LangSmith integration, session logging (3 files)
│   ├── prompts/
│   │   ├── injection.py             Act prompt assembly
│   │   └── templates/               11 core .md templates (1,635 lines)
│   ├── tools/                       CRUD executor, schema builder, normalization (5 files)
│   └── config.py                    CoreSettings (OpenAI, LangSmith, env)
│
└── alfred_kitchen/                   ← kitchen domain implementation
    ├── background/                   Profile builder, dashboard caching (2 files)
    ├── db/                           Supabase client, request context (3 files)
    ├── domain/
    │   ├── __init__.py               KitchenConfig (673 lines) + KITCHEN_DOMAIN singleton
    │   ├── compilers.py              RecipeCompiler, MealPlanCompiler, etc.
    │   ├── crud_middleware.py         KitchenCRUDMiddleware (semantic search, auto-includes)
    │   ├── examples.py               Contextual examples per subdomain
    │   ├── formatters.py             Record formatting (recipes, inventory, etc.)
    │   ├── handoff.py                Cook/brainstorm handoff models
    │   ├── personas.py               Subdomain personas and headers
    │   ├── schema.py                 Field enums, fallback schemas, subdomain registry
    │   ├── modes/                    cook.py, brainstorm.py (bypass mode handlers)
    │   ├── prompts/                  8 .py + 3 .md files (2,443 lines)
    │   └── tools/                    ingredient_lookup.py, ingredient_resolver.py
    ├── models/                       Pydantic entities (Recipe, Inventory, etc.) (2 files)
    ├── recipe_import/                Scrapers, parsers (7 files)
    ├── web/                          FastAPI app, routes, auth, sessions (10 files)
    ├── config.py                     KitchenSettings (extends CoreSettings with Supabase)
    ├── main.py                       CLI entry point
    └── server.py                     Health check / server startup
```

### Sizing

| Package | .py Files | Purpose |
|---------|-----------|---------|
| `alfred` | ~43 | Domain-agnostic orchestration, LLM pipeline, CRUD execution |
| `alfred_kitchen` | ~51 | Kitchen entities, formatters, prompts, DB client, web layer |

---

## 2. The DomainConfig Protocol

`DomainConfig` at [base.py:156](src/alfred/domain/base.py#L156) is an ABC that every domain must implement. It has **66 methods** organized into 8 concern areas:

### Method Census

| Concern Area | Abstract | Default | Total | What They Provide |
|-------------|----------|---------|-------|-------------------|
| Core properties | 3 | 2 | 5 | `name`, `entities`, `subdomains`, `table_to_type`, `type_to_table` |
| Prompt/persona | 2 | 1 | 3 | `get_persona()`, `get_examples()`, `get_act_subdomain_header()` |
| Schema/FK | 11 | 0 | 11 | Field enums, fallback schemas, scope config, FK enrichment, user-owned tables |
| CRUD | 0 | 1 | 1 | `get_crud_middleware()` (optional) |
| Entity processing | 3 | 10 | 13 | Entity labels, type inference, archive keys, tracking, content markers |
| Reply formatting | 1 | 8 | 9 | Subdomain formatters, strip fields, record formatting (context + reply) |
| Mode/agent | 2 | 4 | 6 | `bypass_modes`, `default_agent`, agents, router, compilers, LLM config |
| Prompts | 0 | 12 | 12 | System prompt, node-specific content/injection (Think, Act, Reply, Understand, Router) |
| User context | 0 | 3 | 3 | `get_user_profile()`, `get_domain_snapshot()`, `get_subdomain_guidance()` |
| Database | 1 | 0 | 1 | `get_db_adapter()` |
| Handoff | 1 | 1 | 2 | `get_handoff_result_model()`, `get_handoff_system_prompts()` |
| **Total** | **24** | **42** | **66** | |

**24 abstract methods** must be implemented. **42 default methods** provide sensible fallbacks — a new domain can start with just the abstract methods and progressively override defaults.

### Supporting Dataclasses

Three dataclasses underpin the protocol:

**`EntityDefinition`** at [base.py:26](src/alfred/domain/base.py#L26) — describes one entity type:

| Field | Type | Purpose |
|-------|------|---------|
| `type_name` | `str` | Short ref prefix (e.g., `"recipe"` → `recipe_1`) |
| `table` | `str` | Database table name |
| `primary_field` | `str` | Display label field (default: `"name"`) |
| `fk_fields` | `list[str]` | Foreign key columns |
| `complexity` | `str \| None` | Think node hint: `"high"`, `"medium"`, or `None` |
| `label_fields` | `list[str]` | Fields used to compute labels |
| `nested_relations` | `list[str] \| None` | Related tables to auto-include in reads |
| `detail_tracking` | `bool` | Whether to track summary vs full reads |

**`SubdomainDefinition`** at [base.py:55](src/alfred/domain/base.py#L55) — logical table grouping:

| Field | Type | Purpose |
|-------|------|---------|
| `name` | `str` | Subdomain identifier (e.g., `"recipes"`) |
| `primary_table` | `str` | Main table |
| `related_tables` | `list[str]` | Other tables in this subdomain |
| `description` | `str` | Human-readable description for Think prompt |

**`ReadPreprocessResult`** at [base.py:76](src/alfred/domain/base.py#L76) — returned by `CRUDMiddleware.pre_read()`:

| Field | Type | Purpose |
|-------|------|---------|
| `params` | `Any` | Modified read parameters |
| `select_additions` | `list[str]` | Extra SELECT clauses (e.g., nested relations) |
| `pre_filter_ids` | `list[str] \| None` | IDs from semantic search to filter by |
| `or_conditions` | `list[str] \| None` | Additional OR conditions |
| `short_circuit_empty` | `bool` | Return `[]` without querying |

### Computed Properties

Two properties are auto-derived from `entities` — domains get these for free:

- `table_to_type` at [base.py:224](src/alfred/domain/base.py#L224) — maps `"recipes"` → `"recipe"`
- `type_to_table` at [base.py:234](src/alfred/domain/base.py#L234) — maps `"recipe"` → `"recipes"`

---

## 3. Registration

Domain registration uses a simple global pattern in [domain/__init__.py](src/alfred/domain/__init__.py):

```python
_current_domain: DomainConfig | None = None

def register_domain(domain: DomainConfig) -> None:      # line 29
    global _current_domain
    _current_domain = domain

def get_current_domain() -> DomainConfig:                # line 43
    if _current_domain is None:
        import alfred_kitchen  # backwards-compat fallback
        ...
    return _current_domain
```

### How Kitchen Registers

[alfred_kitchen/__init__.py](src/alfred_kitchen/__init__.py) (16 lines) registers at import time:

```python
from alfred.domain import register_domain

def _register():
    from alfred_kitchen.domain import KITCHEN_DOMAIN
    register_domain(KITCHEN_DOMAIN)

_register()
```

The `KITCHEN_DOMAIN` singleton is created at [domain/__init__.py:673](src/alfred_kitchen/domain/__init__.py#L673):

```python
KITCHEN_DOMAIN = KitchenConfig()
```

### Startup Wiring

Every entry point must import `alfred_kitchen` before calling any core function:

| Entry Point | How It Registers |
|-------------|-----------------|
| `alfred_kitchen/main.py` | Top-level `import alfred_kitchen` |
| `alfred_kitchen/server.py` | Top-level `import alfred_kitchen` |
| `tests/conftest.py` | `import alfred_kitchen` in fixture |
| Core's `get_current_domain()` | Backwards-compat fallback: auto-imports `alfred_kitchen` if nothing registered |

The backwards-compat fallback at [domain/__init__.py:60](src/alfred/domain/__init__.py#L60) means core currently auto-discovers kitchen if no domain is explicitly registered. This is a convenience during the transition — future multi-domain setups will require explicit registration.

---

## 4. Core Guarantees

What `alfred` provides without any domain implementation:

| Capability | Module | What You Get |
|-----------|--------|-------------|
| LLM pipeline | `graph/workflow.py` | Understand → Think → Act → Reply → Summarize with conditional routing |
| Entity tracking | `core/id_registry.py` | UUID → human refs (`recipe_1`), detail levels, FK enrichment, cross-turn persistence |
| CRUD execution | `tools/crud.py` | Filter building, ref↔UUID translation, user_id scoping, batch manifests |
| Conversation memory | `memory/conversation.py` | Turn history, compression, engagement summaries, context windowing |
| Prompt assembly | `prompts/injection.py` | 15-section Act prompt builder, subdomain guidance, quick mode prompts |
| Mode system | `core/modes.py` | QUICK/PLAN/CREATE modes with per-mode LLM config |
| Context building | `context/builders.py` | Think/Act/Understand context assembly from state |
| LLM client | `llm/client.py` | `call_llm()` with structured output, model routing by complexity |
| Prompt templates | `prompts/templates/` | 11 structural .md templates as fallback prompts |
| Observability | `observability/` | LangSmith tracing, session logging |
| Agent protocol | `agents/base.py` | `AgentProtocol`, `AgentRouter`, `MultiAgentOrchestrator` |
| State model | `graph/state.py` | `AlfredState` TypedDict with all pipeline data models |

Core is functional with just the default `DomainConfig` methods — it will run a pipeline, track entities, execute CRUD, and produce responses. The results won't be useful without domain-specific entities, prompts, and formatting, but the machinery works.

---

## 5. Domain Responsibilities

### Must Implement (24 abstract methods)

A domain **must** provide:

**Identity:**
- `name` — domain identifier (`"kitchen"`, `"fpl"`)
- `entities` — entity definitions (what types of things exist)
- `subdomains` — how tables are grouped for Think planning

**Prompt content:**
- `get_persona(subdomain, step_type)` — LLM persona per subdomain
- `get_examples(subdomain, step_type, ...)` — contextual examples

**Schema:**
- `get_table_format(table)` — formatting rules per table
- `get_empty_response(subdomain)` — "no results" message
- `get_fk_enrich_map()` — FK→table→name_column mapping
- `get_field_enums()` — valid values for categorical fields
- `get_semantic_notes()` — subdomain clarifications
- `get_fallback_schemas()` — hardcoded schema fallbacks
- `get_scope_config()` — cross-subdomain relationships
- `get_user_owned_tables()` — tables needing user_id scoping
- `get_uuid_fields()` — FK field names containing UUIDs
- `get_subdomain_registry()` — subdomain→tables mapping
- `get_subdomain_examples()` — example queries per subdomain

**Entity processing:**
- `infer_entity_type_from_artifact(artifact)` — type from generated content structure
- `compute_entity_label(record, entity_type, ref)` — human-readable label
- `get_subdomain_aliases()` — informal name → canonical name mapping
- `get_subdomain_formatters()` — reply formatters per subdomain

**Mode/agent:**
- `bypass_modes` — graph-bypass mode handlers (e.g., cook, brainstorm)
- `default_agent` — agent name for single-agent mode

**Infrastructure:**
- `get_handoff_result_model()` — Pydantic model for bypass mode handoff
- `get_db_adapter()` — database access implementation

### Should Override (Key Defaults)

These defaults work but produce generic results:

| Method | Default | Why Override |
|--------|---------|-------------|
| `get_system_prompt()` | `"You are a helpful {name} assistant."` | Domain identity and personality |
| `format_entity_for_context()` | Simple key-value dump | Rich entity display (e.g., recipes with ingredients) |
| `format_record_for_context()` | `"  - {name} id:{ref}"` | Domain-specific fields (quantity, location, cuisine) |
| `get_crud_middleware()` | `None` (no middleware) | Semantic search, auto-includes, enrichment |
| `get_strip_fields()` | Empty set | Hide internal fields from LLM/user |
| Prompt content methods | `""` (fall back to core templates) | Domain-specific examples and guidance |

### Optional (Truly Optional Defaults)

These have sensible defaults that many domains won't need to change:

- `get_tracked_entity_types()` — auto-derived from entities with `complexity` set
- `get_relevant_entity_types()` — auto-derived same way
- `table_to_type`, `type_to_table` — auto-computed from `entities`
- `compute_artifact_label()` — uses `name`/`title` fields
- `get_priority_fields()` — default list: name, title, date, description, notes, category

---

## 6. Import Boundary

**Core never imports domain. Domain imports core freely.**

This is the foundational architectural rule. It means:

- `src/alfred/` has zero imports from `src/alfred_kitchen/`
- `src/alfred_kitchen/` imports freely from `src/alfred/`
- Core accesses domain behavior exclusively through `get_current_domain()` → `DomainConfig` methods

### Enforcement

```bash
# This must return zero hits:
grep -rn "from alfred_kitchen" src/alfred/ --include="*.py"
```

### The One Exception

[db/__init__.py:15-20](src/alfred/db/__init__.py#L15-L20) has a backwards-compat `__getattr__` shim:

```python
def __getattr__(name: str):
    if name == "get_client":
        from alfred_kitchen.db.client import get_client
        return get_client
    raise AttributeError(...)
```

This exists for legacy code paths that call `from alfred.db import get_client`. It's a lazy import (only triggers if accessed) and will be removed when all callers are migrated.

### Why This Matters

The import boundary ensures core can be extracted into a standalone package (`pip install alfred`) that has no knowledge of any specific domain. A new domain (FPL, fitness, etc.) implements `DomainConfig`, calls `register_domain()`, and the entire pipeline works without core changes.

---

## 7. Key Protocols

Four protocols define the extension surface:

### DomainConfig

**File:** [domain/base.py:156](src/alfred/domain/base.py#L156) (1,135 lines)

The central protocol. 66 methods across 8 concern areas (see section 2). A domain implements this to plug into Alfred's pipeline.

### DatabaseAdapter

**File:** [db/adapter.py:23](src/alfred/db/adapter.py#L23) (52 lines)

```python
@runtime_checkable
class DatabaseAdapter(Protocol):
    def table(self, name: str) -> Any:     # Returns query builder
    def rpc(self, function_name: str, params: dict) -> Any:
```

Thin wrapper over the database client. Uses `@runtime_checkable` for duck typing. The `table()` method returns a query builder compatible with PostgREST's fluent API (`.select()`, `.eq()`, `.insert()`, `.execute()`, etc.). Core's `apply_filter()` in `tools/crud.py` calls 12 query builder methods directly.

**Conscious coupling:** The adapter is tied to the PostgREST query builder pattern. This is acceptable while all domains use Supabase. If a future domain uses a different DB, `apply_filter()` is the refactor point.

Kitchen implements this by returning the Supabase client from `get_client()`.

### CRUDMiddleware

**File:** [domain/base.py:97](src/alfred/domain/base.py#L97)

```python
class CRUDMiddleware:
    async def pre_read(self, params, user_id) -> ReadPreprocessResult
    async def pre_write(self, table, records) -> list[dict]
    def deduplicate_batch(self, table, records) -> list[dict]
```

Optional domain intelligence layer that fires inside `execute_crud()`. Default implementations are pass-throughs. Kitchen's `KitchenCRUDMiddleware` adds semantic search (pgvector), auto-includes (recipe_ingredients), fuzzy name matching, and ingredient enrichment.

See [crud-and-database.md](crud-and-database.md) for the full middleware architecture.

### EntityDefinition

**File:** [domain/base.py:26](src/alfred/domain/base.py#L26)

Configuration dataclass for entity types. Not a protocol — it's a value object that domains instantiate. 8 fields control how core handles each entity type (ref naming, FK tracking, nested relations, detail levels).

---

## Kitchen as Reference Implementation

Kitchen implements all 24 abstract methods and overrides ~20 defaults across 673 lines of `KitchenConfig` ([domain/__init__.py](src/alfred_kitchen/domain/__init__.py)), plus ~3,500 lines across 12 submodules (formatters, personas, examples, schema, compilers, middleware, prompts, etc.).

### Kitchen's Entities (10 types)

| Entity | `type_name` | Table | Complexity | Nested Relations |
|--------|------------|-------|-----------|-----------------|
| Recipes | `recipe` | `recipes` | high | `recipe_ingredients` |
| Recipe Ingredients | `ri` | `recipe_ingredients` | — | — |
| Inventory | `inv` | `inventory` | — | — |
| Shopping List | `shop` | `shopping_list` | — | — |
| Meal Plans | `meal` | `meal_plans` | medium | — |
| Tasks | `task` | `tasks` | — | — |
| Preferences | `pref` | `preferences` | — | — |
| Ingredients | `ing` | `ingredients` | — | — |
| Cooking Log | `log` | `cooking_log` | — | — |
| Flavor Preferences | `flavor` | `flavor_preferences` | — | — |

### Kitchen's Subdomains (7 groups)

| Subdomain | Primary Table | Related Tables |
|-----------|--------------|---------------|
| inventory | `inventory` | `ingredients` |
| recipes | `recipes` | `recipe_ingredients`, `ingredients` |
| shopping | `shopping_list` | `ingredients` |
| meal_plans | `meal_plans` | `recipes`, `tasks` |
| tasks | `tasks` | `recipes`, `meal_plans` |
| preferences | `preferences` | `flavor_preferences` |
| history | `cooking_log` | — |

### Kitchen's Bypass Modes

| Mode | Handler | Purpose |
|------|---------|---------|
| `cook` | `run_cook_session` | Interactive cooking guidance (skips graph pipeline) |
| `brainstorm` | `run_brainstorm` | Recipe brainstorming (skips graph pipeline) |

---

## Key Files

| File | Lines | Role |
|------|-------|------|
| [src/alfred/domain/base.py](src/alfred/domain/base.py) | 1,135 | DomainConfig ABC, EntityDefinition, SubdomainDefinition, CRUDMiddleware |
| [src/alfred/domain/__init__.py](src/alfred/domain/__init__.py) | 79 | `register_domain()`, `get_current_domain()` |
| [src/alfred/db/adapter.py](src/alfred/db/adapter.py) | 53 | DatabaseAdapter protocol |
| [src/alfred/db/__init__.py](src/alfred/db/__init__.py) | 20 | Backwards-compat `__getattr__` shim |
| [src/alfred_kitchen/__init__.py](src/alfred_kitchen/__init__.py) | 16 | Import-time domain registration |
| [src/alfred_kitchen/domain/__init__.py](src/alfred_kitchen/domain/__init__.py) | 673 | KitchenConfig implementation + KITCHEN_DOMAIN singleton |
