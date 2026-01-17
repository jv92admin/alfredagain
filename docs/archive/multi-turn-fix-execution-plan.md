# Multi-Turn Fix: Execution Plan v2

**Status:** Ready for Implementation  
**Date:** 2026-01-13  
**Architecture:** Three-Layer Context API

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT API                                   │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: ENTITY         │  LAYER 2: CONVERSATION  │  LAYER 3: REASONING    │
│  "What exists"           │  "What was said"        │  "What LLMs decided"   │
│  Owner: id_registry      │  Owner: Summarize       │  Owner: Summarize      │
│  + Understand            │                         │  (aggregates all)      │
└─────────────────────────────────────────────────────────────────┘

Each node subscribes to specific slices via build_*_context() functions.
```

**Related Docs:**
- `docs/ideas/context-api-spec.md` — Full API specification
- `docs/ideas/current-state-audit.md` — What exists today
- `docs/ideas/turn-narrative-spec.md` — Turn summary data model

---

## Problem Summary

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Think plans from scratch | No Layer 3 (Reasoning Trace) | Build TurnExecutionSummary |
| Act uses bad filters | No exclusion guidance | Update prompts |
| Reply is transactional | No conversation flow | Add phase/tone to Reply context |
| Intelligence captured but lost | Layers not wired to nodes | Context API builder functions |

---

## Implementation Phases

### Phase 0: Quick Wins (Prompt-Only)
**Time:** 1-2 hours | **Risk:** Low | **State Changes:** None

These are pure prompt updates — no code changes, instant rollback.

| Task | File | Change |
|------|------|--------|
| 0a. Exclusion patterns | `prompts/act/crud.md` | Ban `not_ilike`, show `not_in` pattern |
| 0b. Context reuse | `prompts/act/read.md` | "Check Entity Context before reading" |
| 0c. Think as conversationalist | `prompts/think.md` | Remove "use sparingly", add conversation framing |
| 0d. Analyze ask_user | `prompts/act/analyze.md` | Always pair with partial analysis |

**Phase 0c Details (Think reframe):**

```markdown
## CURRENT (Wrong)
You are a planning agent. Use clarify sparingly.

## NEW (Right)
You are Alfred's conversational intelligence.
Your job is to have a productive conversation, using planning to serve the user.

Complex tasks are iterative conversations, not one-shot answers.
"Plan my meals" → First align on preferences, THEN plan execution.

Use `propose`/`clarify` to ALIGN with the user, not just ask permission.
```

**Phase 0d Details (Analyze ask_user):**

```json
{
  "action": "ask_user",
  "question": "Should I prioritize the expiring chicken or cod?",
  "data": {
    "partial_analysis": {
      "viable_recipes": 6,
      "expiring_proteins": ["chicken (Jan 15)", "cod (Jan 17)"]
    }
  }
}
```

---

### Phase 1: Context API Foundation
**Time:** 2-3 hours | **Risk:** Low | **State Changes:** New file, additive

Create the unified context builder module.

| Task | File | Change |
|------|------|--------|
| 1a. Create context module | `src/alfred/context/__init__.py` | New package |
| 1b. Entity context builder | `src/alfred/context/entity.py` | `get_entity_context()`, `format_entity_context()` |
| 1c. Conversation builder | `src/alfred/context/conversation.py` | `get_conversation_history()`, `format_conversation()` |
| 1d. Reasoning builder | `src/alfred/context/reasoning.py` | `get_reasoning_trace()`, `format_reasoning()` |
| 1e. Node-specific builders | `src/alfred/context/builders.py` | `build_think_context()`, `build_act_context()`, etc. |

**Key insight:** These builders READ from existing state. They don't change storage yet.

```python
# src/alfred/context/builders.py

def build_think_context(state: AlfredState) -> ThinkContext:
    """Build Think's context from existing state."""
    return ThinkContext(
        entity=get_entity_context(state["id_registry"], mode="refs_and_labels"),
        conversation=get_conversation_history(state["conversation"]),
        reasoning=get_reasoning_trace(state["conversation"]),
        curation=get_current_curation(state.get("understand_output")),
    )
```

---

### Phase 2: Extend Storage for Layer 3
**Time:** 1-2 hours | **Risk:** Low | **State Changes:** Additive fields

Add the missing Reasoning Trace storage.

| Task | File | Change |
|------|------|--------|
| 2a. Add TurnExecutionSummary | `src/alfred/graph/state.py` | New Pydantic model |
| 2b. Add turn_summaries field | `src/alfred/graph/state.py` | `ConversationContext.turn_summaries` |
| 2c. Add reasoning_summary field | `src/alfred/graph/state.py` | For compressed older reasoning |

**Data Model:**

```python
class TurnExecutionSummary(BaseModel):
    turn_num: int
    think_decision: str           # "plan_direct" | "propose" | "clarify"
    think_goal: str
    steps: list[StepSummary]
    entity_curation: CurationSummary
    conversation_phase: str       # "exploring" | "narrowing" | "confirming"
    user_expressed: str           # "wants quick meals"

