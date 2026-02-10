# Sessions, Context & Entities

How entities are tracked across turns, how context is built for each node, and how conversation memory works.

---

## Three-Layer Context Model

Every node in the pipeline receives context assembled from three independent layers:

```
Layer 1: Entity (SessionIdRegistry)
    UUID↔ref mappings, entity metadata, temporal tracking, pending artifacts
    Persists: across turns within a session (serialized in AlfredState.id_registry)

Layer 2: Conversation (ConversationContext)
    Turn history, engagement summary, history compression, step summaries
    Persists: across turns within a session (stored in AlfredState.conversation)

Layer 3: Reasoning (TurnExecutionSummary → ReasoningTrace)
    What Think decided, what steps executed, what Understand curated
    Persists: last 2 turns in conversation["turn_summaries"], older compressed to reasoning_summary
```

Each node draws different slices from these layers via dedicated context builders:

| Node | Builder | Layers Used | What It Gets |
|------|---------|-------------|--------------|
| Understand | `build_understand_context()` | 1 + 2 | Entity registry table + conversation with entity annotations + decision history |
| Think | `build_think_context()` | 1 + 2 + 3 | Entity context with detail tracking + conversation + reasoning trace + curation |
| Act | `build_act_entity_context()` | 1 | Entity refs + labels + full data for generated content (lives in act.py) |
| Reply | `build_reply_context()` | 1 + 2 + 3 | Entity refs with saved/generated status + conversation + reasoning + execution outcome |

---

## SessionIdRegistry Deep Dive

`SessionIdRegistry` (`core/id_registry.py`) is a `@dataclass` that persists across turns within a session. It is the single source of truth for entity tracking.

### Core Data Structures

```python
@dataclass
class SessionIdRegistry:
    session_id: str = ""

    # Bidirectional UUID↔ref mapping (persists across turns)
    ref_to_uuid: dict[str, str]    # "recipe_1" → "a508000d-9b55-..."
    uuid_to_ref: dict[str, str]    # "a508000d-9b55-..." → "recipe_1"

    # Sequential counters per entity type
    counters: dict[str, int]       # {"recipe": 3, "inv": 7}
    gen_counters: dict[str, int]   # {"recipe": 1}  (for gen_* refs)

    # Full content of generated artifacts (cross-turn persistence)
    pending_artifacts: dict[str, dict]  # "gen_recipe_1" → {name: "Butter Chicken", ...}

    # Per-ref metadata (all deterministic — set by CRUD layer, not LLMs)
    ref_actions: dict[str, str]     # "recipe_1" → "read" | "created" | "generated" | "linked"
    ref_labels: dict[str, str]      # "recipe_1" → "Butter Chicken"
    ref_types: dict[str, str]       # "recipe_1" → "recipe"

    # Detail tracking (for entities with detail_tracking=True in EntityDefinition)
    ref_detail_tracking: dict[str, dict]  # "recipe_1" → {"level": "full", "full_turn": 3}

    # Temporal tracking
    ref_turn_created: dict[str, int]    # When first seen
    ref_turn_last_ref: dict[str, int]   # When last referenced
    ref_source_step: dict[str, int]     # Which step created it
    ref_turn_promoted: dict[str, int]   # When gen_* ref was saved to DB

    current_turn: int = 0

    # Understand context management
    ref_active_reason: dict[str, str]   # Why older entity is still active

    # Internal queues
    _lazy_enrich_queue: dict[str, tuple[str, str]]  # Refs needing name enrichment
    _last_snapshot_refs: set[str]  # For frontend change tracking
```

### Ref Naming Convention

Refs are human-readable identifiers that follow a strict naming pattern:

- **Database entities:** `{type}_{n}` — e.g., `recipe_1`, `inv_5`, `meal_plan_2`
- **Generated (unsaved) entities:** `gen_{type}_{n}` — e.g., `gen_recipe_1`

The `type` comes from `EntityDefinition.type_name` (defined by the domain). The `n` is a monotonically increasing counter per type within the session. Counters never reset within a session — `recipe_1` always refers to the same entity.

### Ref Detection

