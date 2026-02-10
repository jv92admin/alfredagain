# Think Node — Prompt Regression Audit

**Pre-refactor:** `prompt_logs_downloaded/20260203_014946/07_think.md`
**Post-refactor:** `prompt_logs/20260207_235146/02_think.md`

## System Prompt

Think is the biggest prompt — the system prompt IS the entire Think template. Both are structured identically with XML sections: `<identity>`, `<precedence>`, `<alfred_context>`, `<understanding_users>`, `<system_structure>`, `<conversation_management>`, `<session_context>`, `<conversation_history>`, `<immediate_task>`, `<output_contract>`.

## Section-by-Section Diff

### `<identity>` — Core principle

| Pre-refactor | Post-refactor |
|---|---|
| "Your first response to **'plan my meals'** might just be aligning on preferences" | "Your first response to **a complex request** might just be aligning on preferences" |
| "add **eggs**" doesn't need analysis | "add **X**" doesn't need analysis |

### `<alfred_context>` — What Alfred Enables

**IDENTICAL in both.** Still says kitchen-specific content:
- "Alfred helps users build a personalized kitchen system"
- "Their recipes", "Their pantry", "Their rhythm", "Their plans"
- "Efficient planning enables delicious cooking"
- "batch cooking", "few cuisines per week"
- "catalogs their experiments", "cooking becomes possible"

**This is the ONE section that was NOT genericized.** It stayed kitchen-specific in both versions. This is actually correct — this section SHOULD come from the domain. But it being hardcoded in the core template means it would break for a non-kitchen domain.

### `<understanding_users>` — Know the User

| Pre-refactor | Post-refactor |
|---|---|
| "diet, equipment, skill, cooking rhythm" | "constraints, equipment, skill level" |
| "pantry contents, saved recipes, existing plans" | "what's in their system, saved items, existing plans" |
| "use you ablitites" (typo) | "use your abilities" (fixed typo) |

### `<system_structure>` — How Alfred Works

#### Subdomains table
**IDENTICAL.** Both list: inventory, shopping, recipes, meal_plans, tasks, preferences.
This is kitchen-specific content that stayed in both versions.

#### Linked Tables
**IDENTICAL.** Both describe recipe_ingredients, ingredient backbone, meal_plan_items.
All kitchen-specific, stayed in both.

#### Recipes (Complex Domain)
**IDENTICAL.** Both describe recipe workflow patterns, iteration, etc.

#### Meal Plans (Complex Domain)
**IDENTICAL.** Both describe operational hub, leftover chains, permutations.

**Post-refactor REMOVED these sections that were in pre-refactor:**
- The "What Act Does" subsection was moved/restructured
- "Category-based recipe searches: Act has semantic search" — moved to a one-liner
- Several detailed examples with `recipe_1`, `gen_recipe_1`, `inv_5` refs

#### Step Types table

| Pre-refactor | Post-refactor |
|---|---|
| `generate`: "Creates new content (recipe, meal plan draft)" | `generate`: "Creates new content" |

#### Batch writes examples

| Pre-refactor | Post-refactor |
|---|---|
| "Add all 14 inventory items from receipt" | "Add all 14 items from the list" |
| "Add shopping list items (chicken, rice, peppers)" | "Add items (A, B, C)" |

#### Passing Intent to Act

| Pre-refactor | Post-refactor |
|---|---|
| "Find recipes that work with expiring chicken" | "Find items that match the criteria" |
| "Draft a meal plan for the week" | "Draft a plan for the week" |
| "Check what's running low" | same |
| "Find fish recipes" | REMOVED |
| "Category-based recipe searches: Act has semantic search" | REMOVED from this section |

#### Entity Types table

| Pre-refactor | Post-refactor |
|---|---|
| `recipe_1`, `inv_5`, `meal_3` | `item_1`, `item_5` |
| `gen_recipe_1`, `gen_meal_1` | `gen_item_1`, `gen_item_2` |

#### Context Layers

| Pre-refactor | Post-refactor |
|---|---|
| "**Kitchen Snapshot** (in 'KITCHEN SNAPSHOT')" | "**Dashboard** (in 'DASHBOARD')" |
| "counts, cuisines, what exists" | "counts, categories, what exists" |

#### When to Read vs Analyze table

| Pre-refactor | Post-refactor |
|---|---|
| `gen_recipe_1`, `recipe_1`, `recipe_5` | `gen_item_1`, `item_1`, `item_5` |
| "Kitchen Snapshot shows recipes" | "Dashboard shows items" |

#### Multi-entity operations

Pre-refactor had detailed table:
```
| "What ingredients am I missing?" | Recipe + Inventory | Both in context? |
| "Compare this recipe with that one" | Recipe A + Recipe B | Both available? |
| "Match recipes to my pantry" | Recipes + Inventory | Both loaded? |
```
Post-refactor: **REMOVED** the table, just says "verify ALL sources are in context"

Pre-refactor had a full example:
```json
{"steps": [
  {"description": "Read current inventory", ...},
  {"description": "Compare gen_recipe_1 ingredients with inventory", ...}
]}
```
Post-refactor: **REMOVED** this example entirely.

#### gen_* show/read exception

Pre-refactor had a detailed explanation + table. Post-refactor kept the table but condensed the explanation.

#### Modifying + Saving Generated Content

Pre-refactor had kitchen-specific example:
```json
{"steps": [
  {"description": "Modify gen_recipe_1 to add lime finish", "step_type": "generate", "subdomain": "recipes"},
  {"description": "Save gen_recipe_1", "step_type": "write", "subdomain": "recipes"}
]}
```
Post-refactor: **REMOVED** this example. Generic table kept but less specific.

#### Recipe Data Levels
**IDENTICAL positioning** in both. Still kitchen-specific (recipe reads, instructions, ingredients).