class StepSummary(BaseModel):
    step_num: int
    type: str                     # "read" | "analyze" | "generate" | "write"
    subdomain: str
    outcome: str                  # "Found 5 recipes"
    entities_involved: list[str]  # ["recipe_1", "recipe_2"]
    note: str | None              # Act's note_for_next_step
```

---

### Phase 3: Summarize Builds Layer 3
**Time:** 2-3 hours | **Risk:** Medium | **State Changes:** Summarize output

Update Summarize to build and store TurnExecutionSummary.

| Task | File | Change |
|------|------|--------|
| 3a. Build turn summary | `src/alfred/graph/nodes/summarize.py` | New `_build_turn_execution_summary()` |
| 3b. Store in conversation | `src/alfred/graph/nodes/summarize.py` | Append to `turn_summaries`, keep last 2 |
| 3c. Compress older summaries | `src/alfred/graph/nodes/summarize.py` | LLM call to compress to `reasoning_summary` |
| 3d. Extract conversation phase | `src/alfred/graph/nodes/summarize.py` | Infer from Think decision + step types |

**Phase detection logic:**

```python
def _infer_conversation_phase(think_output, step_results) -> str:
    if think_output.decision in ("propose", "clarify"):
        return "exploring"
    
    step_types = [s.step_type for s in think_output.steps]
    if "write" in step_types:
        return "executing"
    if "analyze" in step_types or "generate" in step_types:
        return "narrowing"
    if all(t == "read" for t in step_types):
        return "exploring"
    
    return "exploring"
```

---

### Phase 4: Wire Think to Context API
**Time:** 2 hours | **Risk:** Medium | **State Changes:** Think node refactor

Update Think to use the Context API.

| Task | File | Change |
|------|------|--------|
| 4a. Use build_think_context() | `src/alfred/graph/nodes/think.py` | Replace ad-hoc context building |
| 4b. Format reasoning section | `src/alfred/graph/nodes/think.py` | Add `<reasoning_trace>` to prompt |
| 4c. Wire Understand curation | `src/alfred/graph/nodes/think.py` | Show what was retained/demoted |
| 4d. Update prompt template | `prompts/think.md` | Add reasoning trace section |

**Think prompt structure:**

```markdown
## Entity Context
{format_entity_context(ctx.entity)}

## Conversation History
{format_conversation(ctx.conversation)}

## What Happened Last Turn
{format_reasoning(ctx.reasoning)}

## Understand's Curation (This Turn)
{format_curation(ctx.curation)}

---
## Your Task
{existing think instructions}
```

**Critical addition to prompt:**

```markdown
## Available Entities (DO NOT RE-READ)
These are already in context from recent turns:
- recipe_1: Lemon Herb Chicken
- recipe_2: Garlic Shrimp Pasta
...

If you need this data, reference it directly. Do not plan read steps for entities already available.
```

---

### Phase 5: Wire Act to Context API
**Time:** 1-2 hours | **Risk:** Low | **State Changes:** Act context update

Update Act to use the Context API (primarily for analyze/generate steps).

| Task | File | Change |
|------|------|--------|
| 5a. Use build_act_context() | `src/alfred/graph/nodes/act.py` | Replace ad-hoc context building |
| 5b. Format entity section | `src/alfred/prompts/injection.py` | Consistent entity formatting |
| 5c. Add prior context for analyze | `src/alfred/prompts/injection.py` | Show what's in context |

---

### Phase 6: Wire Reply to Context API
**Time:** 2-3 hours | **Risk:** Low | **State Changes:** Reply context update

Update Reply for conversation continuity.

| Task | File | Change |
|------|------|--------|
| 6a. Use build_reply_context() | `src/alfred/graph/nodes/reply.py` | Replace ad-hoc context building |
| 6b. Add conversation flow section | `prompts/reply.md` | Phase, tone, acknowledgment patterns |
| 6c. Format flow for prompt | `src/alfred/graph/nodes/reply.py` | Extract from TurnExecutionSummary |
| 6d. Add anti-patterns | `prompts/reply.md` | Ban "Hello!" mid-conversation |

**Reply prompt additions:**

```markdown
## Conversation Flow
- Turn: 3 of ongoing conversation
- Phase: narrowing (user has excluded some options)
- User expressed: "no cod this week"
- Your last response: Showed 8 recipe options

## Anti-Patterns (DO NOT)
- Don't say "Hello!" or "Hi there!" mid-conversation
- Don't say "I'd be happy to help!" after turn 1
- Don't reintroduce yourself