`_is_ref()` distinguishes refs from UUIDs by format:
- UUIDs: 36 chars, 4 hyphens (e.g., `a508000d-9b55-40f0-8886-dbdd88bd2de2`)
- Refs: contain `_`, last segment is a number (e.g., `recipe_1`, `gen_recipe_1`)

---

## Entity Lifecycle

Entities enter the registry through four paths, each with a distinct registration method:

### 1. Read from Database → `translate_read_output()`

When the CRUD layer executes `db_read`, the returned records pass through `translate_read_output()`. For each record:

1. Check if the UUID already has a ref (from a prior turn) — reuse it
2. If new, assign the next sequential ref via `_next_ref()`
3. Store bidirectional mapping (`ref_to_uuid` + `uuid_to_ref`)
4. Set `ref_actions[ref] = "read"`, compute and store label
5. Track temporal data (`turn_created`, `turn_last_ref`)
6. Detect detail level via `domain.detect_detail_level()` and store in `ref_detail_tracking`
7. Translate FK fields (see "FK Lazy Registration" below)
8. Translate nested relations (e.g., `recipe_ingredients` inside a recipe read)

### 2. Generated by LLM → `register_generated()`

When the Act node executes a `generate` step, the LLM produces content (e.g., a recipe). The Act node calls `register_generated()`:

1. Assign a `gen_` prefixed ref via `_next_gen_ref()` — e.g., `gen_recipe_1`
2. Store `__pending__` as the UUID placeholder (no real UUID yet)
3. Set `ref_actions[ref] = "generated"`
4. **Store the full artifact content** in `pending_artifacts` — this is what enables cross-turn "generate now, save later"

### 3. Created in Database → `register_created()`

When the CRUD layer executes `db_create`, it calls `register_created()`. This handles two cases:

**Case A — Promoting a generated entity:** If the user says "save that recipe" and the LLM writes `gen_recipe_1` to the database:
1. `register_created(None, uuid, "recipe", "Butter Chicken")` is called
2. `_find_matching_pending_artifact()` searches `pending_artifacts` by type + label
3. Finds `gen_recipe_1`, promotes it: updates `ref_to_uuid[gen_recipe_1]` from `__pending__` to the real UUID
4. Sets `ref_actions[gen_recipe_1] = "created"` and `ref_turn_promoted[gen_recipe_1] = current_turn`
5. Content is **retained** in `pending_artifacts` until turn end (needed for linked records like recipe_ingredients)

**Case B — Direct creation (no prior gen):** A new entity created without a generate step:
1. Assign the next sequential ref via `_next_ref()`
2. Store mapping as normal

### 4. Registered from UI → `register_from_ui()`

When the frontend reports a user action (create/edit/delete via UI), `register_from_ui()` registers the entity:
1. Check if UUID already known — if so, update action and touch
2. If new, assign a ref and register with action like `"created:user"` or `"updated:user"`

### Action Tags Reference

Each entity carries an action tag reflecting how it entered or was last modified in the registry:

| Tag | Source | Meaning |
|-----|--------|---------|
| `read` | AI via CRUD | Entity fetched from database |
| `created` | AI via CRUD | AI created entity in database |
| `updated` | AI via CRUD | AI updated entity in database |
| `deleted` | AI via CRUD | AI deleted entity from database |
| `generated` | Act node | LLM produced content (not yet saved) |
| `linked` | CRUD layer | FK lazy registration (parent read pulled in child ref) |
| `created:user` | Frontend UI | User created entity via form |
| `updated:user` | Frontend UI | User edited entity via form |
| `deleted:user` | Frontend UI | User deleted entity via UI |
| `mentioned:user` | Chat input | User @-mentioned entity in chat |

The `:user` suffix distinguishes frontend-initiated actions from AI-initiated ones in prompt context.

---

## Entity Tiers & Active Context

Not all registered entities appear in prompts. The registry uses a **tiered system** to decide which entities are "active" in the current context.

### `get_active_entities(turns_window=2)`

This is the core method. It returns two lists:

1. **Recent refs** — Entities referenced within the last `turns_window` turns (default: 2). These are automatically active based purely on recency. No LLM decision needed.

2. **Retained refs** — Entities older than the window but explicitly kept active by the Understand node. Each has a `ref_active_reason` explaining why (e.g., "User's ongoing weekly meal plan goal").

