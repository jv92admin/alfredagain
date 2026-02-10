# Pipeline Stages

How a user message flows through Alfred's LangGraph pipeline — what each node does, what it reads and writes, and how routing decisions connect them.

---

## Pipeline Overview

```
START
  │
  ├─ Pre-processing (workflow.py)
  │  • _process_ui_changes(): register UI CRUD in id_registry
  │  • _resolve_mentions(): resolve @[Label](type:uuid) → refs + fetch data
  │
  ▼
UNDERSTAND  ──┬── needs_clarification ──→ REPLY → SUMMARIZE → END
              │
              ├── quick_mode ──→ ACT QUICK → REPLY → SUMMARIZE → END
              │
              └── (default) ──→ THINK ──┬── propose/clarify ──→ REPLY → SUMMARIZE → END
                                        │
                                        └── plan_direct ──→ ACT ⟲ → REPLY → SUMMARIZE → END
                                                           (loop)
```

Six nodes. Three entry paths from Understand. One loop (Act). Every path ends with Reply → Summarize.

**Router** exists in code (`graph/nodes/router.py`, 80 lines) but is currently bypassed — `create_alfred_graph()` sets `understand` as the entry point directly. Router will be re-enabled for multi-agent support.

---

## AlfredState

`AlfredState` is a `TypedDict` at `state.py:624`. Every node reads from and writes to this shared state. LangGraph merges each node's return dict into the state automatically.

### Key Fields by Category

**Input (set by workflow before graph starts):**

| Field | Type | Purpose |
|-------|------|---------|
| `user_message` | `str` | Raw user input |
| `user_id` | `str` | For CRUD user scoping |
| `conversation_id` | `str \| None` | Session identifier |
| `mode_context` | `dict` | Serialized `ModeContext` |
| `current_turn` | `int` | Turn counter (incremented each call) |
| `id_registry` | `dict \| None` | Serialized `SessionIdRegistry` from prior turn |
| `conversation` | `ConversationContext` | Full conversation state from prior turn |
| `content_archive` | `dict` | Generated content persisted across turns |

**Node outputs:**

| Field | Set By | Read By |
|-------|--------|---------|
| `understand_output: UnderstandOutput` | Understand | Think, Act, Reply |
| `think_output: ThinkOutput` | Think | Act, Reply, Summarize |
| `pending_action: ActAction \| None` | Act | Act (routing), Reply |
| `final_response: str \| None` | Reply | Workflow (returned to caller) |

**Act loop state:**

| Field | Type | Purpose |
|-------|------|---------|
| `current_step_index` | `int` | Which step Act is executing |
| `step_results` | `dict[int, Any]` | Cached results by step index |
| `step_metadata` | `dict[int, dict]` | Per-step: step_type, subdomain, artifacts |
| `current_step_tool_results` | `list` | Tool results within current step (multi-tool pattern) |
| `current_batch_manifest` | `dict \| None` | `BatchManifest` for multi-item operations |
| `schema_requests` | `int` | Counter for `request_schema` safety (max 2) |
| `prev_step_note` | `str \| None` | Note from previous step for context continuity |

### Context Token Thresholds (`state.py:27-34`)

| Constant | Value | Used By |
|----------|-------|---------|
| `ROUTER_CONTEXT_THRESHOLD` | 8,000 tokens | Router, Think |
| `ACT_CONTEXT_THRESHOLD` | 25,000 tokens | Act |
| `FULL_DETAIL_TURNS` | 3 | Conversation compression |
| `FULL_DETAIL_STEPS` | 3 | Step result truncation in Act |

---

## Understand

**File:** `graph/nodes/understand.py` (203 lines)
**Function:** `understand_node()`
**LLM call:** Yes — structured output → `UnderstandOutput`

Understand is Alfred's **memory manager**. It does not plan steps or rewrite messages. It has three responsibilities:

### 1. Entity Curation

Decides which entities stay active beyond the automatic 2-turn window:

- **Retain** — keep an older entity active with a reason (e.g., "User's ongoing meal plan goal")
- **Demote** — remove from active set (still in registry, just not in prompt context)
- **Drop** — remove entirely (user said "forget that")
- **Clear all** — reset everything ("start over")

