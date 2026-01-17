# Alfred Context Layers Architecture

**Status:** Approved Design  
**Date:** 2026-01-13  
**Problem:** Multi-turn context is fragmented. Intelligence captured at each node isn't wired together.

---

## Configuration

| Setting | Default | Location | Notes |
|---------|---------|----------|-------|
| `TURN_RETENTION_WINDOW` | 2 | `src/alfred/config.py` | How many turns to keep full detail for |
| `COMPRESS_OLDER_TURNS` | True | `src/alfred/config.py` | Whether to LLM-compress older turns |

These should be easy to adjust as we learn optimal values.

---

## Executive Summary

Alfred's context system has three layers, but only two are implemented:

| Layer | Purpose | Manager | Status |
|-------|---------|---------|--------|
| **Entity Context** | What objects exist | Understand + Registry | ✅ Implemented |
| **Turn Narrative** | What happened and why | Summarize | ❌ MISSING |
| **Conversation History** | What was said | Summarize | ✅ Implemented |

**The gap:** We capture step results, analysis conclusions, and curation decisions but don't persist them as a "what happened" narrative. Think plans from scratch every turn.

---

## The Three Layers

### Layer 1: Entity Context
**What it contains:** Refs to objects (recipe_1, inv_5, gen_meal_plan_1)
**Who manages:** 
- **Understand** → decides what stays active (curation decisions)
- **SessionIdRegistry** → stores refs, labels, turn tracking

**Retention policy:**
- Last 2 turns: Auto-retained (based on `ref_turn_last_ref`)
- Older: Only if Understand explicitly retains with reason
- Very old: Dropped from working memory

**Example in prompt:**
```markdown
## Entities in Context

### Recent (last 2 turns) — already loaded, reference by ID
- recipe_3: Air Fryer Paneer Tikka (recipe) [read]
- recipe_4: Chicken Tikka Bites (recipe) [read]
- recipe_8: Thai Pad See Ew (recipe) [read]
- recipe_9: Thai Yellow Curry (recipe) [read]
- inv_1..inv_59: [59 inventory items]

### Retained (older, Understand decided)
- gen_meal_plan_1: Weekly Plan (turn 2) — *"User's ongoing goal"*

### Pending (unsaved)
- gen_recipe_1: Custom Thai Curry — *needs save confirmation*

### Excluded (this turn)
- recipe_5, recipe_6 — *User said no french toast, no wings*
```

---

### Layer 2: Turn Narrative (THE MISSING PIECE)
**What it contains:** 
- What happened (steps executed, conclusions)
- What was decided (curation, user choices)
- **Conversation flow** (tone, acknowledgments, direction) ← FOR REPLY

**Who manages:**
- **Summarize** → builds `TurnExecutionSummary` from step_results + understand_output + final_response
- **Think/Act** → consumes execution context
- **Reply** → consumes conversation flow

**Retention policy:**
- Last 2 turns: Full `TurnExecutionSummary` objects
- Older: Compressed into narrative string
- Very old: Dropped (part of compressed narrative)

**Example in prompt (for Think/Act):**
```markdown
## What Happened

### Turn 3 (last turn)
**User asked:** "exclude french toast and wings"
**Steps executed:**
  1. Analyzed existing recipe options from context
  2. Applied user exclusions (recipe_5, recipe_6)
**Understand decided:** Demoted recipe_5, recipe_6
**Result:** 4 remaining viable options
**Note:** recipe_3, recipe_4, recipe_8, recipe_9 ready for selection

### Turn 2
**User asked:** "no cod this week"
**Steps executed:**
  1. Read 9 recipes → recipe_1 through recipe_9
  2. Read 59 inventory items → inv_1 through inv_59
  3. Analyzed for cod exclusion → 6 viable
**Result:** Presented 6 cod-free options

### Earlier (compressed)
User started meal planning session. Exploring saved recipes for the week.
```

