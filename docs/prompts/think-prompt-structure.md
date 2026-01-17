# Think Prompt Structure

**Purpose:** Documents the Think node's prompt assembly — what sections exist, where they come from, and rules for turn windows.

**Related:** `src/alfred/graph/nodes/think.py`, `prompts/think.md`

---

## Overview

Think receives a **system prompt** (static template with placeholders) and a **user prompt** (dynamic, assembled per-turn).

```
┌─────────────────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT (prompts/think.md)                                    │
│ ─────────────────────────────────────────────────────────────────── │
│ Static template with XML placeholders:                              │
│   <session_context></session_context>                               │
│   <conversation_history></conversation_history>                     │
│   <immediate_task></immediate_task>                                 │
├─────────────────────────────────────────────────────────────────────┤
│ USER PROMPT (assembled in think.py)                                 │
│ ─────────────────────────────────────────────────────────────────── │
│ Fills the placeholders with dynamic content per turn                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## System Prompt Sections (`prompts/think.md`)

| Section | Purpose | Mutable? |
|---------|---------|----------|
| `<identity>` | Who Think is, outputs (`plan_direct`/`propose`/`clarify`), hard rules | No |
| `<precedence>` | Priority when instructions conflict | No |
| `<alfred_context>` | What Alfred enables, philosophy | No |
| `<understanding_users>` | How to synthesize context | No |
| `<system_structure>` | Subdomains, linked tables, step types, context types | No |
| `<conversation_management>` | Conversational patterns, phases, checkpoints | No |
| `<session_context>` | **PLACEHOLDER** — filled by user prompt | Yes (injected) |
| `<conversation_history>` | **PLACEHOLDER** — filled by user prompt | Yes (injected) |
| `<immediate_task>` | **PLACEHOLDER** — filled by user prompt | Yes (injected) |
| `<output_contract>` | Response format (JSON schema, examples) | No |

---

## User Prompt Sections (assembled in `think.py`)

### 1. `<session_context>` — Who the user is + what exists

**Contents (in order):**

| Component | Source | Function |
|-----------|--------|----------|
| User Profile | `get_cached_profile(user_id)` | `format_profile_for_prompt()` |
| Subdomain Guidance | `profile.subdomain_guidance` | `format_all_subdomain_guidance()` |
| Kitchen Dashboard | `get_cached_dashboard(user_id)` | `format_dashboard_for_prompt()` |
| Entity Context | `SessionIdRegistry` | `format_for_think_prompt()` |
| Reasoning Trace | `conversation["turn_summaries"]` | `format_reasoning(trace, node="think")` |
| Current Curation | `understand_output.entity_curation` | `format_curation_for_think()` |

**Turn windows:**

| Data | Window | Source |
|------|--------|--------|
| Entity refs | Last 2 turns (automatic) + retained (Understand) | `get_active_entities(turns_window=2)` |
| Turn summaries | Last 2 summaries | `conversation["turn_summaries"][-2:]` |
| Reasoning summary | Compressed older history | `conversation["reasoning_summary"]` |

### 2. `<conversation_history>` — What was said

**Contents (in order):**

| Component | Source | Function |
|-----------|--------|----------|
| Conversation context | `conversation` dict | `format_condensed_context()` |
| Pending clarification | `conversation["pending_clarification"]` | Inline formatting |

**Turn windows:**

| Data | Window | Notes |
|------|--------|-------|
| Recent turns | Last 3 full turns | `FULL_DETAIL_TURNS = 3` in summarize |
| Older turns | Compressed to narrative | `conversation["history_summary"]` |

### 3. `<immediate_task>` — What to do now

**Contents:**

```
**User said**: "{user_message}"{understand_section}

**Today**: {today} | **Mode**: {mode_name} (max {max_steps} steps)

{entity_counts_section}
```

| Component | Source |
|-----------|--------|
| `user_message` | `state["user_message"]` |
| `understand_section` | `understand_output.referenced_entities` |
| `today` | `date.today().isoformat()` |
| `mode_name`, `max_steps` | `mode_context.selected_mode` |
| `entity_counts_section` | Computed from `registry.ref_types` |

---

## Entity Context for Think

**Key principle:** Think sees **refs + labels only**, not full entity data.

### What Think sees:

```markdown
## Generated Content
User can save these or discard:
- `gen_recipe_1`: Thai Curry (recipe) [unsaved]