Curation decisions are stored in `understand_output.entity_curation` (`EntityCurationDecision`, `state.py:165`) and applied by Understand immediately (`understand.py:146-195`):
- `retain_active` → calls `registry.set_active_reason(ref, reason)` — keeps entity beyond 2-turn window
- `demote` → calls `registry.clear_active_reason(ref)` — removes from active set
- `clear_all` → calls `registry.remove_ref(ref)` on all tracked refs

Summarize only **records** the curation decisions in `TurnExecutionSummary.entity_curation` (as `CurationSummary`) — it does not apply them.

### 2. Quick Mode Detection

For simple single-domain reads ("what's in my pantry?"), Understand sets:
- `quick_mode: True`
- `quick_intent: "Show user their inventory items"`
- `quick_subdomain: "inventory"`

This triggers the fast path: Understand → Act Quick → Reply (skipping Think entirely).

### 3. Reference Resolution

Resolves user references to entity refs:
- `referenced_entities: ["recipe_1", "inv_3"]` — simple refs the user is talking about
- `entity_mentions` — structured `EntityMention` objects (`state.py:116`) with resolution confidence
- `needs_disambiguation: True` — when "that recipe" could mean multiple entities

### Output: `UnderstandOutput` (`state.py:194`)

| Field | Purpose |
|-------|---------|
| `referenced_entities` | Refs user is referring to (touched in registry) |
| `entity_curation` | Retain/demote/drop decisions with reasons |
| `quick_mode` / `quick_intent` / `quick_subdomain` | Fast-path detection |
| `needs_clarification` / `clarification_questions` | Routes to Reply for questions |
| `needs_disambiguation` / `disambiguation_options` | Ambiguous entity references |
| `constraint_snapshot` | New constraints ("no dairy", "use cod") |

---

## Router

**File:** `graph/nodes/router.py` (80 lines)
**Function:** `router_node()`
**Status:** Currently **bypassed** — not wired in `create_alfred_graph()`

Router was designed for multi-agent dispatch (different agents for different tasks). In the current single-agent architecture, `_create_default_router_output()` in `workflow.py` provides a static `RouterOutput` with the domain's default agent.

`RouterOutput` (`state.py:64`):
- `agent: str` — domain-specific agent name
- `goal: str` — natural language
- `complexity: "low" | "medium" | "high"`

Router will be re-enabled when multi-agent support is needed. It uses `format_condensed_context()` (8K token budget).

---

## Think

**File:** `graph/nodes/think.py` (311 lines)
**Function:** `think_node()`
**LLM call:** Yes — structured output → `ThinkOutput`

Think is the **planner**. It receives the understood intent and entity context and produces an execution plan.

### Decision Modes

Think returns one of three decisions (`ThinkOutput.decision`):

| Decision | When | Route |
|----------|------|-------|
| `plan_direct` | Clear intent, executable | Steps sent to Act |
| `propose` | Complex or exploratory request | Proposal shown to user for confirmation |
| `clarify` | Missing information (rare — Understand handles most) | Questions sent to user |

### ThinkStep (`state.py:79`)

Each step in the plan:

```python
class ThinkStep(BaseModel):
    description: str                                            # "Read user's inventory"
    step_type: Literal["read", "analyze", "generate", "write"]
    subdomain: str                                              # "inventory", "recipes"
    group: int = 0                                              # Parallelization group
```

**Step types and their LLM complexity mapping** (`state.py:96`):

| Step Type | Purpose | Complexity |
|-----------|---------|-----------|
| `read` | Fetch data via `db_read` | low |
| `analyze` | Reason over data (no CRUD) | medium |
| `generate` | Create new content (no CRUD) | high |
| `write` | Persist via `db_create`/`db_update`/`db_delete` | low |

**Group-based parallelization:** Steps with the same `group` number have no dependencies and can theoretically run concurrently. Groups execute in order: 0 → 1 → 2.

### Think Context

Think receives:
- Conversation history via `format_condensed_context()` (8K token budget)
- Entity context via `ThinkContext.format_entity_context()` (`builders.py:240`) — includes detail tracking tags like `[read:summary]`/`[read:full]`
- User profile and domain snapshot via `domain.get_user_profile()` and `domain.get_domain_snapshot()`
- Reasoning trace from prior turns via `format_reasoning(trace, "think")` (`reasoning.py:166`)
- Mode configuration — QUICK limits to 2 steps, CREATE requires proposal

### ThinkOutput (`state.py:245`)

