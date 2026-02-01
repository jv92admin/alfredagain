# Modes & Endpoints Specification

**Date:** Jan 2026
**Purpose:** Document all Alfred conversation modes, their API contracts, SSE events, LLM configurations, and handoff mechanics. Reference for frontend integration.

---

## Mode Overview

```
POST /api/chat/stream
     |
     +-- mode="plan"        --> LangGraph pipeline (5-17 LLM calls)
     +-- mode="quick"       --> LangGraph pipeline (1-2 LLM calls)
     +-- mode="create"      --> LangGraph pipeline (2-4 LLM calls)
     +-- mode="cook"        --> Standalone runner (1 LLM call/turn)
     +-- mode="brainstorm"  --> Standalone runner (1 LLM call/turn)
```

| Mode | Graph? | LLM Calls/Turn | Latency Target | Use Case |
|------|--------|----------------|----------------|----------|
| Plan | Full pipeline | 5-17 | 2-3s to first token | Complex requests, CRUD, meal planning |
| Quick | Reduced pipeline | 1-2 | <1s to first token | Simple lookups, confirmations |
| Create | Reduced pipeline | 2-4 | 1-2s to first token | Recipe generation, content creation |
| Cook | **Bypasses graph** | 1 | <500ms to first token | Active cooking guidance |
| Brainstorm | **Bypasses graph** | 1 | <500ms to first token | Creative food exploration |

---

## API Contract

### Endpoint

```
POST /api/chat/stream
Authorization: Bearer <jwt>
Content-Type: application/json
```

### Request Body

```python
class CookSessionInit(BaseModel):
    recipe_id: str | None = None
    notes: str = ""

class ChatRequest(BaseModel):
    message: str
    log_prompts: bool = False
    mode: str = "plan"               # "quick" | "plan" | "create" | "cook" | "brainstorm"
    ui_changes: list[UIChange] | None = None
    cook_init: CookSessionInit | None = None   # Cook mode first turn only
    brainstorm_init: bool = False               # Brainstorm mode first turn only
```

### Mode-Specific Request Patterns

**Cook — First Turn (start session):**
```json
{
  "message": "",
  "mode": "cook",
  "cook_init": { "recipe_id": "uuid-here", "notes": "halving the recipe" }
}
```

**Cook — Chat Turn:**
```json
{
  "message": "Is the oil hot enough?",
  "mode": "cook"
}
```

**Cook — Exit:**
```json
{
  "message": "__cook_exit__",
  "mode": "cook"
}
```

**Brainstorm — First Turn:**
```json
{
  "message": "I want to riff on pasta ideas",
  "mode": "brainstorm",
  "brainstorm_init": true
}
```

**Brainstorm — Chat Turn:**
```json
{
  "message": "What about a carbonara with miso?",
  "mode": "brainstorm"
}
```

**Brainstorm — Exit:**
```json
{
  "message": "__brainstorm_exit__",
  "mode": "brainstorm"
}
```

---

## SSE Events

All modes share the same SSE endpoint. Event types differ by mode.

### Graph Modes (plan, quick, create)

| Event | Data | When |
|-------|------|------|
| `job_started` | `{ job_id }` | Immediately |
| `progress` | `{ type, node, step, ... }` | Per graph node |
| `context_updated` | `{ status: "ready" }` | After summarization |
| `done` | `{ response, log_dir, job_id }` | Final response |
| `error` | `{ error }` | On failure |
| `ping` | `""` | Keep-alive (30s timeout) |

### Cook & Brainstorm Modes

| Event | Data | When |
|-------|------|------|
| `job_started` | `{ job_id }` | Immediately |
| `chunk` | `{ content }` | Per streaming token |
| `handoff` | `{ summary, action, action_detail }` | On exit only |
| `done` | `{ response, log_dir, job_id }` | End of turn |
| `error` | `{ error }` | On failure |
| `ping` | `""` | Keep-alive |

### SSE Event Flow by Scenario

**Cook/Brainstorm chat turn:**
```
job_started → chunk → chunk → chunk → ... → done
```

**Cook/Brainstorm exit:**
```
job_started → handoff → done
```

**Cook/Brainstorm error (recoverable):**
```
job_started → error
```
User stays in mode. Can retry or exit.

---

## Handoff Mechanics

When a user exits Cook or Brainstorm mode, a single LLM call produces a structured result:

```python
class HandoffResult(BaseModel):
    summary: str        # 2-4 sentence narrative of what happened
    action: Literal["save", "update", "close"]
    action_detail: str  # What to save/update, or why closing
```

### Action Types

| Action | Meaning | Backend Behavior | Frontend Behavior |
|--------|---------|-----------------|-------------------|
| `save` | New content worth persisting | Summary injected into `recent_turns` | Show summary, confirm return to Plan |
| `update` | Modifications to existing content | Summary injected into `recent_turns` | Show summary, confirm return to Plan |
| `close` | Nothing worth persisting | No injection | Silently return to Plan |

