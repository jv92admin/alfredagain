# Alfred Architecture Documentation Plan

## Context

The domain abstraction refactoring (Phases 0-4d) is complete. Alfred is now split into two packages:
- `alfred` (core) — domain-agnostic orchestration engine
- `alfred_kitchen` — kitchen-specific domain implementation

This plan covers documenting the architecture so that (a) we fully understand the internals, (b) future domains can be built against core, and (c) existing docs reflect the new structure.

---

## Document Inventory

### Tier 1: Deep-Dive Internals (write first — forces thorough understanding)

| # | File | Purpose |
|---|------|---------|
| 1 | `docs/architecture/crud-and-database.md` | CRUD executor, DatabaseAdapter, middleware hooks, filter system |
| 2 | `docs/architecture/sessions-context-entities.md` | SessionIdRegistry, entity lifecycle, context builders, conversation memory |
| 3 | `docs/architecture/pipeline-stages.md` | Graph nodes, routing, state shape, input/output contracts per stage |
| 4 | `docs/architecture/prompt-assembly.md` | Template loading, injection.py composition, domain prompt overrides |

### Tier 2: Architecture / External (synthesize from Tier 1)

| # | File | Purpose |
|---|------|---------|
| 5 | `docs/architecture/core-domain-architecture.md` | How core and domain packages relate, DomainConfig protocol overview |
| 6 | `docs/architecture/core-public-api.md` | What `pip install alfred` gives you — entry points, extension points, capabilities |
| 7 | `docs/architecture/domain-implementation-guide.md` | Step-by-step guide to building a new domain (FPL as worked example) |

### Tier 3: Updates to Existing Files

| # | File | Change |
|---|------|--------|
| 8 | `docs/architecture/overview.md` | Rewrite — currently kitchen-flavored, needs to reflect two-package structure |
| 9 | `CLAUDE.md` | Add core vs kitchen package distinction, update import conventions |
| 10 | `docs/ROADMAP.md` | Mark Phase 4 complete, update Phase 5 items |
| 11 | `README.md` | Rewrite — stale pipeline description ("four nodes", "Instructor"), no two-package structure, wrong agent names |

---

## Writing Order

Tier 1 first (1→2→3→4), then Tier 2 (5→6→7), then Tier 3 (8→9→10).

Rationale: Deep-dive docs force auditing every function and data flow. The external/synthesis docs then draw from that verified understanding. Updates are quick edits last.

---

## Doc 1: crud-and-database.md

**Covers:** How LLM tool calls become database operations and come back as human-readable refs.

**Source map:**

| Topic | Primary File | Key Functions | Grep Pattern |
|-------|-------------|---------------|--------------|
| CRUD models | `src/alfred/tools/crud.py` | `FilterClause`, `DbReadParams`, `DbCreateParams`, `DbUpdateParams`, `DbDeleteParams` | `class Db.*Params` |
| Filter application | `src/alfred/tools/crud.py` | `apply_filter()` | `def apply_filter` |
| Execute dispatcher | `src/alfred/tools/crud.py` | `execute_crud()` | `def execute_crud` |
| Input translation | `src/alfred/tools/crud.py` | `_translate_input_params()` | `def _translate_input` |
| Output translation | `src/alfred/tools/crud.py` | `_translate_output()` | `def _translate_output` |
| Ref↔UUID mapping | `src/alfred/core/id_registry.py` | `translate_read_output()`, `resolve_ref()` | `def translate_read_output\|def resolve_ref` |
| DatabaseAdapter protocol | `src/alfred/db/adapter.py` | `DatabaseAdapter` | `class DatabaseAdapter` |
| Kitchen middleware | `src/alfred_kitchen/domain/crud_middleware.py` | `KitchenCRUDMiddleware`, `pre_read()`, `pre_write()` | `class KitchenCRUD` |
| Middleware protocol | `src/alfred/domain/base.py` | `CRUDMiddleware` | `class CRUDMiddleware` |
| Ingredient enrichment | `src/alfred_kitchen/domain/tools/ingredient_lookup.py` | `lookup_ingredient()` | `def lookup_ingredient` |

**Section outline:**

1. **Data flow diagram** — LLM tool call → Act node → execute_crud() → middleware.pre_read/pre_write → DB → _translate_output → refs back to LLM
2. **Pydantic models** — FilterClause, the 4 Db*Params, what each field means
3. **Filter system** — How `apply_filter()` maps op strings to Supabase query builder methods (12 ops)
4. **Ref translation** — How _translate_input_params swaps `recipe_1` → UUID, and _translate_output swaps UUID → `recipe_1`
5. **DatabaseAdapter protocol** — What a domain must implement, thin wrapper pattern, conscious coupling to PostgREST
6. **CRUDMiddleware hooks** — pre_read (semantic search, auto-includes, fuzzy matching), pre_write (ingredient enrichment, dedup), when each fires
7. **Kitchen middleware walkthrough** — Concrete example: "read recipes with chicken" → semantic search → auto-include recipe_ingredients → format results
8. **Extension point summary** — Table: what core provides vs what domain provides