## Natural Continuity
- Acknowledge: "Got it" / "No problem" / "Sure thing"
- Bridge: "That leaves us with..." / "Down to..."
```

---

### Phase 7: Testing & Validation
**Time:** 2-3 hours | **Risk:** N/A

| Test | Scenario |
|------|----------|
| Multi-turn meal planning | Plan → exclude → narrow → select → save |
| Think conversation | "Plan my meals" → Should clarify, not execute immediately |
| Context reuse | Turn 2 shouldn't re-read Turn 1 data |
| Reply continuity | Turn 3 should feel like Turn 3, not Turn 1 |

---

## File Change Summary

### New Files
```
src/alfred/context/
├── __init__.py
├── entity.py        # Layer 1 builder
├── conversation.py  # Layer 2 builder
├── reasoning.py     # Layer 3 builder
└── builders.py      # Node-specific builders
```

### Modified Files
| File | Phase | Change Type |
|------|-------|-------------|
| `prompts/act/crud.md` | 0 | Prompt only |
| `prompts/act/read.md` | 0 | Prompt only |
| `prompts/think.md` | 0, 4 | Prompt + structure |
| `prompts/act/analyze.md` | 0 | Prompt only |
| `prompts/reply.md` | 6 | Prompt + structure |
| `src/alfred/graph/state.py` | 2 | Additive models |
| `src/alfred/graph/nodes/summarize.py` | 3 | Build Layer 3 |
| `src/alfred/graph/nodes/think.py` | 4 | Use Context API |
| `src/alfred/graph/nodes/act.py` | 5 | Use Context API |
| `src/alfred/graph/nodes/reply.py` | 6 | Use Context API |
| `src/alfred/prompts/injection.py` | 5, 6 | Formatting updates |

---

## Execution Order

```
Phase 0 (Prompts Only) ──────────────────────────────────────┐
  0a. crud.md exclusions                                     │
  0b. read.md context reuse                                  │ Can deploy
  0c. think.md conversationalist                             │ immediately
  0d. analyze.md ask_user                                    │
─────────────────────────────────────────────────────────────┘
                              ↓
Phase 1 (Context API Foundation) ────────────────────────────┐
  1a-e. Create src/alfred/context/ module                    │ Foundation
─────────────────────────────────────────────────────────────┘
                              ↓
Phase 2 (Storage) ───────────────────────────────────────────┐
  2a-c. Add TurnExecutionSummary to state.py                 │ Additive
─────────────────────────────────────────────────────────────┘
                              ↓
Phase 3 (Summarize Builds Layer 3) ──────────────────────────┐
  3a-d. Summarize builds and stores TurnExecutionSummary     │ Core change
─────────────────────────────────────────────────────────────┘
                              ↓
Phase 4 (Think) ─────────────────────────────────────────────┐
  4a-d. Think uses Context API, gets reasoning trace         │ High impact
─────────────────────────────────────────────────────────────┘
                              ↓
Phase 5 (Act) ───────────────────────────────────────────────┐
  5a-c. Act uses Context API                                 │ Refinement
─────────────────────────────────────────────────────────────┘
                              ↓
Phase 6 (Reply) ─────────────────────────────────────────────┐
  6a-d. Reply uses Context API, conversation continuity      │ Polish
─────────────────────────────────────────────────────────────┘
                              ↓
Phase 7 (Testing) ───────────────────────────────────────────┐
  Full flow validation                                       │
─────────────────────────────────────────────────────────────┘
```

---

## Success Criteria

**After all phases, this should work:**

```
Turn 1: "help me plan meals"
Think: propose → "How many days? What's your cooking schedule?"
       (Uses kitchen snapshot, preferences to make smart proposal)

Turn 2: "3 days, dinners only"
Think: plan_direct → read recipes, read inventory, analyze
       (Now has enough info to act)
Reply: "Based on your inventory, here are 8 recipes..."

Turn 3: "no cod this week"
Understand: demotes cod recipes
Think: sees reasoning trace, knows we have 8 recipes loaded
       plan_direct → analyze (filter out cod)
       (Does NOT re-read recipes!)
Reply: "Got it! That leaves us with 6 options..."

Turn 4: "let's go with the chicken and pasta ones"
Think: sees what's viable, plans write steps
Reply: "Perfect! I've added Lemon Herb Chicken and Garlic Pasta to your plan."
```

---

## Rollback Strategy

| Phase | Rollback |
|-------|----------|
| 0 | Revert prompt files |
| 1 | Delete context module (not used yet) |
| 2 | Remove new fields (ignored by existing code) |
| 3+ | Feature flag: `ENABLE_TURN_NARRATIVES = False` |

---

## Ready to Start

**Recommended starting point:** Phase 0 (prompt-only changes)

- Zero risk
- Immediate benefit
- Can test before committing to code changes

**Shall I begin with Phase 0a (crud.md exclusion patterns)?**
