# Reply Node — Prompt Regression Audit

**Pre-refactor:** `prompt_logs_downloaded/20260203_014946/13_reply.md`
**Post-refactor:** `prompt_logs/20260207_235146/07_reply.md`

## System Prompt — Header (Alfred Identity)

**IDENTICAL in both.** The "Alfred - Your Kitchen Intelligence" header is hardcoded in both:
```
# Alfred - Your Kitchen Intelligence

You are Alfred, an intelligent kitchen and pantry assistant. You help users manage
their food inventory, discover recipes, plan meals, and reduce waste.
```

This kitchen-specific identity block was NOT genericized. It comes from `domain.get_system_prompt()` which is correctly wired to KitchenConfig.

**Core Identity, What You Can Do, What You Cannot Do, Communication Style sections: IDENTICAL.**

## System Prompt — Reply Template

### `<identity>` section

| Pre-refactor | Post-refactor |
|---|---|
| Entity Context: "Saved refs (`recipe_1`) vs generated (`gen_recipe_1`)" | "Saved refs (`item_1`) vs generated (`gen_item_1`)" |
| Example: "User asked to update a recipe, but only a read happened" | "User asked to update an item, but only a read happened" |
| > "I pulled up the recipe..." | > "I pulled up the item..." |
| Frame: "Here are 5 recipes that work with your inventory" | "Here are some options" |
| Not: "I've selected these 5 recipes for your meal plan." | Not: "I've selected these for you." |

### `<subdomains>` section

**IDENTICAL in both.** All kitchen-specific subdomain formatting guides remain unchanged:
- Inventory (Pantry/Fridge/Freezer) with Milk, Eggs, Chicken examples
- Shopping List with Onions, Garlic, Chicken breast examples
- Recipes with Mediterranean Chickpea Bowl example, magazine-style format
- Meal Plans with calendar view, Air Fryer Chicken Tikka example
- Tasks with Thaw chicken, Prep vegetables examples
- Preferences with air fryer example

This is correct — the `<subdomains>` section comes from domain injection and should stay kitchen-specific.

### `<conversation>` section

**IDENTICAL.** No changes.

### `<principles>` section

| Pre-refactor | Post-refactor |
|---|---|
| "Done! Added eggs to your shopping list." | "Done! Added the items." |
| "Here's your meal plan for the week:" | "Here's your plan for the week:" |
| "Your pantry has 2 cartons of milk and 12 eggs" | "You have 2 cartons of milk and 12 eggs" |
| "Chicken expires Jan 15" | "Item expires Jan 15" |
| ✅/❌ emoji markers in tables | Removed emoji markers |
| "Want me to save this recipe?" | "Want me to save this?" |

### `<output_contract>` section

**IDENTICAL.** No changes.

### Bottom-of-prompt instruction

| Pre-refactor | Post-refactor |
|---|---|
| "If recommending a saved recipe (recipe_X), present IT" | "If recommending a saved item (item_X), present IT" |

## Verdict: MOSTLY OK

Reply is in the best shape of all nodes because:
1. **System prompt header** — correctly comes from `domain.get_system_prompt()`, stays kitchen-specific
2. **`<subdomains>` section** — correctly stays kitchen-specific (domain-injected formatting guides)
3. **`<conversation>` and `<output_contract>`** — correctly domain-neutral

**Still has ~8 genericized lines** in `<identity>` and `<principles>` that replaced recipe/meal examples with "item"/"items". These are minor but still teach the LLM less effectively.

**The key architectural win:** The Reply prompt already has the right split — kitchen identity from domain, subdomain formatting from domain, generic orchestration contract from core.
