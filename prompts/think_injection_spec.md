# Think Prompt — Injection Architecture

## Overview

The Think prompt is assembled from:
1. **Static template** (`think_v2.md`) — roles, output format, rules
2. **Injected sections** — runtime context

This document specifies what gets injected, when, and how.

---

## Injection Order

Sections inject in order of **stability** (most stable → most dynamic):

```
┌─────────────────────────────────────────┐
│ STATIC TEMPLATE                         │
│ - Role, Output Format, Step Types       │
│ - Subdomains, Planning Rules, Examples  │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│ ## User Profile                         │
│ Rarely changes. Hard constraints here.  │
│ Source: preferences table               │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│ ## Kitchen Dashboard                    │
│ Snapshot of DB state. What EXISTS.      │
│ Source: count queries per subdomain     │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│ ## Entities in Context                  │
│ What's ADDRESSABLE by ref this session. │
│ Source: SessionIdRegistry               │
│ ⚠️ Only these refs are valid!           │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│ ## Conversation                         │
│ Recent turns for continuity.            │
│ Source: conversation history            │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│ ## Task                                 │
│ Current request. Most dynamic.          │
│ Source: understand_output               │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│ ## Your Decision                        │
│ Final nudge (static)                    │
└─────────────────────────────────────────┘
```

---

## Section Specifications

### User Profile

**Source:** `state["preferences"]` or dashboard query
**Format:**
```markdown
## User Profile
**Constraints:** Diet: vegetarian | Allergies: shellfish, peanuts
**Equipment:** air fryer, instant pot, stove
**Skill:** beginner
**Cuisines:** indian, thai, mexican
**Vibes:** quick weeknight meals, batch cooking
```

**Rules:**
- Constraints are HARD — never plan anything that violates allergies
- Skill affects recipe complexity suggestions
- Compact single-line format to save tokens

---

### Kitchen Dashboard

**Source:** Count queries + recent samples
**Format:**
```markdown
## Kitchen Dashboard
- **Inventory:** 49 items (pantry: 36, fridge: 7, freezer: 5)
- **Recipes:** 3 saved (indian: 2, thai: 1)
- **Meal Plan:** 2 meals planned (Mon dinner, Tue lunch)
- **Shopping:** 12 items
- **Tasks:** 1 pending
```

**Rules:**
- Shows what EXISTS in DB (ground truth)
- Does NOT mean refs are available — that's Entities in Context
- Include cuisine/category breakdown for recipes if helpful

---

### Entities in Context

**Source:** `SessionIdRegistry.format_for_think_prompt()`
**Format:**
```markdown
## Entities in Context

These refs are available. Act can use them directly.

**inventory:** (49 items)
  - `inv_1`: chicken thighs
  - `inv_2`: basmati rice
  - ... and 47 more

**recipes:** (2 items)
  - `recipe_1`: Spicy Cod Masala ← referenced this turn
  - `recipe_2`: Butter Chicken
```

**Rules:**
- ONLY these refs are valid for use in step descriptions
- If Dashboard shows items not here → must search by name
- Mark items "referenced this turn" if Understand flagged them
- Truncate long lists with "... and N more"

**Critical Warning (inject inline):**
```markdown
⚠️ Only use refs shown above. Dashboard items not listed here must be searched by name.
```

---

### Conversation

**Source:** `state["conversation_history"]` or summarized turns
**Format:**
```markdown
## Conversation

**Recent:**
User: what's in my pantry?
Alfred: You have 49 items including chicken thighs, rice, and various spices.

User: can you make a recipe with the cod?
Alfred: [current turn]

**Earlier:** User set up preferences and added inventory items.
```

**Rules:**
- Last 2-3 turns verbatim (or summarized if long)
- Older turns compressed to one-line summary
- Helps Think understand what was already discussed/done

---

### Task

**Source:** `understand_output`
**Format:**
```markdown
## Task

**Goal:** Generate a spicy cod recipe using pantry items
**User said:** "yeah make me that cod recipe!"
**Resolved:** User confirms previous proposal for cod recipe
**Referenced:** `inv_49` (frozen cod), `recipe_1` (if applicable)
**Mode:** PLAN (up to 8 steps)
**Today:** 2026-01-08
```

**Rules:**
- Goal is Understand's interpretation
- User said is raw message
- Resolved shows any reference resolution
- Referenced lists entities explicitly mentioned
- Mode indicates complexity budget
- Today enables date inference

---

## Conditional Injections

Some sections are conditional:

| Section | Condition |
|---------|-----------|
| Entities in Context | Only if registry has entries |
| Previous Turn note | Only if this is a confirmation response |
| Mode: QUICK | Only for simple single-step requests |

---

## Token Budget Guidelines

| Section | Target | Notes |
|---------|--------|-------|
| Static template | ~800 tokens | Fixed |
| User Profile | ~50 tokens | Compact format |
| Dashboard | ~80 tokens | Counts + samples |
| Entities in Context | ~200 tokens | Truncate at 10 per type |
| Conversation | ~150 tokens | Summarize older turns |
| Task | ~100 tokens | Current request |
| **Total** | **~1400 tokens** | Leaves room for response |

---

## Implementation Notes

### Current State
- `think_node.py` assembles prompt via string concatenation
- Uses `build_think_context()` from `injection.py`
- Multiple helper functions with overlapping logic

### Proposed Refactor
1. Define `ThinkPromptBuilder` class
2. Each section has a dedicated method
3. Methods return formatted markdown strings
4. `build()` concatenates in correct order
5. Unit tests verify section format

### Section Markers
Use HTML comments for debugging:
```markdown
<!-- BEGIN: entities_in_context -->
## Entities in Context
...
<!-- END: entities_in_context -->
```

This enables prompt log parsing and section extraction.
