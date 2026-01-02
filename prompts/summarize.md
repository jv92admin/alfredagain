# Summarize Node Contracts

## Role

Summarize is the **memory manager**. It runs after every Reply to:
1. Compress long responses for context (so future prompts aren't bloated)
2. Track conversation history
3. Maintain session theme
4. Merge entities from the turn into active tracking
5. Garbage collect stale entities

**Summarize does NOT produce user-facing output.** It updates internal state.

---

## Input Contract

Summarize receives:

| Input | Source | Purpose |
|-------|--------|---------|
| `final_response` | Reply node | The text shown to user |
| `user_message` | Router | What user said |
| `router_output` | Router | Goal, complexity, agent |
| `think_output` | Think | Decision type, steps, proposal_message |
| `step_results` | Act | Tool results per step |
| `turn_entities` | Act | Entities created/modified this turn |
| `conversation` | State | Existing history, entities, summaries |

---

## Output Contract

Summarize updates:

| Output | Content | Used By |
|--------|---------|---------|
| `conversation.recent_turns` | Full text of last N turns | Context for Think/Act |
| `conversation.history_summary` | Compressed older turns | Context for Think |
| `conversation.engagement_summary` | 1-sentence session theme | Context for all nodes |
| `conversation.active_entities` | Recent entities for reference | Think/Act entity resolution |
| `conversation.step_summaries` | Compressed step results | Act older step lookup |
| `entity_registry` | Full entity lifecycle tracking | V3 entity management |

---

## Three LLM Calls

### 1. Response Summary (`AssistantResponseSummary`)

**When**: Reply's output > 400 chars AND Think's decision was NOT propose/clarify

**Input**: `final_response` (Reply's full text)

**Output**: 1-sentence summary of what was accomplished

**V3 Safeguard**: If Think decided `propose` or `clarify`, we skip the LLM entirely and return a deterministic summary like "Proposed a plan and awaiting user confirmation." This prevents hallucinating completion from proposals.

**Critical Rules**:
- **Proposals ≠ Completed actions**
  - "I'll save the recipes" → "Proposed to save recipes; awaiting confirmation"
  - "Done! I saved the recipes." → "Saved recipes: [exact names]"
- Use EXACT entity names from the text
- Don't invent or paraphrase names

**Used For**: `conversation.recent_turns[].assistant_summary` - shown in context for Think/Act

### 2. Turn Compression (`TurnSummary`)

**When**: `recent_turns` exceeds `FULL_DETAIL_TURNS` (currently 3)

**Input**: Oldest turn's user + assistant text

**Output**: 1-sentence summary of the exchange

**Critical Rules**:
- **Proposals ≠ Completed actions** (same rule applies)
  - "I'll design 3 recipes" → "User requested X; assistant proposed a plan"
  - "Done! Designed 3 recipes" → "Assistant created recipes: [names]"
- Focus on: what user asked, what action was taken
- Mention any entities created/modified
- Keep specific (IDs, names)

**Used For**: `conversation.history_summary` - provides context for older interactions

### 3. Session Theme (`EngagementSummary`)

**When**: Significant action (high complexity or multi-step)

**Input**: Current summary + latest exchange

**Output**: 1-sentence theme update

**Critical Rules**:
- Focus on the ongoing theme, not individual actions
- "Planning rice bowl meal prep" not "Just saved a recipe"

**Used For**: `conversation.engagement_summary` - shown at top of context

---

## Entity Management

### Input: `turn_entities` (from Act)

Entities extracted during Act steps with:
- `id`: UUID or temp_id
- `type`: recipe, meal_plan, task, etc.
- `label`: Human-readable name
- `state`: PENDING or ACTIVE
- `source`: db_read, db_write, generate, analyze

### Processing

1. **Merge to EntityRegistry**: Add all entities to registry for lifecycle tracking
2. **Filter for active_entities**: Only store entities from DB sources (db_read, db_write) in `active_entities`. PENDING entities from generate/analyze steps are NOT promoted.
3. **Garbage collect**: Mark entities not referenced in `PENDING_TTL_TURNS` as inactive.

### Why Filtering Matters

GENERATE steps produce entities with temp/hallucinated IDs that don't exist in the database. If these are promoted to `active_entities`, later turns will try to use these IDs for FK references and fail.

**Only store entities that exist in the database.**

---

## Decision Context Tracking

Summarize tracks `pending_clarification` for context threading:

| Decision | What's Stored |
|----------|---------------|
| `plan_direct` | Nothing - execution complete |
| `propose` | proposal_message, assumptions, goal |
| `clarify` | clarification_questions, goal |

This helps the next turn know we're waiting for user confirmation.

---

## What Summarize Does NOT Do

- Generate user-facing text (that's Reply)
- Make decisions about what to do (that's Think)
- Execute any actions (that's Act)
- Route requests (that's Router)

Summarize is purely about **maintaining state** for future turns.

---

## Configuration

| Constant | Value | Purpose |
|----------|-------|---------|
| `SUMMARIZE_THRESHOLD` | 400 chars | Minimum length to trigger LLM summarization |
| `FULL_DETAIL_TURNS` | 3 | How many recent turns to keep in full |
| `FULL_DETAIL_STEPS` | 3 | How many recent step results to keep in full |
| `PENDING_TTL_TURNS` | 3 | How long before PENDING entities are garbage collected |