**Example in prompt (for Reply) — Conversation Flow:**
```markdown
## Conversation Flow

### Where we are
User is narrowing down meal options. We've been collaborative — asking preferences, 
presenting options, adjusting based on feedback. This is turn 3 of a meal planning session.

### Last exchange
User: "no cod this week"
Alfred: Presented 6 options warmly, invited further refinement

### Current exchange  
User: "lets not do the french toast or wings"
→ User is continuing to refine. Acknowledge naturally, present remaining options,
   keep the collaborative tone. Don't restart the conversation.

### Tone guidance
- Acknowledge their choice ("Got it" / "No problem")
- Reference what you're excluding (shows you heard them)
- Present remaining options
- Bridge to next step naturally
```

---

### Layer 3: Conversation History
**What it contains:** User messages + assistant responses (the dialogue)
**Who manages:**
- **Summarize** → appends turns, compresses older ones

**Retention policy:**
- Last 2-3 turns: Full text (`FULL_DETAIL_TURNS = 3`)
- Older: Compressed into `history_summary` string

**Example in prompt:**
```markdown
## Conversation

User: can you help me plan some meals?
Alfred: Absolutely! You usually cook on Sundays and Wednesdays, and you like 
simple, beginner-friendly meals with leftovers for lunch. Would you like to 
pick from your saved recipes, or are you interested in trying something new?

User: lets not do cod this week?
Alfred: Here are 6 recipes that fit your pantry (no cod): Air Fryer Paneer Tikka,
Chicken Tikka Bites, Chai French Toast, Dry Rub Wings, Pad See Ew, Yellow Curry.

User: lets not do the french toast or wings
→ (current turn, being processed)

### Earlier
User initiated meal planning for the week.
```

---

## How Layers Differ

| Aspect | Entity Context | Turn Narrative | Conversation |
|--------|---------------|----------------|--------------|
| **Contains** | Object refs | Execution summaries | Dialogue text |
| **Granularity** | Per-entity | Per-turn | Per-turn |
| **Manager** | Understand + Registry | Summarize | Summarize |
| **Retention** | 2 turns + explicit | 2 turns + compress | 3 turns + compress |
| **Used by** | All nodes | Think, Act | All nodes |
| **Action guidance** | "Use these IDs" | "We already did X" | Tone continuity |

---

## Prompt Structure (Standardized)

### For Think

```markdown
<session_context>
## User Profile
**Constraints:** Diet: no breakfast | Allergies: shellfish
**Has:** Equipment: air-fryer | Skill: beginner
**Likes:** Cuisines: indian, thai, mexican

## User Preferences (by domain)
**meal_plans:** I cook 2-3 times per week, usually Sunday and Wednesday...
**recipes:** Keep recipes to 5-7 steps max. Metric measurements preferred.

## Kitchen Dashboard
- **Recipes:** 9 saved (indian: 3, thai: 2, fusion: 3, malaysian: 1)
- **Inventory:** 59 items (pantry: 36, fridge: 9, freezer: 5)
- **Meal Plan:** Nothing planned for next 7 days
</session_context>

<entity_context>
## Entities in Context

### Recent (last 2 turns) — DO NOT re-read
- recipe_3: Air Fryer Paneer Tikka [read]
- recipe_4: Chicken Tikka Bites [read]
- recipe_8: Thai Pad See Ew [read]
- recipe_9: Thai Yellow Curry [read]
- inv_1..inv_59: [inventory loaded]

### Excluded (user rejected)
- recipe_5: French Toast — *"don't feel like it"*
- recipe_6: Dry Rub Wings — *"not this week"*

### Viable for planning
recipe_3, recipe_4, recipe_8, recipe_9
</entity_context>

<turn_narrative>
## What We've Done

### Last turn (turn 3)
**User:** "no cod this week"
**Steps:** Read recipes (9), Read inventory (59), Analyze (6 viable)
**Conclusion:** 6 recipes work with inventory, no cod

### This turn
**Understand resolved:** User excluded recipe_5, recipe_6
**Remaining viable:** recipe_3, recipe_4, recipe_8, recipe_9
</turn_narrative>

<conversation_history>
[Last 2-3 turns full text]

### Earlier
User started meal planning session.
</conversation_history>

<current_task>
**User says:** "lets not do the french toast or wings"
**Today:** 2026-01-13
**Mode:** PLAN (max 8 steps)

The user is narrowing options. Don't re-read — reference viable IDs directly.
</current_task>
```

### For Act (analyze/generate steps)