```
Turn 1: Read recipe_1, recipe_2, recipe_3
Turn 2: Read inv_1, inv_2 (recipe_1-3 still in 2-turn window)
Turn 3: Read meal_plan_1 (recipe_1-3 fall out of window unless Understand retains them)
         inv_1, inv_2 still in window
```

### Understand Curation

The Understand node runs at the start of each turn. It sees the full entity registry table and decides:
- **Retain:** Keep older entity active with a reason → `set_active_reason(ref, reason)`
- **Demote:** Let older entity fall out of context → `clear_active_reason(ref)`

This is how long-term context management works — it's LLM-curated rather than purely time-based.

### Entity Tiers in Context

The `EntityContext` dataclass (`context/entity.py`) structures entities into three tiers for prompt injection:

| Tier | Source | Contents |
|------|--------|----------|
| `active` | Recent refs (automatic 2-turn window) | Entities the LLM just worked with |
| `generated` | Refs with `pending_artifacts` data AND action `"generated"` | Unsaved LLM output |
| `retained` | Understand-curated (older but relevant) | Entities with `ref_active_reason` |

Each node formats entity tiers through its own implementation:

| Node | Formatter | What It Shows |
|------|-----------|---------------|
| Think | `ThinkContext.format_entity_context()` (`builders.py:240`) | Detail tracking tags (`[read:full]`/`[read:summary]`), source tag legend, entity-specific data legends from domain |
| Act | `build_act_entity_context()` (`act.py:753`) | Full entity data injected directly (not just refs) — reads `step_results` and `pending_artifacts` |
| Reply | `format_entity_context(ctx, mode="reply")` (`entity.py:181`) | Saved entities marked "ALREADY EXIST", generated marked "NOT YET SAVED" |

Note: The standalone `format_entity_context()` in `entity.py` defines additional modes (`"full"`, `"refs_and_labels"`, `"do_not_read"`) but only `"reply"` is actively called. Think and Act have their own specialized implementations.

---

## Detail Tracking

Some entity types benefit from tracking whether the LLM has seen a summary or the full record. This is controlled by `EntityDefinition.detail_tracking = True` (set per entity type by the domain).

### How It Works

When `translate_read_output()` processes a record, it calls `domain.detect_detail_level(entity_type, record)`:
- Returns `"full"` or `"summary"` based on the record's field set
- Returns `None` if the entity type doesn't support detail tracking

The result is stored in `ref_detail_tracking[ref]`:
```python
{"level": "full", "full_turn": 3}   # Full record read on turn 3
{"level": "summary"}                 # Only summary columns returned
```

### How Think Uses It

The `ThinkContext.format_entity_context()` method renders detail tracking as action tags:

```
- `recipe_1`: Butter Chicken (recipe) [read:full] T3
- `recipe_2`: Lemon Pasta (recipe) [read:summary] T2
```

Think sees `[read:summary]` and knows it should plan a full read before using that entity's detailed fields. This prevents redundant reads — Think won't plan "read recipe_1" if it already has `[read:full]`.

---

## FK Lazy Registration

When reading entities with foreign key fields (e.g., a `meal_plan` with `recipe_id`), the referenced entity might not be in the registry yet. Without handling this, raw UUIDs would leak to the LLM.

### The Flow

Inside `translate_read_output()`, for each FK field in the record:

1. **Already known** — The FK UUID is in `uuid_to_ref`. Use the existing ref. Also inject a label if available: `_recipe_id_label: "Butter Chicken"`.

2. **Unknown** — Lazy-register: assign a new ref immediately, set `ref_actions = "linked"`, and queue for name enrichment.

The enrichment queue (`_lazy_enrich_queue`) stores `{ref: (table, name_column)}`. After the CRUD operation completes, `_enrich_lazy_registrations()` in `crud.py` batch-fetches the actual names:

```
1. registry.get_lazy_enrich_queue()     → {recipe_5: ("recipes", "name", uuid)}
2. Batch SELECT name FROM recipes WHERE id IN (uuid1, uuid2, ...)
3. registry.apply_enrichment({"recipe_5": "Butter Chicken"})
4. Queue cleared
```