| Field | Purpose |
|-------|---------|
| `goal` | Natural language goal description |
| `steps` | `list[ThinkStep]` — the execution plan |
| `decision` | `"plan_direct"` / `"propose"` / `"clarify"` |
| `proposal_message` | For `propose` — what to show user |
| `clarification_questions` | For `clarify` — questions to ask |

Has a `model_validator` (`state.py:273`) that auto-corrects `plan_direct` with empty steps + `proposal_message` to `propose`.

---

## Act

**File:** `graph/nodes/act.py` (1913 lines)
**Function:** `act_node()` at line 980
**LLM call:** Yes, per step iteration — structured output → `ActDecision`

Act is the **execution engine**. It executes Think's plan step-by-step, making CRUD calls and managing entity lifecycle.

### Step Execution Loop

For each step:
1. Build context: previous step results, current step's tool results, entity context, conversation, schema
2. Call LLM → `ActDecision` (what action to take)
3. If `tool_call` → execute CRUD via `execute_crud()`, accumulate results, **loop back** (step stays current)
4. If `step_complete` → cache result, advance `current_step_index`, clear tool results
5. If all steps done → `pending_action = None`, exit to Reply

**Key invariant:** Act does NOT advance the step index on `tool_call`. The LLM must explicitly emit `step_complete` to move forward. This enables multi-tool patterns within a single step (e.g., create recipe → create each recipe_ingredient → step_complete).

### ActDecision (`act.py:214`)

The LLM's decision model. 8 action types:

| Action | Purpose | What Act Does |
|--------|---------|---------------|
| `tool_call` | Execute a CRUD operation | Calls `execute_crud()`, appends to `current_step_tool_results`, loops back |
| `step_complete` | Step is done | Caches result in `step_results`, increments `current_step_index`, clears tool results |
| `request_schema` | Need table schema | Fetches schema, loops back (max 2 per step) |
| `retrieve_step` | Need older step data | Injects data into `current_step_tool_results`, loops back |
| `retrieve_archive` | Need cross-turn content | Fetches from `content_archive`, injects into tool results, loops back |
| `ask_user` | Need clarification | Exits to Reply with question |
| `blocked` | Can't proceed | Exits to Reply with structured error (reason_code, details, suggested_next) |
| `fail` | Unrecoverable error | Exits to Reply with error message |

### ActAction Union (`state.py:469`)

Each action maps to a typed Pydantic model:

```
ActAction = ToolCallAction | StepCompleteAction | RequestSchemaAction
          | RetrieveStepAction | AskUserAction | BlockedAction | FailAction
```

### Circuit Breakers

Two safety mechanisms prevent infinite loops:

1. **Max tool calls per step** (`MAX_TOOL_CALLS_PER_STEP = 3`, `act.py:977`) — forces `step_complete` after 3 tool calls in one step
2. **Duplicate empty query detection** (`act.py:1031`) — if the same table returns empty results twice in one step, forces completion

### Entity Context in Act

Act builds its own entity context via `build_act_entity_context()` (`act.py:753`). This is distinct from Think's and Reply's entity formatters. It renders five sections:

| Section | Content |
|---------|---------|
| **Needs Creating** | Pending artifacts (gen_* refs) that need their main record saved |
| **Just Saved This Turn** | Recently promoted artifacts with real UUIDs |
| **Active Entities** | Full data from `step_results` and `turn_step_results` (last 2 turns) |
| **Recent Context** | Refs from last 2 turns without loaded data (need `db_read` if data needed) |
| **Long Term Memory** | Retained refs beyond 2-turn window with retention reasons |

### Artifact Lifecycle in Act

When Act completes a `generate` step (`act.py:1596`):
1. Extracts artifacts from `decision.data`
2. Registers each via `session_registry.register_generated()` → gets `gen_*` ref
3. Stores full content in `pending_artifacts` for later write steps
4. Archives data in `content_archive` for cross-turn retrieval

When Act completes a `write` step (`act.py:1626`):
1. CRUD layer calls `session_registry.register_created()` which promotes `gen_*` → real ref
2. Related `content_archive` keys are cleared via `domain.get_archive_keys_for_subdomain()`
3. Pending artifact data is preserved per-ref (only the saved ref is cleared, not all)

### Batch Tracking

For multi-item operations (e.g., saving 3 generated recipes), `BatchManifest` (`state.py:318`) tracks per-item status:

```python
class BatchItem(BaseModel):
    ref: str          # "gen_recipe_1"
    label: str        # "Butter Chicken"
    status: str       # "pending" | "completed" | "failed"
    result_id: str    # DB ref when created
    error: str        # Error if failed
```

