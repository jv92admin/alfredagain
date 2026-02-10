# Summarize Node Contracts (V4)

## Role

Summarize is the **Conversation Historian**. It runs after every Reply to:
1. Append the current turn to conversation history
2. Compress older turns when threshold exceeded (LLM)
3. Build a structured audit ledger (SummarizeOutput)
4. Add newly created entities to context

**V4 Key Change**: Summarize does NOT curate entity context. That's Understand's job.

**Summarize does NOT produce user-facing output.** It updates internal state.

---

## What Summarize Does (V4)

| Responsibility | Description |
|----------------|-------------|
| **Append Turn** | Add current user + assistant to recent_turns |
| **Compress History** | LLM-summarize older turns into narrative (no IDs) |
| **Audit Ledger** | Build SummarizeOutput with entity deltas, artifact counts |
| **Add Entities** | Add newly created entities to EntityContextModel |
| **Track Clarification** | Store pending_clarification for context threading |

---

## What Summarize Does NOT Do (V4)

| Not Our Job | Who Does It |
|-------------|-------------|
| **Entity Curation** | Understand (curates based on user intent) |
| **Entity Lifecycle** | Understand (promote, demote, drop) |
| **Engagement Summary** | Think (has the goal) |
| **User-facing Text** | Reply |
| **Decisions** | Think |

---

## Input Contract

Summarize receives:

| Input | Source | Purpose |
|-------|--------|---------|
| `final_response` | Reply node | The text shown to user |
| `user_message` | Router | What user said |
| `router_output` | Router | Goal, complexity, agent |
| `think_output` | Think | Decision type, steps |
| `step_results` | Act | Tool results per step |
| `step_metadata` | Act | V4: Full artifacts for generate steps |
| `turn_entities` | Act | Entities created/modified this turn |
| `conversation` | State | Existing history |
| `entity_context` | State | V4: Tiered entity context |
| `session_constraints` | State | V4: Accumulated constraints |

---

## Output Contract

Summarize updates:

| Output | Content | Purpose |
|--------|---------|---------|
| `conversation.recent_turns` | Full text of last N turns | Context for Think/Act |
| `conversation.history_summary` | Narrative of older turns (no IDs) | Context for Understand |
| `summarize_output` | V4: Structured audit ledger | Machine-readable deltas |
| `entity_context` | V4: Updated with new entities | For Understand to curate |
| `session_constraints` | V4: Successful query patterns | For Think |
| `current_turn` | Incremented turn number | Turn tracking |

---

## Two LLM Calls (V4 Simplified)

### 1. Response Summary (`AssistantResponseSummary`)

**When**: Reply's output > 400 chars

**Input**: `final_response` (Reply's full text)

**Output**: 1-sentence summary of what was accomplished

**Critical Rules**:
- **Proposals ≠ Completed actions**
  - "I'll save the items" → "Proposed to save items"
  - "Done! I saved the items." → "Saved items: [names]"
- Use EXACT entity names from the text

### 2. Conversation Compression (`_compress_turns_to_narrative`)

**When**: `recent_turns` exceeds `FULL_DETAIL_TURNS` (currently 3)

**Input**: Oldest turns to compress

**Output**: 2-3 sentence narrative summary

**Critical Rules**:
- Focus on conversation arc, not entity IDs
- "User explored options, decided on a direction, saved 3 items"
- NO UUIDs, NO technical details
- This is for Understand's narrative context

---

## V4: SummarizeOutput (Structured Audit Ledger)

```json
{
  "turn_summary": "Created 3 items, saved to database",
  "entities_created": [
    {"id": "abc123", "type": "item", "label": "Example Item"}
  ],
  "entities_updated": [],
  "entities_deleted": [],
  "artifacts_generated": {"items": 3},
  "artifacts_saved": {"items": 3},
  "errors": [],
  "next_step_suggestion": "Would you like to do anything else with these?"
}
```

This is machine-readable for debugging and analytics, not for prompts.

---

## Entity Handling (V4)

### What Summarize Does

1. **Add new entities to context**: Entities created this turn go to active tier
2. **Set turn number**: Update current_turn on entity context

### What Summarize Does NOT Do

- Promote/demote entities (Understand does this)
- Drop stale entities (Understand does this)
- Garbage collect based on time (removed in V4)

**The key insight**: Entity relevance is intent-dependent, not time-dependent.
Understand sees user intent and curates accordingly.

---

## Clarification Tracking

Summarize tracks `pending_clarification` for context threading:

| Decision | What's Stored |
|----------|---------------|
| `plan_direct` | Nothing - execution complete |
| `propose` | proposal_message, goal |
| `clarify` | clarification_questions, goal |
| `understand` | Disambiguation questions |

This helps the next turn know we're waiting for user confirmation.

---

## Configuration

| Constant | Value | Purpose |
|----------|-------|---------|
| `SUMMARIZE_THRESHOLD` | 400 chars | Minimum length to trigger LLM summarization |
| `FULL_DETAIL_TURNS` | 3 | How many recent turns to keep in full |
