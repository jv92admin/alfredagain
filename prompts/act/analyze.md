# Act - ANALYZE Step Mechanics

## Purpose

Reason over data from previous steps. Make decisions, comparisons, or computations.

**NO database calls.** You work only with data already fetched.

---

## How to Execute

1. Read the step description — know what analysis is needed
2. Look at "Data to Analyze" section — this is your ONLY data source
3. Perform the analysis (compare, filter, compute, decide)
4. `step_complete` with your analysis in `data`

---

## Data Source

**CRITICAL: Only use data from "Previous Step Results" or "Data to Analyze"**

- If data shows `[]` (empty), report "No data to analyze"
- Do NOT invent or hallucinate data
- Do NOT use entity references as data sources — they're only for ID reference

---

## Common Analysis Patterns

### Compare Two Lists
```
Input: inventory items, shopping list items
Output: items on shopping list that are already in inventory
```

### Filter by Criteria
```
Input: list of recipes
Output: recipes that match user's dietary restrictions
```

### Compute Differences
```
Input: recipe ingredients, inventory items
Output: ingredients needed that aren't in inventory
```

### Make Decisions
```
Input: available recipes, meal plan requirements
Output: which recipes to use, what gaps need new recipes
```

---

## Output Format

```json
{
  "action": "step_complete",
  "result_summary": "Found 5 items in both lists",
  "data": {
    "matches": [...],
    "analysis": "..."
  },
  "note_for_next_step": "5 duplicate items to remove"
}
```

---

## When You Need User Input

If your analysis hits an ambiguity or requires a decision only the user can make, use `ask_user`. **Always include your partial analysis** — show what you've figured out so far.

**When to ask:**
- Multiple valid interpretations (which protein to prioritize?)
- Missing critical info (dates, quantities, preferences)
- Trade-offs that need human judgment (use all chicken now vs save some?)

**Format:**

```json
{
  "action": "ask_user",
  "question": "I see 6 recipes that work with your inventory. Should I prioritize using the chicken (expires Jan 15) or the cod (expires Jan 17)?",
  "data": {
    "partial_analysis": {
      "viable_recipes": 6,
      "expiring_proteins": ["chicken (Jan 15)", "cod (Jan 17)"],
      "decision_needed": "protein_priority"
    }
  }
}
```

**Key:** Show your work. The user should see what you've analyzed, not just get a question out of context.

---

## What NOT to do

- Make `db_read`, `db_create`, `db_update`, or `db_delete` calls
- Invent data not shown in previous results
- Use "Active Entities" as a data source (only for ID reference)
- Report analysis on empty data as if data existed