After enrichment, `_add_enriched_labels()` injects labels into the CRUD result:
```json
{"recipe_id": "recipe_5", "_recipe_id_label": "Butter Chicken"}
```

Which FK fields exist for each entity is defined by `EntityDefinition.fk_fields`. The enrichment table/column mapping comes from `domain.get_fk_enrich_map()`.

---

## Pending Artifacts

Generated content follows a "generate now, save later" pattern. The full artifact content lives in `pending_artifacts` until explicitly saved.

### Lifecycle

```
Turn N:   User says "suggest a recipe"
          → Act generate step → LLM produces recipe JSON
          → register_generated() stores content in pending_artifacts
          → gen_recipe_1 assigned, content = {name: "Butter Chicken", ...}
          → Reply shows the recipe to the user

Turn N+1: User says "save it" (or "change the protein to tofu" then "save it")
          → Act write step → CRUD db_create with gen_recipe_1 data
          → register_created() promotes: gen_recipe_1 now points to real UUID
          → Content retained in pending_artifacts for linked records
          → Summarize calls clear_turn_promoted_artifacts() at turn end
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `get_entity_data(ref)` | Unified access — returns `pending_artifacts[ref]` or `None` |
| `update_entity_data(ref, content)` | Modify a generated artifact (e.g., user feedback: "add feta") |
| `get_all_pending_artifacts()` | All artifacts including promoted (for Act prompt context) |
| `get_truly_pending_artifacts()` | Only unsaved artifacts (action != "created") |
| `get_just_promoted_artifacts()` | Artifacts saved this turn (for "Just Saved" prompt section) |
| `clear_turn_promoted_artifacts()` | Cleanup at turn end (called by Summarize) |
| `clear_pending_artifact(ref)` | Explicit clear after all linked records saved |

### Read Rerouting

When the LLM asks to read `gen_recipe_1`, the CRUD layer detects the `__pending__` UUID placeholder via `_try_reroute_pending_read()` and returns the in-memory data from `pending_artifacts` — no database query needed.

---

## Context Builders

Three builder functions assemble node-specific context from the three layers. Each returns a typed dataclass with a `format()` method.

### UnderstandContext (`context/builders.py:55`)

Built by `build_understand_context(state)`. Provides:

- **Current message** — The user's latest input, displayed prominently
- **Recent conversation** — Last 5 turns with entity annotations per turn (e.g., "Turn 3: recipe_1: Butter Chicken (read)")
- **Decision history** — Table of previous Understand decisions for curation continuity (Turn | Entity | Decision | Reason)
- **Entity registry table** — All registered entities with turn tracking columns (Ref | Type | Label | Last Action | Created | Last Ref)
- **Pending clarification** — If Think previously asked a question

The entity annotations per turn are computed by scanning the registry's `ref_turn_created` and `ref_turn_last_ref` dictionaries.

### ThinkContext (`context/builders.py:225`)

Built by `build_think_context(state)`. Provides:

- **Entity context with detail tracking** — Via `format_entity_context()`:
  - Generated Content section (unsaved artifacts with `[unsaved]` tag)
  - Active Entities section with `[read:full]` / `[read:summary]` tags + source tag legend
  - Long Term Memory section (Understand-retained entities with reasons)
  - Entity-specific data legends from `domain.get_entity_data_legend()`
- **Conversation history** — Via `format_conversation()` with depth=2 and pending state
- **Reasoning trace** — What happened last turn (Think decision, step outcomes, entity curation)
- **Current curation** — This turn's Understand decisions (retained/demoted)

### ReplyContext (`context/builders.py:412`)

Built by `build_reply_context(state)`. Provides:

- **Entity context in reply mode** — Saved entities marked "ALREADY EXIST. Don't offer to save", generated entities marked "NOT YET SAVED. Offer to save if appropriate"
- **Full pending artifact content** — JSON of generated artifacts so Reply can display them
- **Conversation** — With engagement summary
- **Reasoning** — Conversation phase and user-expressed preferences
- **Execution outcome** — Brief summary of what was accomplished (e.g., "Find Indian recipes: 5 items; Generate weekly plan: completed")

### Act's Entity Context (lives in `graph/nodes/act.py`)

`build_act_entity_context()` lives in act.py because it needs direct access to `SessionIdRegistry` methods and complex `step_results` parsing. It injects full entity data (not just refs) directly into the Act prompt.

---

## Conversation Memory

### ConversationContext TypedDict (`graph/state.py:568`)

The conversation is stored as a TypedDict in `AlfredState.conversation`:

```python
class ConversationContext(TypedDict, total=False):
    engagement_summary: str       # High-level session theme
    recent_turns: list[dict]      # Last N turns (full text)
    history_summary: str          # Compressed older turns
    step_summaries: list[dict]    # Compressed older step results
    content_archive: dict          # Generated content persisted across turns
    active_entities: dict          # EntityRefs for anaphoric resolution
    all_entities: dict             # All entities ever seen
    pending_clarification: dict    # Think's question awaiting response
    turn_summaries: list[dict]    # Last 2 TurnExecutionSummary (Layer 3)
    reasoning_summary: str        # Compressed older reasoning