**Backend behavior is identical for save and update.** The distinction is for frontend messaging only (e.g., "Save these ideas?" vs "Update your recipe notes?").

### Conversation State During Modes

Plan state is preserved throughout Cook/Brainstorm sessions:

```
conversation = {
    # Plan state (untouched during Cook/Brainstorm)
    "id_registry": { ... },
    "recent_turns": [ ... ],
    "turn_summaries": [ ... ],

    # Mode flag
    "active_mode": "cook" | "brainstorm" | "plan",

    # Cook-specific (present only during cook session)
    "cook_context": "# Recipe Name\n## Ingredients\n...",
    "cook_history": [{ role, content }, ...],
    "cook_recipe_name": "Spaghetti Carbonara",

    # Brainstorm-specific (present only during brainstorm session)
    "brainstorm_context": "# Kitchen Context\n...",
    "brainstorm_history": [{ role, content }, ...],
}
```

On exit, mode-specific fields are cleared and `active_mode` resets to `"plan"`.

---

## LLM Configuration

### Model Selection

All Cook/Brainstorm/Handoff calls use `complexity="low"` → `gpt-4.1-mini`.

| Node | Model | Temperature | Verbosity |
|------|-------|-------------|-----------|
| `cook` | gpt-4.1-mini | 0.4 | terse |
| `brainstorm` | gpt-4.1-mini | 0.6 | medium |
| `handoff` | gpt-4.1-mini | 0.3 | low |

Compared to graph nodes:

| Node | Model | Temperature | Verbosity |
|------|-------|-------------|-----------|
| `router` | gpt-4.1-mini | 0.15 | low |
| `understand` | gpt-4.1 | 0.2 | low |
| `think` | gpt-4.1 | 0.35 | medium |
| `act` | gpt-4.1-mini | 0.25 | low |
| `reply` | gpt-4.1-mini | 0.6 | medium |

### Streaming

Cook and Brainstorm use `call_llm_chat_stream()` — raw `AsyncOpenAI` streaming (no Instructor). Tokens yield as `chunk` SSE events.

Handoff uses `call_llm()` — Instructor-wrapped for structured `HandoffResult` output. Non-streaming.

### History Limits

| Mode | Max Messages | Exchanges |
|------|-------------|-----------|
| Cook | 20 | ~10 user/assistant pairs |
| Brainstorm | 40 | ~20 user/assistant pairs |

Older messages are trimmed from the front when the cap is exceeded.

---

## Context Loading

### Cook Mode

Context is **frozen at session start** — the recipe does not change during cooking.

1. Frontend sends `cook_init.recipe_id`
2. Backend fetches recipe via `db_read` (includes auto-joined `recipe_ingredients`)
3. Formats into `cook_context`: name, description, cuisine, servings, times, ingredients, instructions, user notes
4. Injected into system prompt via `{cook_context}` placeholder

### Brainstorm Mode

Context is **loaded at session start** from cached profile + dashboard.

1. Frontend sends `brainstorm_init: true`
2. Backend loads `get_cached_profile(user_id)` + `get_cached_dashboard(user_id)`
3. Formats into `brainstorm_context`: preferences, inventory summary, recipe titles by cuisine
4. Injected into system prompt via `{brainstorm_context}` placeholder

For full recipe details during brainstorm, users @-mention specific recipes — the frontend resolves these and includes the data in the message text. No LLM-initiated reads.

---

## System Prompts

| Mode | File | Key Traits |
|------|------|------------|
| Cook | `prompts/cook.md` | Concise (2-3 sentences), sensory cues, safety reminders, recipe-bound |
| Brainstorm | `prompts/brainstorm.md` | Conversational, expansive, riff-oriented, no data mutation |

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Invalid `recipe_id` on cook init | `error` event, stays in Plan mode |
| Recipe not found | `error` event, stays in Plan mode |
| LLM failure mid-turn | `error` event, stays in current mode (user retries or exits) |
| Client disconnect mid-stream | Background task completes, result stored in jobs table |
| Handoff LLM failure | Logged, `error` event pushed to queue |

---

## Files Reference

| File | Role |
|------|------|
| `src/alfred/core/modes.py` | Mode enum, `MODE_CONFIG` with `bypass_graph` flag |
| `src/alfred/llm/client.py` | `call_llm_chat_stream()`, `get_raw_async_client()` |
| `src/alfred/llm/model_router.py` | Node temperatures, verbosity configs |
| `src/alfred/modes/cook.py` | `run_cook_session()` async generator |
| `src/alfred/modes/brainstorm.py` | `run_brainstorm()` async generator |
| `src/alfred/modes/handoff.py` | `generate_session_handoff()` → `HandoffResult` |
| `src/alfred/web/app.py` | `ChatRequest`, `CookSessionInit`, SSE event routing |
| `src/alfred/web/background_worker.py` | Mode routing to correct generator |
| `prompts/cook.md` | Cook system prompt template |
| `prompts/brainstorm.md` | Brainstorm system prompt template |
| `tests/test_modes.py` | Unit tests (23 tests) |