Act **cannot** call `step_complete` while batch items are still pending (`act.py:1476`) — the batch must be fully processed first.

### Step Result Formatting

Previous step results are formatted with a recency window (`_format_step_results()`, `act.py:384`):
- Last `FULL_DETAIL_STEPS` (3) steps → full data with table-aware formatting
- Older steps → summarized (count + name preview)
- **Exception:** Generate step artifacts are always shown in full for subsequent write steps

Current step's tool results are formatted by `_format_current_step_results()` (`act.py:654`) — shows actual DB data from each tool call with IDs, counts, and semantic meaning.

---

## Act Quick

**File:** `graph/nodes/act.py`
**Function:** `act_quick_node()` at line 1747
**LLM call:** Yes — structured output → `ActQuickDecision`

Simplified single-step execution path for quick mode. Key differences from full Act:

| Aspect | Act | Act Quick |
|--------|-----|-----------|
| Steps | Multi-step from Think | Single step |
| Loop | Iterates with step_complete | No loop — one LLM call, one CRUD call |
| Decision model | `ActDecision` (8 actions) | `ActQuickDecision` (`tool_call` only) |
| Complexity | Varies by step type | Always `"low"` |
| Source of intent | `think_output.steps[i]` | `understand_output.quick_intent` |
| Routing after | `should_continue_act()` | Always → Reply |

Act Quick uses the **same** prompt builder (`build_act_user_prompt`), entity context builder (`build_act_entity_context`), and CRUD executor (`execute_crud`) as full Act. The simplification is in the decision model and absence of looping.

`should_continue_act_quick()` (`act.py:1906`) always returns `"reply"`.

---

## Reply

**File:** `graph/nodes/reply.py` (1224 lines)
**Function:** `reply_node()` at line 407
**LLM call:** Conditional — many paths skip the LLM entirely

Reply generates the final user-facing response. It handles multiple response modes with a priority cascade:

### Response Mode Priority

Reply checks conditions in this order (first match wins):

| Priority | Condition | Action | LLM? |
|----------|-----------|--------|------|
| 1 | `understand_output.needs_clarification` | Format clarification questions | No |
| 2 | `quick_result` exists | Deterministic formatter or light LLM | Maybe |
| 3 | `think_output.decision == "propose"` | Format proposal for confirmation | No |
| 4 | `think_output.decision == "clarify"` | Format clarification questions | No |
| 5 | `error` exists | Error message | No |
| 6 | `AskUserAction` | Pass through question | No |
| 7 | `FailAction` | Pass through user_message | No |
| 8 | `BlockedAction` | Generate response with error context | Yes |
| 9 | No step_results + think_output | Empty execution guard (honest error) | No |
| 10 | Normal completion | Full response from execution summary | Yes |

### Quick Mode Response (`reply.py:313`)

`_format_quick_response()` tries deterministic formatters first:
1. Empty result → `domain.get_empty_response(subdomain)`
2. List result with domain formatter → `domain.get_subdomain_formatters()[subdomain](result)`
3. Write confirmation → `domain.get_quick_write_confirmation()`
4. No match → `_quick_llm_response()` (light LLM call with action-mismatch detection)

### Normal Completion (`reply.py:614-710`)

For full pipeline responses, Reply builds a user prompt with:
- Original request and Think's goal
- Entity context (saved vs generated distinction) via `build_reply_context()` + `format_entity_context(mode="reply")`
- Execution summary (`_format_execution_summary()`, `reply.py:713`) — step-by-step outcomes with generated vs saved tracking
- Conversation context via `format_condensed_context()`
- Conversation flow section — turn counter, phase, continuity guidance
- Action mismatch warning — detects when user wanted an update but only a read happened

### Execution Summary (`_format_execution_summary()`, `reply.py:713`)

Structures the handoff from Act to Reply:
- Batch progress status ("3 of 3 saved")
- Representational status (generated vs saved counts)
- Plan overview (steps planned vs completed)
- Primary output promotion (last analyze/generate step highlighted)
- Per-step outcomes with formatted records
- Generated vs saved mismatch warnings
- Single next-step suggestion

### Output

`ReplyOutput` (`reply.py:59`) — just `response: str`. Stored as `state["final_response"]`.

**System prompt:** `domain.get_system_prompt()` + reply instructions from either `domain.get_reply_prompt_content()` or core template `reply.md`.

