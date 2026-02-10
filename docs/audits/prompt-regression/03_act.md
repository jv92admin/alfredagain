# Act Node — Prompt Regression Audit

**Pre-refactor:** `prompt_logs_downloaded/20260203_014946/08_act.md` (read step, inventory subdomain)
**Post-refactor:** `prompt_logs/20260207_235146/03_act.md` (read step, meal_plans subdomain)

Note: Different subdomains and step types were executed, so the dynamic user-prompt portions (schema, step context) differ naturally. The comparison focuses on the **system prompt template** which is the same across all Act invocations.

## System Prompt — Core Act Template

### Structure
Both have identical sections: Role, Core Principles, Actions table, Exit Contract, CRUD Tools Reference, Filter Syntax, Schema note, READ Step guidance, Execute Think's Intent, Entity Context, How to Execute, Complete Example, Entity IDs, Advanced Patterns, Principles.

### Diffs in Core Template

| Section | Pre-refactor | Post-refactor |
|---|---|---|
| Core Principle #2 | "generate = create content (recipes, meal plans, etc.)" | "generate = create content (domain-specific items)" |
| Core Principle #2 | "save generated recipe" | "save generated content" |
| Core Principle #9 | "`recipe_1`, `inv_5`, `gen_recipe_1`" | "`item_1`, `item_5`, `gen_item_1`" |
| Blocked example | "save gen_recipe_1" | "save gen_item_1" |
| Exit Contract example | "Created recipe and 5 ingredients" | "Created item and 5 linked records" |
| Exit Contract note | "Recipe ID abc123 created" | "Item ID abc123 created" |
| Filter example | `recipe_1`, `recipe_2`, `recipe_5` | `item_1`, `item_2`, `item_5` |
| is_null example | `expiry_date` | `due_date` |
| Simple refs note | "`recipe_1`, `inv_5`" | "`item_1`, `item_5`" |

### READ Step Section — Significant Structural Change

**Pre-refactor** had kitchen-specific content INLINE in the core template:
```
| "Read saved recipes" | Read ALL recipes |
| "Read recipes matching 'chicken'" | Filter by name ilike %chicken% |
| "Read user's inventory" | Read ALL inventory items |
| "Read what's in my pantry" | Read ALL inventory items |
```
Plus "Broader Intent Before Filtering" section with pantry/fridge/freezer examples.

**Post-refactor** split this into two parts:
1. **Generic core template** — simplified Think intent table:
   ```
   | "Read all items" | Read ALL items |
   | "Read items matching 'X'" | Filter by name ilike %X% |
   | "Read user's data" | Read ALL rows |
   ```
2. **"Kitchen-Specific Read Patterns" section** — appended AFTER the generic template, containing:
   - Broader Intent Before Filtering (pantry/fridge/freezer)
   - Think Intent Examples (recipes, inventory)
   - Semantic Search (Recipes only)
   - Kitchen-Specific Notes (tags, instructions, occasions)

**This is actually a reasonable split** — the core template is generic, and kitchen-specific patterns are injected. However, the generic examples ("Read all items", "Read user's data") are useless placeholders.

### Advanced Patterns — Semantic Search

**Pre-refactor:** Semantic search section in core template with recipes-specific example.
**Post-refactor:** Semantic search REMOVED from core template, moved to "Kitchen-Specific Read Patterns" injection.

### Advanced Patterns — Other

| Pre-refactor | Post-refactor |
|---|---|
| OR Logic: `recipes` table, `%chicken%`, `%rice%` | OR Logic: `items` table, `%keyword1%`, `%keyword2%` |
| Date Range: `meal_plans` table | Date Range: `events` table |
| Array Contains: `occasions` | Array Contains: `tags` |
| Note about `tags` field | REMOVED from core (moved to kitchen injection) |
| Principle #6: "For recipes: only fetch `instructions`..." | "Only fetch verbose fields if step explicitly needs them" |

### Complete Example

| Pre-refactor | Post-refactor |
|---|---|
| `table: "recipes"`, `name ilike %chicken%` | `table: "items"`, `name ilike %keyword%` |
| Entity IDs: `recipe_1`, `recipe_2`, `recipe_5`, `recipe_6` | Entity IDs: `item_1`, `item_2`, `item_5`, `item_6` |

## User Prompt (Dynamic Injection)

Different subdomains so naturally different. But the structure is the same:
- Domain description + persona
- Smart search patterns (pre) or Kitchen-Specific Read Patterns (post)
- Schema tables
- Filter syntax (duplicated from system prompt)
- Field enums
- Examples
- STATUS section
- Task description
- Step History
- Entities in Context
- Context (conversation)
- DECISION prompt

## Verdict: MIXED

The Act node is the LEAST broken of the genericized nodes because:
1. The core/domain split is architecturally reasonable (generic template + kitchen injection section)
2. The kitchen-specific content (semantic search, pantry interpretation, recipe-specific notes) was properly separated into an injection section labeled "Kitchen-Specific Read Patterns"
3. The dynamic user prompt (schema, domain description, examples) comes from domain injection and is still kitchen-specific

**Still broken:**
- The core template examples are useless ("Read all items", `item_1`, `events` table)
- These should either be genuinely domain-neutral structural examples OR omitted
- The domain should inject its own examples in the injected section