```

### Turn Compression

The system uses token-budget-aware compression with configurable thresholds:

| Constant | Value | Purpose |
|----------|-------|---------|
| `FULL_DETAIL_TURNS` | 3 | Last 3 turns kept in full text |
| `FULL_DETAIL_STEPS` | 3 | Last 3 step results kept in full data |
| `ROUTER_CONTEXT_THRESHOLD` | 8,000 tokens | Budget for Router/Think condensed context |
| `ACT_CONTEXT_THRESHOLD` | 25,000 tokens | Budget for Act full context |

These are defined in `graph/state.py:27-34`.

### Assistant Message Summarization

Long assistant messages are compressed for conversation context via `_summarize_assistant_message()` (`memory/conversation.py:50`). Three patterns:

1. **Generated content detection** — Uses `domain.get_generated_content_markers()` to detect domain-specific content. If 3+ markers match, summarizes as "Generated {label}(s): Name1, Name2. [Content archived]"

2. **Item list detection** — If 5+ list markers (`\n- ` or `\n* `), summarizes as "{intro} ({count} items: item1, item2, item3 +N more)"

3. **Default truncation** — First 400 chars + "... [content continues in step results]"

### Context Formatting Functions

Two main formatting functions serve different nodes:

**`format_condensed_context()`** — For Router and Think. Token-budgeted. Priority order:
1. Engagement summary
2. Active entities (filtered to relevant types via `domain.get_relevant_entity_types()`)
3. Last 1-2 turns (with assistant summaries)
4. History summary (if space remains)

**`format_full_context()`** — For Act. Larger budget (25K tokens). Includes:
1. Engagement summary
2. Recent conversation turns (last 3, full user messages, summarized assistant messages)
3. History summary
4. Older step summaries (compressed)
5. Background entities (at end — step results are the primary data source)

---

## Layer 2: Conversation History (Context API)

The `context/conversation.py` module provides a structured view of conversation history:

```python
@dataclass
class ConversationHistory:
    recent_turns: list[ConversationTurn]  # Full detail
    history_summary: str                   # Compressed older turns
    engagement_summary: str                # Session theme
    pending: PendingState | None           # Awaiting user response
    current_turn: int
```

`get_conversation_history(conversation_dict)` builds this from the raw `ConversationContext` dict. `format_conversation(history, depth, include_pending)` renders it for prompt injection.

---

## Layer 3: Reasoning Trace

The reasoning trace captures execution decisions and outcomes. It's built by the Summarize node at the end of each turn.

### TurnExecutionSummary (`graph/state.py:538`)

A Pydantic model capturing what happened in one turn:

```python
class TurnExecutionSummary(BaseModel):
    turn_num: int
    think_decision: str      # "plan_direct" | "propose" | "clarify"
    think_goal: str          # "Find vegetarian recipes"
    steps: list[StepExecutionSummary]   # What steps ran and their outcomes
    entity_curation: CurationSummary    # What Understand retained/demoted
    conversation_phase: str  # "exploring" | "narrowing" | "confirming" | "executing"
    user_expressed: str      # "wants variety" | "prefers quick meals"
    blocked_reason: str | None