#### Updates Need Two Steps

Pre-refactor had kitchen example:
```
Step 1 (read): "Read recipe_5 with instructions and ingredients"
Step 2 (write): "Update recipe_5: change gai lan to broccoli, update chef's note"
```
Post-refactor: **REMOVED** the example, just says "Act handles the actual CRUD operation."

### `<conversation_management>` — Managing the Conversation

#### Conversation Before Planning

| Pre-refactor | Post-refactor |
|---|---|
| "Plan my meals" → propose: "How many days? Batch-cooking?" | "Complex open-ended task" → propose: "Align on scope" |
| "Help me use this chicken" → plan_direct | "Specific request with context" → plan_direct |
| "What's in my fridge" → plan_direct | "Simple lookup" → plan_direct |

Kitchen examples replaced with abstract descriptions.

#### Iterative Workflows

| Pre-refactor | Post-refactor |
|---|---|
| "read recipes, analyze options" | "read data, analyze options" |
| "Here are some options based on your inventory" | "Here are some options based on your data" |
| Detailed 8-step meal plan workflow | REMOVED |

#### Don't One-Shot Complex Tasks

| Pre-refactor | Post-refactor |
|---|---|
| "Week meal plan" / "Recipe creation" / "Shopping list" | "Complex plan" / "Content creation" / "List building" |
| "Which cuisines are you feeling this week?" | "What are your priorities?" |
| "I see you have chicken and Thai ingredients" | "I see what you have" |
| "Based on your meal plan, here's what you need" | "Based on your plan, here's what you need" |

#### Human-in-the-Loop

| Pre-refactor | Post-refactor |
|---|---|
| "For meal planning especially:" | "For complex planning especially:" |
| "Recipe selection", "Day assignment", "Adjustments" with details | Generic "Selection", "Scheduling", "Adjustments" |

#### Checkpoints

| Pre-refactor | Post-refactor |
|---|---|
| "After reading recipes → 'Which of these interest you?'" | "After reading data → 'Which of these interest you?'" |
| "After analyzing options → 'Here's what works with your inventory'" | "After analyzing options → 'Here's what works'" |
| "After generating draft → 'Does this schedule work?'" | "After generating draft → 'Does this work?'" |

#### Post-Action Awareness

Pre-refactor had detailed table:
```
| "I cooked [recipe]" | Update inventory, iterate on recipe |
| "I went shopping" | Update inventory from shopping list |
| "That was great!" | Save recipe, add to rotation |
| "I didn't make it" | Reschedule, swap recipe |
```
Post-refactor: **REMOVED** the table entirely. Just says "Use propose to surface 1-2 natural follow-ups."

### `<output_contract>` — Your Response

#### plan_direct example

| Pre-refactor | Post-refactor |
|---|---|
| "Show recipe options for the week" | "Show options based on available data" |
| "Read saved recipes" subdomain: "recipes" | "Read saved items" subdomain: "items" |
| "Read current inventory" subdomain: "inventory" | "Read current data" subdomain: "data" |
| "Identify which recipes work with available ingredients" | "Identify which items work with available data" |

#### propose example

| Pre-refactor | Post-refactor |
|---|---|
| "Plan meals for the week" | "Plan items for the week" |
| "9 saved recipes and some chicken and cod that could use some love" | "some saved items and some data to work with" |

#### clarify example

| Pre-refactor | Post-refactor |
|---|---|
| "Help with dinner party" | "Help with a complex task" |
| "menu ideas, a shopping list, or prep planning?" | "ideas, a list, or planning?" |

#### Tone guidance

| Pre-refactor | Post-refactor |
|---|---|
| "whats in my pantry" → Just execute | "Simple lookup" → Just execute |
| "i want to create recipes for next week" | "Open-ended creative task" |
| "hosting people this weekend" | "Event/occasion" |
| "just cooked that, it was great!" → "save it or update your pantry?" | "Post-action" → "save it or update your data?" |

## Verdict: BROKEN (Severely)

Think is the most critical prompt — it's the "brain" that plans all actions. The genericization is far more damaging here than in Understand because:

1. **`<alfred_context>` was NOT genericized** — it still says "kitchen system", "recipes", "pantry", "cooking". This is inconsistent: the examples say "items" but the context says "recipes."

2. **Kitchen-specific system_structure was partially genericized** — Subdomains table, Linked Tables, Recipes, Meal Plans sections are STILL kitchen-specific. But examples within those sections were genericized. The LLM now reads "inventory, shopping, recipes, meal_plans" in the subdomains table but sees `item_1`, `gen_item_1` in the examples.

3. **Critical examples were REMOVED entirely:**
   - Multi-entity operation table (recipe + inventory cross-check)
   - 8-step iterative meal plan workflow
   - Post-action awareness table (cooked, shopped, etc.)
   - gen_recipe modification example
   - Update recipe example (gai lan → broccoli)
   - Semantic search mention for recipe discovery

4. **The inconsistency is worse than either extreme.** Half kitchen, half generic = the LLM gets confused signals about what domain it's operating in.

### What core should own
- `<identity>` (orchestration role, hard rules)
- `<precedence>` (conflict resolution)
- `<output_contract>` structure (Pydantic-enforced)
- Generic step type definitions (read/write/analyze/generate)
- Generic context layer definitions (active/long-term/generated)

### What domain should inject
- `<alfred_context>` entirely (philosophy, what Alfred enables)
- `<system_structure>` — subdomains, linked tables, complex domain descriptions, workflow patterns, all examples
- `<conversation_management>` — domain-specific conversation patterns, checkpoints, post-action table, iterative workflow examples
- `<output_contract>` examples (plan_direct, propose, clarify with domain context)
