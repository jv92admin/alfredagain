# Phase 0.3: Constraint Flow Audit

## Executive Summary

Explicit user constraints (e.g., "8 meals", "2 lighter dinners") are compressed into narrative by Summarize and progressively lost across turns. Neither Think nor Act receive structured constraint data.

---

## 1. Constraint Flow Diagram

```
Turn 1: User says "plan 8 meals for Jan 5-9, rotate through 4 recipes, 2 lighter ones for dinner"
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ UNDERSTAND                                                               │
│ Output: processed_message = "User wants 8 meals, Jan 5-9, 4 recipes..."  │
│ ⚠️ No structured extraction of counts                                   │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ THINK                                                                    │
│ Sees: User said "...", Profile, Dashboard, Conversation Context          │
│ Plans: read inventory → generate 4 recipes → write → generate meal plan  │
│ ⚠️ Step description: "Generate 4 recipes (2 lighter for dinner)"        │
│ ⚠️ No structured constraints passed, just narrative                      │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ACT (Generate Step)                                                      │
│ Sees: Step description, User profile, Prior step data                    │
│ ⚠️ Only sees "Generate 4 recipes (2 lighter for dinner)" as text        │
│ ⚠️ No structured constraints: {meal_count: 8, lighter_dinners: 2}        │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ REPLY                                                                    │
│ Presents: 4 recipes generated                                            │
│ Output: Full recipe details                                              │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ SUMMARIZE                                                                │
│ Input: Full response, user message                                       │
│ LLM summarizes to: "User requested 8 meals for Jan 5-9 with 4 recipes    │
│                     including 2 lighter dinner options"                  │
│ ⚠️ Counts compressed into narrative string                              │
│ ⚠️ No structured storage of constraints                                 │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
Turn 2: Conversation context shows compressed narrative
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ THINK (Turn 2)                                                           │
│ Sees conversation: "User requested 8 meals..." (narrative)               │
│ ⚠️ No structured reminder: {meal_count: 8}                              │
│ ⚠️ Must re-parse narrative to understand constraints                     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Where Constraints Enter

### Entry Point: User Message

```
"plan 8 meals for next week. Jan 5-9th. Lets maybe rotate through 4 recipes (2 lighter ones for dinner)"
```

Contains explicit constraints:
- **meal_count**: 8
- **date_range**: Jan 5-9
- **recipe_count**: 4
- **lighter_dinner_count**: 2

### Current Handling

| Node | Sees Constraints As | Issues |
|------|---------------------|--------|
| Understand | Raw user message | No extraction |
| Think | Raw user message + conversation | Must parse from text |
| Act | Step description only | Only what Think wrote |
| Reply | Step results | No constraint awareness |
| Summarize | Full response | Compresses to narrative |

---

## 3. How Constraints Transform

### Turn 1: Original Constraints

User message (verbatim):
```
"plan 8 meals for next week. Jan 5-9th. Lets maybe rotate through 4 recipes (2 lighter ones for dinner)"
```

### Turn 1 → Turn 2: Compression

Summarize output (from LLM):
```
"User requested 8 meals planned for Jan 5-9 with 4 batch prep recipes including 2 lighter dinner options"
```

This goes into `conversation.history_summary` or `recent_turns[].assistant_summary`.

### Turn 2+: Further Compression

After multiple turns, history_summary may become:
```
"...User planned meals for the week with specific dietary preferences. Prepared 4 batch prep recipes..."
```

The "8 meals", "2 lighter dinners" specifics are lost.

---

## 4. Code Analysis

### 4.1 Summarize Node (`summarize.py`)

**`_summarize_assistant_response()`** (lines 321-391):
- LLM-summarizes responses > 400 chars
- Prompt focuses on "what action was taken"
- No instruction to preserve explicit counts

**`_compress_old_turns()`** (lines 393-449):
- Compresses oldest turn to "ONE brief sentence"
- Focus: "what the user asked, what action was taken"
- No instruction to preserve numeric constraints

**`_update_engagement_summary()`** (lines 452-481):
- Updates session theme
- Focus: "ongoing theme", not specific requirements

### 4.2 Conversation Context (`conversation.py`)

**`format_condensed_context()`** (lines 400-459):
- Formats for Think
- Includes: engagement_summary, active_entities, recent_turns, history_summary
- No structured constraints section

**`ConversationContext` structure**:
```python
{
    "engagement_summary": "",
    "recent_turns": [],
    "history_summary": "",
    "step_summaries": [],
    "active_entities": {},
    "all_entities": {},
    "content_archive": {},
}
```

**Missing**: `active_constraints` field

---

## 5. Impact Analysis

### Session Audit Evidence

From `prompt_logs/20260104_083751/68_reply.md`:

User originally requested: "8 meals for Jan 5-9, 2 lighter ones for dinner"

Meal plan generated:
- Jan 5: 2 meals ✓
- Jan 6: 1 meal + "leftovers" 
- Jan 7: 1 meal + "leftovers"
- Jan 8: 0 meals (all leftovers)
- Jan 9: 0 meals (all leftovers)

**Result**: Only 4 actual recipe-meals, not 8.

**Root Cause**: The generate step didn't have structured access to:
- `meal_count: 8`
- `lighter_dinner_count: 2`

It only saw the step description which said "allocate these 4 recipes across January 5-9".

### From `prompt_logs/20260104_083751/83_reply.md`:

After correction, meal plan still had 3 empty dinner slots instead of minimal breaks.

**Root Cause**: By Turn 2, "8 meals with some empty slots for breaks" became ambiguous. System over-allocated empty slots.

---

## 6. Gap Analysis

### GAP-C1: No Structured Constraint Extraction

Understand doesn't extract explicit constraints like:
```python
{
    "meal_count": 8,
    "date_range": "Jan 5-9",
    "recipe_count": 4,
    "lighter_dinner_count": 2
}
```

### GAP-C2: No Constraint Storage Field

ConversationContext has no `active_constraints` field.

### GAP-C3: No Constraint Preservation in Summarize

LLM summarization prompts don't instruct:
> "Preserve explicit numeric constraints (counts, dates, specific requirements)"

### GAP-C4: No Constraint Injection to Act

Act (generate steps) doesn't receive:
```markdown
## Active Constraints
- Meal count: 8
- Date range: Jan 5-9
- Recipe count: 4
- Lighter dinners: 2
```

### GAP-C5: No Constraint Expiry

Even if we add constraints, we need:
- Expiry logic (after how many turns?)
- Override detection ("actually, make it 6 meals")

---

## 7. Recommendations

### 7.1 Add Constraint Extraction to Understand

```python
class ExplicitConstraints(BaseModel):
    meal_count: int | None = None
    date_range: str | None = None
    recipe_count: int | None = None
    lighter_dinner_count: int | None = None
    custom: dict[str, Any] | None = None
    source_turn: int = 0
    expires_at_turn: int | None = None