```

### Storage & Compression

- Last 2 `TurnExecutionSummary` instances are stored as dicts in `conversation["turn_summaries"]`
- Older summaries get compressed into `conversation["reasoning_summary"]` (a single string)

### ReasoningTrace Dataclass (`context/reasoning.py:70`)

The Context API wraps this in a structured dataclass:

```python
@dataclass
class ReasoningTrace:
    recent_summaries: list[TurnSummary]  # Last 2 turns
    reasoning_summary: str               # Compressed older reasoning
```

### Formatting by Node

`format_reasoning(trace, node)` renders different views:

- **Think:** Full detail on last 2 turns — decision, phase, user expressed, step outcomes, curation decisions
- **Reply:** Last turn only — phase, user expressed, accomplished outcomes (one-liner)

---

## Serialization

The registry serializes to/from dict for storage in `AlfredState.id_registry`:

**`to_dict()`** — Serializes all fields except internal queues (`_lazy_enrich_queue`, `_last_snapshot_refs`). These are transient and rebuilt each turn.

**`from_dict(data)`** — Class method that reconstructs a registry from a dict. Uses `.get()` with defaults for backwards compatibility when new fields are added.

### What Persists Across Turns

| Data | Persists | How |
|------|----------|-----|
| UUID↔ref mappings | Yes | `ref_to_uuid`, `uuid_to_ref` in serialized dict |
| Counters | Yes | `counters`, `gen_counters` |
| Pending artifacts | Yes | Full content in `pending_artifacts` |
| Entity metadata | Yes | `ref_actions`, `ref_labels`, `ref_types` |
| Temporal tracking | Yes | `ref_turn_created`, `ref_turn_last_ref`, etc. |
| Active reasons | Yes | `ref_active_reason` (Understand curation) |
| Detail tracking | Yes | `ref_detail_tracking` |
| Enrichment queue | No | Rebuilt each turn from FK processing |
| Frontend snapshot | No | Internal diff tracking |

---

## DomainConfig Hooks

The registry delegates domain-specific decisions to `DomainConfig`:

| Hook | Called By | Purpose |
|------|-----------|---------|
| `entities` property | `_table_to_type()`, `_get_fk_fields()`, nested relation handling | Entity type definitions, FK field lists, nested relations |
| `table_to_type` property | `_table_to_type()` | Table name → entity type mapping (e.g., "recipes" → "recipe") |
| `compute_entity_label(record, entity_type, ref)` | `translate_read_output()` | Domain-specific label computation (e.g., meal_plan: "Mon Dinner" from date + meal_type) |
| `detect_detail_level(entity_type, record)` | `translate_read_output()` | Determines "full" vs "summary" from record shape |
| `get_fk_enrich_map()` | `translate_payload()`, `_fk_field_to_enrich_info()` | Maps FK fields to (target_table, name_column) for enrichment |
| `get_entity_data_legend(entity_type)` | `ThinkContext.format_entity_context()` | Entity-specific prompt text explaining data tags |
| `get_generated_content_markers()` | `_looks_like_generated_content()` | Domain-specific markers for content detection in summarization |
| `get_relevant_entity_types()` | `format_condensed_context()`, `format_full_context()` | Which entity types to show in condensed context |

---

## Key Files

| File | Role | Lines |
|------|------|-------|
| `src/alfred/core/id_registry.py` | SessionIdRegistry — UUID↔ref mapping, entity lifecycle, serialization | 1167 |
| `src/alfred/context/entity.py` | Layer 1 — EntitySnapshot, EntityContext, tier classification | 263 |
| `src/alfred/context/conversation.py` | Layer 2 — ConversationHistory, formatting | 164 |
| `src/alfred/context/reasoning.py` | Layer 3 — ReasoningTrace, TurnSummary, formatting | 257 |
| `src/alfred/context/builders.py` | Node-specific context builders (Understand, Think, Reply) | 603 |
| `src/alfred/memory/conversation.py` | Turn management, entity extraction, context formatting, summarization | 749 |
| `src/alfred/graph/state.py` | AlfredState TypedDict, ConversationContext, EntityRef, TurnExecutionSummary | 714 |
| `src/alfred/domain/base.py` | DomainConfig entity hooks (compute_entity_label, detect_detail_level, etc.) | 1135 total |