---

## Doc 2: sessions-context-entities.md

**Covers:** How entities are tracked across turns, how context is built for each node, how conversation memory works.

**Source map:**

| Topic | Primary File | Key Functions | Grep Pattern |
|-------|-------------|---------------|--------------|
| SessionIdRegistry | `src/alfred/core/id_registry.py` | `register_read()`, `register_created()`, `register_generated()`, `resolve_ref()`, `get_active_entities()` | `class SessionIdRegistry` |
| Ref naming | `src/alfred/core/id_registry.py` | `_assign_ref()` | `def _assign_ref` |
| Detail tracking | `src/alfred/core/id_registry.py` | `_track_detail_level()` | `def _track_detail` |
| Entity tiers | `src/alfred/context/entity.py` | `EntitySnapshot`, `EntityContext`, tier classification | `class EntitySnapshot\|class EntityContext` |
| Context builders | `src/alfred/context/builders.py` | `UnderstandContext`, `ThinkContext`, `ReplyContext` | `class.*Context` |
| Reasoning trace | `src/alfred/context/reasoning.py` | `ReasoningTrace`, `TurnSummary`, `StepSummary` | `class ReasoningTrace` |
| ConversationContext type | `src/alfred/graph/state.py` | `ConversationContext` TypedDict | `class ConversationContext` |
| Conversation functions | `src/alfred/memory/conversation.py` | `add_turn_to_context()`, `format_condensed_context()`, `extract_entities_from_result()` | `def add_turn_to_context\|def format_condensed\|def extract_entities_from_result` |
| Graph state | `src/alfred/graph/state.py` | `AlfredState` TypedDict | `class AlfredState` |
| Serialization | `src/alfred/core/id_registry.py` | `serialize()`, `deserialize()` | `def serialize\|def deserialize` |
| FK enrichment | `src/alfred/core/id_registry.py` | `_enrich_lazy_registrations()` | `def _enrich_lazy` |
| Pending artifacts | `src/alfred/core/id_registry.py` | `pending_artifacts` | `pending_artifacts` |

**Section outline:**

1. **Three-layer context model** — Layer 1: Entity (SessionIdRegistry), Layer 2: Conversation (turn history), Layer 3: Reasoning (execution trace)
2. **SessionIdRegistry deep dive** — UUID↔ref mapping, ref naming convention (`{type}_{n}`, `gen_{type}_{n}`), the `_entities` dict structure
3. **Entity lifecycle** — Created (DB write) vs Generated (LLM output) vs Read (DB read). How each registration method works.
4. **Entity tiers** — Active vs Generated vs Retained. How context builders decide what to include and at what detail level.
5. **Detail tracking** — Summary vs full. How `_track_detail_level()` works, when entities get promoted/demoted.
6. **FK lazy registration** — How child entities (recipe_ingredients) get registered when parent is read. The `_enrich_lazy_registrations` flow.
7. **Pending artifacts** — How generated content waits for user confirmation before persistence. The gen_ → saved transition.
8. **Context builders** — What UnderstandContext, ThinkContext, ReplyContext each include. How they draw from the registry + conversation memory.
9. **Conversation memory** — Turn compression, how old turns get summarized, engagement tracking.
10. **Serialization** — How registry state persists across turns via `serialize()`/`deserialize()`.
11. **DomainConfig hooks** — `get_entity_definitions()`, `compute_entity_label()`, `detect_detail_level()`, `get_ref_pattern()`

---

## Doc 3: pipeline-stages.md

**Covers:** The LangGraph pipeline — what each node does, routing logic, state shape, input/output contracts.

**Source map:**

| Topic | Primary File | Key Functions | Grep Pattern |
|-------|-------------|---------------|--------------|
| Graph construction | `src/alfred/graph/workflow.py` | `build_graph()`, `run_alfred_streaming()` | `def build_graph\|def run_alfred` |
| State shape | `src/alfred/graph/state.py` | `AlfredState` | `class AlfredState` |
| Understand node | `src/alfred/graph/nodes/understand.py` | `understand_node()`, `UnderstandOutput` | `def understand_node` |
| Think node | `src/alfred/graph/nodes/think.py` | `think_node()`, `ThinkOutput`, `ThinkStep` | `def think_node` |
| Act node | `src/alfred/graph/nodes/act.py` | `act_node()`, `act_quick_node()`, `ActDecision`, `ActAction` | `def act_node\|def act_quick` |
| Reply node | `src/alfred/graph/nodes/reply.py` | `reply_node()`, `ReplyOutput` | `def reply_node` |
| Summarize node | `src/alfred/graph/nodes/summarize.py` | `summarize_node()`, `TurnExecutionSummary` | `def summarize_node` |
| Router | `src/alfred/graph/nodes/router.py` | `router_node()` | `def router_node` |
| Mode system | `src/alfred/core/modes.py` | `Mode`, `MODE_CONFIG` | `class Mode` |
| Bypass modes | `src/alfred/domain/base.py` | `bypass_modes` property | `bypass_modes` |