---

## Summarize

**File:** `graph/nodes/summarize.py` (1143 lines)
**Function:** `summarize_node()`
**LLM calls:** Up to 3 per turn

Summarize is the **conversation historian**. It runs after Reply on every path and persists everything needed for the next turn.

### What Summarize Produces

**1. TurnExecutionSummary** (`state.py:538`) — Layer 3 reasoning trace:

| Field | Content |
|-------|---------|
| `turn_num` | Current turn number |
| `think_decision` / `think_goal` | What Think planned |
| `steps: list[StepExecutionSummary]` | What each step did (type, subdomain, outcome, entities) |
| `entity_curation: CurationSummary` | What Understand retained/demoted |
| `conversation_phase` | LLM-classified: "exploring" / "narrowing" / "confirming" / "executing" |
| `user_expressed` | LLM-classified: "wants variety" / "prefers quick meals" |
| `blocked_reason` | Set when turn was blocked before completion |

**2. Conversation context updates:**
- Add current turn to `recent_turns`
- Compress oldest turn beyond `FULL_DETAIL_TURNS` (3) → append to `history_summary`
- Compress oldest turn summary beyond 2 entries → append to `reasoning_summary`
- LLM-generate `engagement_summary` (high-level session description)

**3. Registry persistence:** Serializes `id_registry` into `conversation["id_registry"]` for cross-turn access.

**4. Step result serialization** (`_serialize_step_results()`):
- Extracts entity refs and tables from step results
- Stores in `conversation["turn_step_results"]` keyed by turn number
- Enables Act's entity context builder to show full entity data without re-reading

### LLM Calls

| Call | Purpose | When |
|------|---------|------|
| Assistant summary | Compress assistant response to ~100 words | Every turn |
| Turn compression | Compress oldest full turn to summary | When `recent_turns` exceeds `FULL_DETAIL_TURNS` |
| Engagement summary | Update high-level session description | Every turn |

### Entity Curation Recording

Summarize **records** Understand's curation decisions in the `TurnExecutionSummary.entity_curation` field (`CurationSummary` at `summarize.py:968-973`). The actual application to the registry happens in Understand (see Understand section above). Summarize preserves the decisions for future Think/Reply context.

---

## Mode System

**File:** `core/modes.py` (132 lines)

### Core Modes

`Mode` enum:

| Mode | `max_steps` | `skip_think` | `proposal_required` | Description |
|------|------------|-------------|---------------------|-------------|
| `QUICK` | 2 | Yes | No | Simple reads, skip Think |
| `PLAN` | 8 | No | Yes | Default multi-step execution |
| `CREATE` | 4 | No | No | Creative tasks, direct execution |

`MODE_CONFIG` stores per-mode settings: `max_steps`, `skip_think`, `proposal_required`, `verbosity`, `max_tool_calls_per_step`.

### ModeContext

Serializable context passed through the graph:

```python
@dataclass
class ModeContext:
    selected_mode: Mode
    override_params: dict                  # Per-turn overrides
    active_bypass_mode: str | None = None  # Domain bypass mode name
```

### Domain Bypass Modes

Domains register lightweight modes that **skip the graph entirely** via `DomainConfig.bypass_modes`. Kitchen registers `cook` and `brainstorm` modes.

Bypass mode flow:
1. Workflow detects `mode` matches a bypass mode name in `domain.bypass_modes`
2. Calls the bypass mode function directly (its own LLM calls, no graph nodes)
3. Returns response + updated conversation

Bypass modes are defined in `domain/base.py` as a property returning `dict[str, Callable]`.

---

## Routing Logic

### Graph Construction

`create_alfred_graph()` (`workflow.py:427`):

```python
graph.set_entry_point("understand")

# Understand → conditional
graph.add_conditional_edges("understand", route_after_understand, {
    "think": "think",
    "act_quick": "act_quick",
    "reply": "reply",
})

# Think → conditional
graph.add_conditional_edges("think", route_after_think, {
    "act": "act",
    "reply": "reply",
})

# Act → conditional (the loop)
graph.add_conditional_edges("act", should_continue_act, {
    "continue": "act",
    "reply": "reply",
    "ask_user": "reply",
    "fail": "reply",
})

# Act Quick → Reply (unconditional)
graph.add_edge("act_quick", "reply")

# Reply → Summarize → END (unconditional)
graph.add_edge("reply", "summarize")
graph.add_edge("summarize", END)
```

