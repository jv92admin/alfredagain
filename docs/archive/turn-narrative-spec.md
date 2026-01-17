# Turn Narrative Specification

**Status:** Draft  
**Problem:** Multi-turn context is fragmented. Intelligence captured at each node isn't used by downstream nodes or future turns.

---

## The Problem

We capture intelligence at every node but don't wire it together:

| Node | Captures | Stored Where | Used By |
|------|----------|--------------|---------|
| Understand | Entity curation decisions, retention reasons | `understand_decision_log` | Only future Understand |
| Think | Goal, step plan, "why" reasoning | `think_output` | Act (description only) |
| Act | `note_for_next_step`, `result_summary` | `step_results` (within-plan only) | Next step in same plan |
| Summarize | Turn summary | `history_summary` (thin narrative) | Think (but no IDs/specifics) |

**Result:** Think plans fresh reads even when entities are in Recent Context. Act uses unsupported filters because it doesn't know what IDs to include/exclude.

---

## The Solution: Turn Execution Summary

A single structure that captures what happened in a turn, built by Summarize, consumed by Think/Act in subsequent turns.

### Data Model

```python
class StepExecutionSummary(BaseModel):
    """Summary of a single step's execution."""
    
    description: str          # From ThinkStep
    step_type: str            # read/write/analyze/generate
    subdomain: str            # recipes/inventory/etc
    outcome: str              # "Found 9 recipes" / "Analysis complete"
    note: str | None          # note_for_next_step from Act
    entities_affected: list[str]  # refs touched: recipe_1, recipe_2, ...


class TurnExecutionSummary(BaseModel):
    """
    Summary of what happened in a turn.
    
    Built by Summarize. Consumed by Think/Act/Reply in subsequent turns.
    """
    
    turn_number: int
    user_message: str         # What user asked
    goal: str                 # From ThinkOutput
    
    # Steps executed (not full data - just summary)
    steps: list[StepExecutionSummary]
    
    # Understand's decisions (surfaced from entity_curation)
    curation_summary: str | None  # "User demoted recipe_5, recipe_6 (French Toast, Wings)"
    retained_refs: list[str]       # Refs explicitly retained with reasons
    demoted_refs: list[str]        # Refs demoted this turn
    
    # Analysis conclusions (from analyze step data)
    analysis_conclusions: str | None  # "6 recipes fit inventory and equipment"
    
    # Response summary (brief - what user saw)
    response_summary: str
    
    # === CONVERSATION FLOW (for Reply) ===
    conversation_phase: str        # "exploring" / "narrowing" / "confirming" / "executing" / "reflecting"
    tone: str                      # "collaborative" / "informative" / "clarifying" / "problem_solving"
    what_user_expressed: str       # User's intent/feeling: "Wants to exclude options"
    what_we_acknowledged: str      # How Alfred responded: "Confirmed exclusions, presented remaining"
    natural_next: str              # What's expected: "User will pick final options or request more filtering"
```

### Where It Comes From

Summarize has access to:
- `user_message` → Direct
- `think_output.goal` → Direct
- `step_results` + `step_metadata` → Build steps summary
- `understand_output.entity_curation` → Build curation summary
- `final_response` → Summarize for response_summary

### Where It Goes

1. **Stored in:** `conversation["turn_execution_summaries"]` (list, last 2-3 turns)
2. **Injected into Think:** As "## Last Turn Summary" section (execution context)
3. **Injected into Act:** As "## Prior Context" section (for analyze/generate steps)
4. **Injected into Reply:** As "## Conversation Flow" section (tone, continuity)

### Prompt Injection Examples

#### For Think (subsequent turn):

```markdown
## Last Turn Summary

**Turn 2:** User asked "lets not do cod this week?"
**Goal:** Show recipe options for the week (excluding cod)
**Steps executed:**
1. Read 9 recipes → recipe_1 through recipe_9
2. Read 59 inventory items → inv_1 through inv_59
3. Analyze → 6 viable options: recipe_3, recipe_4, recipe_5, recipe_6, recipe_8, recipe_9

**Understand decisions:** Demoted recipe_1, recipe_2, recipe_7 (contain cod)
**Response:** Listed 6 cod-free options

---

**Turn 3 (current):** User says "lets not do the french toast? i also dont feel like doing wings"
**Understand resolved:** recipe_5 (French Toast), recipe_6 (Wings) → demoted

**Remaining viable options:** recipe_3, recipe_4, recipe_8, recipe_9
**DO NOT re-read** — these are already in Recent Context.
```

#### For Act (analyze step):

```markdown
## Prior Context

**Last turn results:**
- Recipes read: recipe_1 through recipe_9 (9 total)
- Inventory read: inv_1 through inv_59 (59 total)
- Analysis: 6 recipes fit inventory

**Current turn context:**
- User excluded: recipe_5 (French Toast), recipe_6 (Wings)
- Remaining candidates: recipe_3, recipe_4, recipe_8, recipe_9

**Use these IDs directly** — don't re-query.
```

