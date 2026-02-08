# Understand Node — Prompt Regression Audit

**Pre-refactor:** `prompt_logs_downloaded/20260203_014946/06_understand.md`
**Post-refactor:** `prompt_logs/20260207_235146/01_understand.md`

## System Prompt

**IDENTICAL.** No change.

```
You are Alfred's MEMORY MANAGER. Your job: (1) resolve entity references to simple refs
from the registry, (2) curate context (decide what older entities stay active with reasons),
(3) detect quick mode for simple READ-ONLY queries. NEVER invent entity refs. Think has the
raw message — you just resolve refs and curate context.
```

## User Prompt (Template) — Structural Comparison

**Structure:** IDENTICAL. Same sections, same ordering, same formatting. Same V5 header.

**Content:** ~20 kitchen-to-generic word replacements throughout. Every domain-specific noun/example was replaced with a meaningless generic placeholder.

## Exact Diffs

### Intro paragraph

| Pre-refactor | Post-refactor |
|---|---|
| "building **meal plans** over a week, refining **recipes** through iterations, tracking evolving preferences" | "building **plans** over sessions, refining **content** through iterations, tracking evolving preferences" |

### Reference Resolution table

| Pre-refactor | Post-refactor |
|---|---|
| "that recipe" -> `recipe_1` | "that item" -> `item_1` |
| "the fish one" -> ambiguous | "the first one" -> ambiguous |
| "all those recipes" -> `[recipe_1, recipe_2, recipe_3]` | "all those items" -> `[item_1, item_2, item_3]` |

### Context Curation retain_active example

| Pre-refactor | Post-refactor |
|---|---|
| `gen_meal_plan_1`, "User's ongoing weekly meal plan goal" | `gen_item_1`, "User's ongoing planning goal" |
| `recipe_3`, "Part of the meal plan being built" | `item_3`, "Part of the plan being built" |

### Quick Mode Detection table

| Pre-refactor | Post-refactor |
|---|---|
| "show my inventory" | "show my items" |
| "what recipes do I have?" | "what do I have saved?" |
| "show my shopping list" | "show my list" |
| "add milk to inventory" | "add X to my items" |
| "delete that recipe" | "delete that item" |
| "show recipes and pantry" | "show items and list" |
| "show recipe with ingredients" | "show item with details" |
| "what can I substitute for X?" | same |
| "how do I cook Y?" | "how do I do Y?" |

Quick mode warning: "cooking tips" removed, just "tips"

### Output Contract

| Pre-refactor | Post-refactor |
|---|---|
| `recipe_1`, `recipe_3`, `entity_type: "recipe"` | `item_1`, `item_3`, `entity_type: "item"` |
| `gen_meal_plan_1`, "User's ongoing meal plan" | `gen_item_1`, "User's ongoing plan" |
| "User returning to meal plan from earlier" | "User returning to plan from earlier" |

### Example 1: Clear Reference

| Pre-refactor | Post-refactor |
|---|---|
| "delete that recipe" | "delete that item" |
| `recipe_1`: Butter Chicken | `item_1`: Example Item |

### Example 2: Ambiguous Reference

| Pre-refactor | Post-refactor |
|---|---|
| "save the fish recipe" | "save the second one" |
| `recipe_1`: Honey Glazed Cod, `recipe_2`: Salmon Teriyaki | `item_1`: Item A, `item_2`: Item B |
| "Which fish recipe — Honey Glazed Cod or Salmon Teriyaki?" | "Which one — Item A or Item B?" |

### Example 3: Returning to Older Topic

| Pre-refactor | Post-refactor |
|---|---|
| "save that meal plan", gen_meal_plan_1 | "save that plan", gen_item_1 |
| Turn 3-4: "Asked about pantry" | Turn 3-4: "Asked about other data" |
| "User returning to meal plan after pantry questions" | "User returning to earlier plan after other questions" |

### Example 4: Topic Change

| Pre-refactor | Post-refactor |
|---|---|
| "what's in my shopping list?" | "what's in my list?" |
| `recipe_1`: Thai Curry, `recipe_2`: Pasta | `item_1`: Item A, `item_2`: Item B |
| "User switched from recipes to shopping" | "User switched to different subdomain" |
| `quick_subdomain: "shopping"` | `quick_subdomain: "list"` |

### Example 6: Rejection

| Pre-refactor | Post-refactor |
|---|---|
| "don't want a fish recipe now that I think about it" | "don't want that one now that I think about it" |
| `gen_recipe_1`: Thai Cod en Papillote | `gen_item_1`: Generated Item |
| "User rejected fish recipe suggestion" | "User rejected generated suggestion" |

### Key Insight paragraph

| Pre-refactor | Post-refactor |
|---|---|
| `gen_meal_plan_1`, "User's ongoing weekly plan" | `gen_item_1`, "User's ongoing plan" |

## Verdict: BROKEN

The genericized examples are worthless to the LLM. "Item A", "show my items", "that item" give zero signal about:
- What entity types exist in the domain
- How users naturally refer to entities ("that recipe", "the fish one")
- What constitutes a quick lookup vs a complex query in this domain
- Domain-specific disambiguation patterns

### What core should own (orchestration shell)
- Role: "You are Alfred's memory manager"
- Responsibilities: resolve refs, curate context, detect quick mode
- Output contract (Pydantic-enforced anyway)

### What domain should inject
- ALL examples (Butter Chicken, meal plans, shopping lists)
- Quick mode table with domain-specific entries
- Entity-type-specific reference patterns
- Curation signal examples with domain context