### Routing Functions

**`route_after_understand()`** (`workflow.py:374`):

| Condition | Route | Why |
|-----------|-------|-----|
| `understand_output.needs_clarification` | `"reply"` | Ask clarifying questions |
| `understand_output.quick_mode` | `"act_quick"` | Fast path, skip Think |
| Default | `"think"` | Normal planning path |

**`route_after_think()`** (`workflow.py:400`):

| Condition | Route | Why |
|-----------|-------|-----|
| `decision == "plan_direct"` | `"act"` | Execute the plan |
| `decision == "propose"` or `"clarify"` | `"reply"` | Show proposal/questions to user |
| Default | `"act"` | Fallback |

**`should_continue_act()`** (`act.py:1667`):

| Condition | Route | Why |
|-----------|-------|-----|
| `pending_action is None` | `"reply"` | All steps done |
| `ToolCallAction` | `"continue"` | Tool executed, step not done — loop back |
| `StepCompleteAction` + more steps | `"continue"` | Step done, advance to next |
| `StepCompleteAction` + no more steps | `"reply"` | Last step done |
| `RequestSchemaAction` | `"continue"` | Schema fetched, retry step |
| `RetrieveStepAction` | `"continue"` | Data retrieved, retry step |
| `AskUserAction` | `"ask_user"` | Need user input |
| `BlockedAction` | `"reply"` | Error, let Reply handle it |
| `FailAction` | `"fail"` | Unrecoverable |

---

## Streaming Events

`run_alfred_streaming()` (`workflow.py:672`) yields typed events as the graph executes:

| Event Type | When | Key Fields |
|------------|------|------------|
| `thinking` | Before graph starts | `message` |
| `think_complete` | After Think (plan_direct) | `goal`, `stepCount` |
| `plan` | After Think (plan_direct) | `goal`, `total_steps`, `steps[]` |
| `propose` | After Think (propose) | `goal`, `proposal_message` |
| `clarify` | After Think (clarify) | `goal`, `questions[]` |
| `step` | Act starts a new step | `step`, `total`, `description`, `step_type`, `group` |
| `step_complete` | Act finishes a step | `step`, `total`, `data`, `tool_calls` |
| `working` | Act loops within same step | `step` |
| `active_context` | After entity changes | `data` (entity cards for frontend) |
| `done` | After Reply | `response`, `conversation`, `active_context` |
| `context_updated` | After Summarize | `conversation` (final persisted state) |

**`done` yields before `context_updated`** — the response appears to the user immediately while Summarize persists state in the background.

---

## Pre-Processing

`run_alfred_streaming()` and `run_alfred()` perform two pre-processing steps before the graph starts:

### UI Change Processing (`_process_ui_changes()`, `workflow.py:233`)

When the frontend sends CRUD changes (user edited/created/deleted entities via the UI):
1. Registers each change in `id_registry` via `register_from_ui()`
2. Injects fresh entity data into `turn_step_results` so Act sees updated values, not stale cache

### @-Mention Resolution (`_resolve_mentions()`, `workflow.py:300`)

Parses `@[Label](type:uuid)` patterns from the user message:
1. Registers the mentioned entity in `id_registry` via `register_from_ui()` with action `"mentioned:user"`
2. Fetches full entity data from the database via `db_read`
3. Injects into `turn_step_results` so Act has the data in context

Both run before `understand_node()` so every LLM node sees all entities from the start of the turn.

---

## Key Files

| File | Role | Lines |
|------|------|-------|
| `src/alfred/graph/workflow.py` | Graph construction, routing, entry points | 994 |
| `src/alfred/graph/state.py` | AlfredState, all Pydantic action/output models | 714 |
| `src/alfred/graph/nodes/understand.py` | Entity curation, quick mode detection | 203 |
| `src/alfred/graph/nodes/think.py` | Planning, step generation | 311 |
| `src/alfred/graph/nodes/act.py` | Step execution loop, CRUD orchestration | 1913 |
| `src/alfred/graph/nodes/reply.py` | Response generation, formatting | 1224 |
| `src/alfred/graph/nodes/summarize.py` | Turn persistence, conversation compression | 1143 |
| `src/alfred/graph/nodes/router.py` | Multi-agent routing (currently bypassed) | 80 |
| `src/alfred/core/modes.py` | Mode enum, ModeContext, MODE_CONFIG | 132 |