## Recent Context (last 2 turns)
**Known refs and labels only. Do NOT assume full record data is loaded for Act in this turn.**
- `recipe_1`: Butter Chicken (recipe) [read:summary]
- `recipe_3`: Cod Masala (recipe) [read:full]
- `inv_1`: eggs (inv) [read]

## Long Term Memory (retained from earlier)
- `gen_meal_plan_1`: Weekly Plan (meal) — *User's ongoing goal*
```

### Deterministic flags:

| Flag | Meaning | When set |
|------|---------|----------|
| `[read:summary]` | Recipe was read WITHOUT instructions | Default recipe read |
| `[read:full]` | Recipe was read WITH instructions | "with instructions" in step |
| `[unsaved]` | Generated but not persisted | `pending_artifacts` |
| `[created]` | Generated and saved | After `db_create` |

### Source function:

```python
# src/alfred/core/id_registry.py
SessionIdRegistry.format_for_think_prompt() -> str
```

---

## What Think Does NOT See

| Data | Reason |
|------|--------|
| Full entity content (metadata, ingredients, instructions) | Token savings, cognitive load |
| Step results from prior turns | Cleared when Think runs |
| UUIDs | Never exposed to LLMs |

---

## Output Contract

Think returns `ThinkOutput`:

```python
class ThinkOutput(BaseModel):
    decision: Literal["plan_direct", "propose", "clarify"]
    goal: str
    steps: list[ThinkStep] | None  # Only for plan_direct
    proposal_message: str | None   # Only for propose
    clarification_questions: list[str] | None  # Only for clarify
```

Each `ThinkStep`:

```python
class ThinkStep(BaseModel):
    description: str      # What to do (intent, not pseudo-query)
    step_type: str        # read | write | analyze | generate
    subdomain: str        # recipes | inventory | meal_plans | shopping | tasks | preferences
    group: int            # Parallelization group (same group = parallel)
```

---

## Subdomain Knowledge Sources

Think learns about subdomains from TWO sources:

| Source | What it provides | Where |
|--------|------------------|-------|
| **`prompts/think.md`** (`<system_structure>`) | Linked tables, step types, data relationships | Static in system prompt |
| **`profile.subdomain_guidance`** | User-specific preferences per domain | Dynamic in `<session_context>` |

**Note:** Think does NOT see `personas.py` or `schema.py` directly. Those files are for **Act**:
- `schema.py` → Database structure (tables, columns, CRUD examples)
- `personas.py` → Step-type-specific guidance (read/write/analyze/generate personas)

Think's subdomain knowledge is baked into `think.md` — it knows things like:
- "meal_plans has recipe_id FK but NOT ingredients"
- "To get ingredients for meals: read meal_plans → read recipes"

---

## Key Design Decisions

1. **Refs only for Think** — Full data goes to Act, not Think (reduces cognitive load)
2. **2-turn entity window** — Automatic, deterministic, no LLM involvement
3. **Understand curation** — Extends retention beyond 2 turns with reasons
4. **Recipe data levels** — Think knows if instructions were loaded (`[read:summary]` vs `[read:full]`)
5. **Mode-aware step limits** — QUICK: 2, COOK: 4, PLAN: 8, CREATE: 4
6. **Subdomain guidance split** — System-level in `think.md`, user-level in profile

---

## Files to Update Together

When changing Think's context:

| File | What to change |
|------|----------------|
| `prompts/think.md` | System prompt — subdomain structure, linked tables, step types |
| `src/alfred/graph/nodes/think.py` | User prompt assembly |
| `src/alfred/core/id_registry.py` | `format_for_think_prompt()` |
| `src/alfred/context/reasoning.py` | Reasoning trace formatting |

**NOT for Think** (these are for Act):

| File | Purpose |
|------|---------|
| `src/alfred/tools/schema.py` | DB structure, CRUD examples, SEMANTIC_NOTES |
| `src/alfred/prompts/personas.py` | Step-type personas (read/write/analyze/generate) |

---

*Last updated: 2026-01-17*