**Section outline:**

1. **Pipeline overview** — Understand → Router → Think → Act (loop) → Reply → Summarize. Visual diagram.
2. **AlfredState** — Key fields in the TypedDict, what each node reads and writes.
3. **Understand** — Input: raw user message + conversation context. Output: `UnderstandOutput` (intent, entities, subdomain). Contract.
4. **Router** — Quick mode bypass decision. When it routes to Think vs Act directly.
5. **Think** — Input: understood intent + entity context. Output: `ThinkStep[]` plan. The step types (read, write, analyze, generate). How it decides number of steps.
6. **Act** — The step execution loop. `ActDecision` → `ActAction` union (7 variants). How each action type maps to tool calls. The retry/blocked mechanism.
7. **Act Quick** — Simplified single-step path for quick mode. How it differs from full Act.
8. **Reply** — Input: execution summary + entity context. Output: natural language response. How it uses domain formatters.
9. **Summarize** — Input: full turn state. Output: `TurnExecutionSummary`. What gets persisted for next turn.
10. **Mode system** — Core modes (QUICK/PLAN/CREATE) vs domain bypass modes. How bypass modes skip the graph entirely.
11. **Routing logic** — Conditional edges in the graph. Think→Act loop termination. Error/blocked handling.

---

## Doc 4: prompt-assembly.md

**Covers:** How prompts are built for each node — template loading, dynamic injection, domain overrides.

**Source map:**

| Topic | Primary File | Key Functions | Grep Pattern |
|-------|-------------|---------------|--------------|
| Act prompt builder | `src/alfred/prompts/injection.py` | `build_act_user_prompt()` | `def build_act_user_prompt` |
| Quick prompt builder | `src/alfred/prompts/injection.py` | `build_act_quick_prompt()` | `def build_act_quick_prompt` |
| Section builders | `src/alfred/prompts/injection.py` | `_build_common_sections()`, `_build_step_type_sections()` | `def _build_common\|def _build_step_type` |
| Template loading | `src/alfred/graph/nodes/act.py` | `_load_act_prompt()` | `def _load_act_prompt` |
| Think prompt | `src/alfred/graph/nodes/think.py` | `_load_prompt()`, `_build_system_prompt()` | `def _load_prompt\|def _build_system` |
| Reply prompt | `src/alfred/graph/nodes/reply.py` | `_get_prompts()` | `def _get_prompts` |
| Template dir | `src/alfred/prompts/templates/` | `.md` files | N/A (file glob) |
| Domain prompt content | `src/alfred_kitchen/domain/prompts/` | `reply_content.py`, `reply_guide.py`, `think_context.py` | `REPLY_PROMPT_CONTENT\|REPLY_SUBDOMAIN_GUIDE` |
| Domain overrides | `src/alfred/domain/base.py` | `get_reply_prompt_content()`, `get_think_context()`, `get_system_prompt()` | `def get_reply_prompt\|def get_think_context\|def get_system_prompt` |
| Subdomain guidance | `src/alfred/prompts/injection.py` | `get_subdomain_guidance()`, `format_all_subdomain_guidance()` | `def get_subdomain_guidance\|def format_all_subdomain` |
| Persona injection | `src/alfred/domain/base.py` | `get_persona()`, `get_examples()`, `get_act_subdomain_header()` | `def get_persona\|def get_examples\|def get_act_subdomain` |

**Section outline:**

1. **Prompt composition model** — Core template (structural skeleton) + domain content (examples, personas, entity-specific text). The fallback chain.
2. **Template files** — What lives in `src/alfred/prompts/templates/`, what each .md provides.
3. **Act prompt deep dive** — `build_act_user_prompt()` assembles 15+ sections. Walk through each: entity context, step instructions, subdomain persona, previous results, batch manifest, etc.
4. **Domain prompt override chain** — `domain.get_reply_prompt_content()` → falls back to core template. How kitchen provides `REPLY_PROMPT_CONTENT` vs core providing `reply.md`.
5. **Persona and examples injection** — `get_persona(subdomain, step_type)`, `get_examples(subdomain, step_type)`, `get_act_subdomain_header()`. How these plug into injection.py.
6. **Subdomain guidance** — User preference data surfaced per-subdomain in prompts. Generic mechanism, domain-specific content.
7. **Caching** — Module-level prompt caching (`_SYSTEM_PROMPT`, `_REPLY_PROMPT`). When cache is populated, when it's invalidated (never — app restart).
8. **Node-by-node prompt structure** — Table: node → system prompt source → user prompt source → what gets injected.