#### For Reply (conversation continuity):

```markdown
## Conversation Flow

**Session context:** Turn 3 of meal planning. User has been collaborating to narrow down options.

**Where we are:**
- Phase: narrowing (user is filtering down options)
- Tone: collaborative (we're helping them decide)
- We've been: Presenting options, asking preferences, adjusting based on feedback

**Last exchange:**
- User expressed: Wanted to exclude cod from options
- We acknowledged: Confirmed exclusion, presented 6 remaining options warmly
- Natural next: User refines further or picks final options

**This exchange:**
- User expressed: Wants to exclude French Toast and Wings
- What we did: Filtered those out (recipe_5, recipe_6)
- Remaining: 4 options to present

**How to respond:**
- Acknowledge their choice naturally ("Got it!" / "Sure thing" / "No problem")
- Reference what you're excluding (shows you heard them)
- Present remaining options with the same helpful energy
- Bridge naturally to next step ("Want me to..." / "Ready to pick some?")
- DO NOT restart the conversation — you're mid-flow, not beginning
```

---

## Conversation Flow Details

The conversation flow fields help Reply maintain natural dialogue continuity:

### Conversation Phases

| Phase | Description | Typical Reply Tone |
|-------|-------------|--------------------|
| `exploring` | User is asking questions, browsing options | Informative, suggesting |
| `narrowing` | User is filtering down choices | Confirmatory, presenting alternatives |
| `confirming` | User is about to commit to a choice | Clear, summarizing |
| `executing` | User is acting (creating, updating) | Confirming actions, showing results |
| `reflecting` | User is reviewing what was done | Summarizing, inviting next steps |

### Tone Categories

| Tone | When to use | Example phrases |
|------|-------------|-----------------|
| `collaborative` | Working together on a task | "Let's see...", "Here's what we've got" |
| `informative` | Answering questions | "Here's the info you asked for" |
| `clarifying` | Resolving ambiguity | "Just to make sure I understand..." |
| `problem_solving` | Handling issues | "Here's what I found...", "We can try..." |

### Building Conversation Flow in Summarize

Summarize should extract conversation flow from:
1. **User message sentiment** → `what_user_expressed`
2. **Reply content** → `what_we_acknowledged`
3. **Session state** (turn count, entity activity) → `conversation_phase`
4. **Previous tone** (maintain consistency) → `tone`
5. **Step outcomes** → `natural_next`

This can be done by the existing Summarize LLM call — just extend the prompt to ask for these fields.

---

## Implementation Plan

### Phase 1: Build TurnExecutionSummary in Summarize

1. Add `TurnExecutionSummary` model to `state.py`
2. In `summarize_node()`:
   - Build `StepExecutionSummary` from `step_results` + `step_metadata`
   - Extract `curation_summary` from `understand_output.entity_curation`
   - Extract `analysis_conclusions` from analyze step data
   - Build `response_summary` from `final_response` (existing LLM call)
3. Store in `conversation["turn_execution_summaries"]`

### Phase 2: Wire to Think

1. In `think_node()`:
   - Read `conversation["turn_execution_summaries"]`
   - Format as "## Last Turn Summary" section
   - Include in `<conversation_history>` block

### Phase 3: Wire to Act (for analyze/generate)

1. In `act_node()`:
   - For analyze/generate steps, include prior turn context
   - Format remaining viable refs based on curation decisions
   - Add explicit "use these IDs" guidance

### Phase 4: Wire Understand → Think (same turn)

1. In `think_node()`:
   - Read `understand_output.entity_curation` from current state
   - If demotions exist, add "User excluded: ..." to immediate task
   - Compute remaining refs and include in prompt

---

## Key Principles

1. **No data duplication** — Turn summaries contain refs and outcomes, not full entity data
2. **Entity data stays in registry** — Full content lives in `SessionIdRegistry`, summaries point to refs
3. **LLM-driven narrative** — Summarize uses LLM to produce coherent summary, not just JSON dump
4. **Last 2 turns only** — Don't bloat context with ancient history
5. **Explicit action guidance** — "Use these IDs directly" beats hoping LLM figures it out

---

## Resolved Questions

| Question | Decision | Rationale |
|----------|----------|-----------|
| How many turn summaries? | **2 turns** (configurable) | Balance context quality vs token budget |
| Analyze conclusions format? | LLM-summarized | More coherent for downstream consumers |
| Conversation direction hint? | **Yes** (in `conversation_phase`) | Helps Reply maintain continuity |
| Analyze ask_user? | Yes, but always pair with partial analysis | Don't just ask — show your work |

---

## Quick Mode Note

Quick mode is single-step reads decided by Understand. It doesn't change Think/Act design — conversation history retention is the same. Quick mode just bypasses Think for simple lookups.

---

*Last updated: 2026-01-13*