```markdown
<step_context>
## Current Step
**Step 3 of 3** | Type: analyze | Subdomain: recipes
**Your job:** Identify best recipes for the week from remaining options

## Prior Steps (this plan)
1. ✅ Read recipes — already in context
2. ✅ Read inventory — already in context
</step_context>

<entity_context>
## Viable Entities
- recipe_3: Air Fryer Paneer Tikka (indian, serves 2)
- recipe_4: Chicken Tikka Bites (indian, serves 4)
- recipe_8: Thai Pad See Ew (thai, serves 2)
- recipe_9: Thai Yellow Curry (thai, serves 2)

## Excluded (don't include)
- recipe_5, recipe_6
</entity_context>

<prior_turn_context>
## What happened before this plan
Last turn: Read all recipes and inventory, analyzed for cod exclusion.
User then excluded french toast and wings.
</prior_turn_context>

<data_to_analyze>
[Step results from prior steps in this plan]
</data_to_analyze>
```

### For Reply

**THE PROBLEM:** Reply today sounds like a fresh email every time:
```
User: "lets not do the french toast or wings"
Reply: "Hello! I'd be happy to help with your meal planning today.
       Based on your request, I have removed French Toast and Wings 
       from your available options. Here are the remaining recipes..."
```

**THE FIX:** Reply needs conversation flow context to respond naturally:

```markdown
<conversation_flow>
## Where We Are in This Conversation

**Session:** Turn 3 of meal planning. Collaborative exploration.
**Phase:** narrowing (user filtering down options)
**Tone:** collaborative (working together on this)

**Last exchange:**
- User: "no cod this week"
- You: Presented 6 cod-free options, invited refinement

**This exchange:**
- User: "lets not do the french toast or wings"
- You are mid-conversation, not starting fresh

**How to continue:**
- Acknowledge choice briefly ("Got it" / "No problem")
- Reference what you're excluding (shows you heard them)
- Present remaining naturally
- Bridge to next step ("Ready to pick?")
</conversation_flow>

<execution_results>
## What Happened This Turn
Goal: Filter out French Toast and Wings from options
Status: ✅ Success

### Remaining Options (4 recipes)
- recipe_3: Air Fryer Paneer Tikka (serves 2)
- recipe_4: Chicken Tikka Bites (serves 4)  
- recipe_8: Thai Pad See Ew (serves 2)
- recipe_9: Thai Yellow Curry (serves 2)
</execution_results>
```

**DESIRED REPLY OUTPUT:**
```
"Got it! No French Toast or Wings this week.

That leaves us with 4 solid options:
- Air Fryer Paneer Tikka (serves 2)
- Chicken Tikka Bites (serves 4)
- Thai Pad See Ew (serves 2)  
- Thai Yellow Curry (serves 2)

Want to pick a couple for the week, or should we narrow down further?"
```

**Key differences:**
1. No "Hello!" or formal greeting (mid-conversation)
2. Acknowledges their choice first (shows continuity)
3. References what's excluded (not just what's remaining)
4. Bridges naturally to next step
5. Tone matches prior exchanges (collaborative, not robotic)

---

## Data Structures

### TurnExecutionSummary (NEW)

```python
class StepExecutionSummary(BaseModel):
    """Summary of one step's execution."""
    description: str          # From ThinkStep
    step_type: str            # read/write/analyze/generate
    subdomain: str
    outcome: str              # "Found 9 recipes" / "Analysis complete"
    note: str | None          # note_for_next_step from Act
    entities_affected: list[str]  # refs touched


class TurnExecutionSummary(BaseModel):
    """What happened in a turn. Built by Summarize, consumed by Think/Act/Reply."""
    
    turn_number: int
    user_message: str
    goal: str                 # From ThinkOutput
    
    # Steps executed
    steps: list[StepExecutionSummary]
    
    # Understand's curation decisions
    curation_summary: str | None      # "Demoted recipe_5, recipe_6"
    retained_refs: list[str]          # Explicit retentions
    demoted_refs: list[str]           # Refs demoted this turn
    
    # Conclusions
    analysis_conclusions: str | None  # "4 recipes fit constraints"
    
    # What user saw
    response_summary: str
    
    # === CONVERSATION FLOW (for Reply continuity) ===
    conversation_phase: str        # "exploring" / "narrowing" / "confirming" / "executing"
    tone: str                      # "collaborative" / "informative" / "clarifying"
    what_user_expressed: str       # Intent: "Wants to exclude French Toast and Wings"
    what_we_acknowledged: str      # How Alfred responded: "Confirmed, presented remaining"
    natural_next: str              # Expected: "User picks finals or filters more"
```