---

## Doc 5: core-domain-architecture.md

**Covers:** The two-package split, DomainConfig protocol, how core and domain interact.

**Section outline:**

1. **Package structure** — `alfred` (core) vs `alfred_kitchen` (domain). Directory layout.
2. **The DomainConfig protocol** — ABC overview, ~50 methods grouped by concern (entities, CRUD, formatting, prompts, modes).
3. **Registration** — `register_domain()` / `get_current_domain()`. Startup wiring.
4. **Core guarantees** — What core provides without any domain (graph, LLM, CRUD executor, id registry, etc.).
5. **Domain responsibilities** — What a domain MUST implement vs optional overrides.
6. **Import boundary** — Core never imports domain. Domain imports core freely. Enforced by grep.
7. **Key protocols** — `DomainConfig`, `DatabaseAdapter`, `CRUDMiddleware`, `EntityDefinition`.

---

## Doc 6: core-public-api.md

**Covers:** What you get from `pip install alfred` — the external-facing API surface, and how to extract it into its own repo.

**Section outline:**

1. **Entry points** — `run_alfred_streaming()`, `register_domain()`, bypass mode registration
2. **Capabilities table** — What core gives you for free (orchestration, entity tracking, CRUD, etc.)
3. **Extension points** — DomainConfig methods, CRUDMiddleware, DatabaseAdapter, payload compilers
4. **What domain does NOT touch** — Graph wiring, LLM client, id registry internals, prompt caching
5. **Multi-repo extraction** — How to split `src/alfred/` into its own repo. What the standalone `pyproject.toml` looks like (dependencies: langgraph, openai, pydantic, tiktoken — NOT supabase, fastapi). How `alfred_kitchen` becomes a downstream consumer via `pip install alfred`. What backwards-compat shims (`__getattr__` redirects in `db/__init__.py`, `tools/schema.py`) get removed and what breaks. The import boundary enforcement (`grep -rn "from alfred_kitchen" src/alfred/` must return zero).

---

## Doc 7: domain-implementation-guide.md

**Covers:** Step-by-step guide to creating a new domain.

**Section outline:**

1. **Prerequisites** — What to have ready (entity list, DB, subdomains)
2. **Scaffold** — Create package, implement DomainConfig, register
3. **Entity definitions** — How to define EntityDefinition instances
4. **Database adapter** — Implement DatabaseAdapter for your DB
5. **CRUD middleware** — Optional: semantic search, auto-includes, enrichment
6. **Prompts** — System prompt, personas, examples
7. **Bypass modes** — Optional: domain-specific modes
8. **Testing** — How to test with StubDomainConfig vs real domain
9. **FPL worked example** — Concrete snippets for a hypothetical FPL domain

---

## Tier 3: Quick Updates

**Doc 8: overview.md** — Rewrite 148-line kitchen-flavored doc to reflect two-package structure. Reference new Tier 1/2 docs for details.

**Doc 9: CLAUDE.md** — Add section on `alfred` vs `alfred_kitchen` packages. Update import conventions (which imports come from where).

**Doc 10: ROADMAP.md** — Mark Phase 4 complete. Update Phase 5 items. Add documentation milestone.

**Doc 11: README.md** — Rewrite. Current version says "four nodes", references "Instructor", lists "Coach Agent" and "Cellar Agent" that don't exist, and has no mention of the two-package structure. Update to reflect: 5-node pipeline (Understand → Think → Act → Reply → Summarize), core/domain split, correct tech stack, current project structure diagram.

---

## Verification

After all docs written:
1. Each Tier 1 doc has a source map table verified against actual code (grep patterns return expected functions)
2. Each doc cross-references related docs where appropriate
3. No stale kitchen-only references in core-facing docs
4. CLAUDE.md accurately reflects current package structure
5. A new contributor could read docs 5→6→7 and understand how to build a domain

---

## Effort Estimate

| Tier | Docs | Sessions |
|------|------|----------|
| Tier 1: Deep-dive internals | 4 docs | 2-3 |
| Tier 2: Architecture/external | 3 docs | 1-2 |
| Tier 3: Updates | 4 files | 0.5 |
| **Total** | **11 items** | **3-5 sessions** |