```

Understand outputs `explicit_constraints` field.

### 7.2 Add `active_constraints` to ConversationContext

```python
ConversationContext = TypedDict('ConversationContext', {
    ...existing fields...
    'active_constraints': ExplicitConstraints | None,
})
```

### 7.3 Inject Constraints to Think

```markdown
## Active Constraints (from user)
- Meal count: 8
- Date range: Jan 5-9 (5 days)
- Recipe count: 4
- Lighter dinners: 2
```

### 7.4 Inject Constraints to Act (Generate Steps)

Include in `build_generate_sections()`:
```python
if active_constraints:
    parts.append(f"## Active Constraints\n{format_constraints(active_constraints)}")
```

### 7.5 Preserve Constraints in Summarize

Update compression prompts:
> "Preserve explicit numeric constraints (counts, dates, specific requirements) verbatim."

Or better: Skip LLM for constraints entirely—store them structured.

### 7.6 Add Constraint Expiry Logic

```python
def should_expire_constraints(constraints: ExplicitConstraints, current_turn: int) -> bool:
    if constraints.expires_at_turn and current_turn >= constraints.expires_at_turn:
        return True
    # Default: expire after 5 turns if not refreshed
    if current_turn - constraints.source_turn > 5:
        return True
    return False
```

---

## 8. Code Locations

| Component | File | Lines |
|-----------|------|-------|
| Summarize Node | `src/alfred/graph/nodes/summarize.py` | All |
| Conversation Memory | `src/alfred/memory/conversation.py` | All |
| Think Context Building | `src/alfred/graph/nodes/think.py` | 148-244 |
| Act Context Building | `src/alfred/graph/nodes/act.py` | 763-1000+ |
| Prompt Injection | `src/alfred/prompts/injection.py` | All |

---

## 9. Design Decision Questions

Based on this audit:

1. **Where should constraints be extracted?**
   - Option A: Understand (already parses user message)
   - Option B: Router (sees full message first)
   - Option C: New dedicated node

2. **How should constraints expire?**
   - Option A: After N turns (configurable)
   - Option B: When explicitly overridden
   - Option C: When goal changes (new topic)

3. **Should constraints be LLM-extracted or rule-based?**
   - Option A: LLM extraction (flexible but expensive)
   - Option B: Regex patterns (fast but brittle)
   - Option C: Hybrid (regex for common patterns, LLM for complex)

4. **Should Act always see constraints?**
   - Option A: Only for generate steps
   - Option B: For generate and analyze steps
   - Option C: For all step types