### Storage in Conversation

```python
conversation = {
    # Existing
    "recent_turns": [...],           # Last 3 full turns
    "history_summary": "...",        # Compressed older turns
    
    # NEW: Turn narratives
    "turn_summaries": [              # Last 2 TurnExecutionSummary
        TurnExecutionSummary(...),   # Turn N-1
        TurnExecutionSummary(...),   # Turn N
    ],
    "earlier_execution_summary": "...",  # Compressed older narratives
    
    # Existing
    "understand_decision_log": [...],  # Curation history
}
```

---

## The Retention Model (Unified)

Both Entity and Narrative use the same pattern:

```
                    ┌─────────────────────────────────────────┐
                    │              RECENT                      │
                    │         (last 2 turns)                   │
                    │     Auto-retained, full detail           │
                    └─────────────────┬───────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │             RETAINED                     │
                    │       (explicit, with reason)            │
                    │    Understand: "User's ongoing goal"     │
                    │    Summarize: "Important context"        │
                    └─────────────────┬───────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │            COMPRESSED                    │
                    │         (narrative string)               │
                    │    "User started meal planning..."       │
                    └─────────────────┬───────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │             DROPPED                      │
                    │      (beyond retention window)           │
                    └─────────────────────────────────────────┘
```

| Layer | Recent Window | Explicit Retention | Compression |
|-------|--------------|-------------------|-------------|
| Entity | 2 turns | Understand's `retain_active` | N/A (just dropped) |
| Narrative | 2 turns | N/A (always compress) | LLM summarization |
| Conversation | 3 turns | N/A | LLM summarization |

---

## Who Builds What

| Component | Built By | From What | Stored In |
|-----------|----------|-----------|-----------|
| Entity refs | CRUD layer | db_read/db_create results | `id_registry` |
| Entity curation | Understand | User intent | `ref_active_reason`, `decision_log` |
| Turn narrative | Summarize | step_results + understand_output | `turn_summaries` |
| Conversation | Summarize | user_message + final_response | `recent_turns` |

---

## Implementation Plan

### Phase 1: Data Structures
1. Add `StepExecutionSummary` and `TurnExecutionSummary` to `state.py`
2. Add `turn_summaries` and `earlier_execution_summary` to conversation schema

### Phase 2: Summarize Builds Narrative
1. In `summarize_node()`:
   - Build `TurnExecutionSummary` from available inputs
   - Store in `conversation["turn_summaries"]` (keep last 2)
   - Compress older into `earlier_execution_summary`

### Phase 3: Wire to Think
1. In `think_node()`:
   - Read `turn_summaries` from conversation
   - Format as `<turn_narrative>` section
   - Add to prompt

### Phase 4: Wire to Act (for analyze/generate)
1. In `act_node()`:
   - For analyze/generate steps, include prior turn context
   - Format excluded/viable refs explicitly

### Phase 5: Update Reply
1. Add `<conversation_flow>` section
2. Add `<reply_guidance>` for conversational continuity

### Phase 6: Wire Understand → Think (same turn)
1. In `think_node()`:
   - Read `understand_output.entity_curation`
   - Add excluded/demoted refs to entity context section

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| How many turn narratives to keep? | 2 (same as entity recency window) |
| Should analyze conclusions be LLM-summarized? | No, use `note_for_next_step` + `result_summary` directly |
| When do narratives compress? | After 2 turns, LLM compresses older into string |
| How detailed should step summaries be? | Description + outcome + note. No full data (that's in entity refs). |

---

## Related Documents

- `docs/ideas/turn-narrative-spec.md` — Original Turn Narrative design
- `docs/ideas/act-filtering-audit.md` — Filtering system documentation
- `docs/context-engineering-architecture.md` — Existing architecture (needs update)

---

*Last updated: 2026-01-13*
