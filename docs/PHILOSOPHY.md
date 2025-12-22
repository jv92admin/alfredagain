# Alfred V2 - Design Philosophy & Entity Intent

> Core philosophy for agent behavior and the intent behind each data entity.

---

## Part 1: Agent Philosophy

### The Switchboard Operator Principle

From v1's Top-Level Planner constitution (adapted for v2):

> Think of yourself as an expert **switchboard operator**. Your only goal is to get the user to the correct specialist (agent) as quickly and efficiently as possible.

**Key principles:**
- **Success is fast, correct routing** - Get to the right agent quickly
- **Specialists expect ambiguity** - Domain agents are experts; trust them
- **Clarification is failure** - Asking for details that specialists can handle slows users down

**v2 application:** The Router node should route, not interrogate. If we know the domain, send it there.

---

### Trust the Model

From v1 lessons learned:

> We had 261 examples across 7 JSONL files. Modern models don't need this hand-holding.

**Key principles:**
- Clear instructions > many examples
- 5-10 well-chosen examples max
- Let the model reason; don't over-constrain
- Use structured outputs to guarantee format, not to limit thinking

**v2 application:** Agent prompts should be short, clear, and trust the model to figure out details.

---

### Flair, Not Fabrication

From v1's Synthesizer constitution:

> You have creative freedom in **presentation**, but **zero freedom in facts.**

**Key principles:**
- Every detail must be grounded in actual data
- Flair is in phrasing and formatting, not inventing content
- Never hallucinate quantities, ingredients, or steps
- If generation fails, admit it rather than making things up

**v2 application:** The Reply node has personality but strict factual grounding.

---

### The Pantry Personality

From v1's Synthesizer constitution:

> When responding for the Pantry agent, you are a world-class **Chef's Assistant and Kitchen Manager** with the warmth of a food blogger and the precision of a sous chef.

**Your Culinary Persona:**
- **Think like a recipe blogger** - Inspire with beautiful descriptions
- **Act like a friend in the kitchen** - Warm, encouraging, genuinely helpful
- **Maintain accuracy of a sous chef** - Precise with measurements and timing
- **Anticipate needs** - Suggest prep tips, storage advice, seasonal alternatives

**Example voice:**
- Not: "Added 2 apples to inventory"
- But: "I've added 2 Honeycrisp apples to your pantry - they'll stay crisp for about 2 weeks"

---

### High-Friction vs Low-Friction Operations

From v1's Domain Planner constitution:

**High-Friction (require user review):**
- `recipes` - Complex recipes need user approval
- `meal_plans` - Scheduling conflicts need user awareness

**Low-Friction (auto-upsert allowed):**
- `inventory` - Safe to add/update automatically
- `flavor_preferences` - Safe to create/update automatically
- `shopping_list` - Operational data, safe to modify

**v2 application:** Auto-upsert triggers should only fire for low-friction entities.

---

### Multi-Vault Coordination Intelligence

From v1's Domain Planner constitution:

When users express preferences or make changes, coordinate across related entities:

**Example: "I hate Brussels sprouts" during recipe discussion**
→ Two operations:
1. Update `flavor_preferences`: Brussels sprouts = -1.0
2. Modify the current recipe: Replace Brussels sprouts

**Example: "Save this recipe and add it to Tuesday dinner"**
→ Two operations:
1. Add to `recipes`: Save the recipe
2. Add to `meal_plans`: Schedule for Tuesday

**v2 application:** The Planner node should recognize multi-entity intents and plan accordingly.

---

## Part 2: Entity Intent Documentation

### Entity Relationship Map

```
PANTRY DOMAIN ENTITIES
══════════════════════

┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   ingredients   │◀────▶│     recipes     │◀────▶│   meal_plans    │
│    (master)     │      │                 │      │                 │
│                 │      │                 │      │                 │
│ • Canonical list│      │ • How to make   │      │ • What to eat   │
│ • Seeded + user │      │ • System + user │      │ • Date-based    │
│ • Has nutrition │      │ • Has embeddings│      │ • Links recipes │
│ • Has flavor    │      │ • Has variants  │      │                 │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│    inventory    │      │     flavor      │      │  shopping_list  │
│   (user's)      │      │  preferences    │      │                 │
│                 │      │                 │      │                 │
│ • What user HAS │      │ • What user     │      │ • What to BUY   │
│ • Quantities    │      │   LIKES/hates   │      │ • From meal plan│
│ • Expiry dates  │      │ • Learned over  │      │ • Or manual     │
│ • Locations     │      │   time          │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘

MEMORY ENTITIES
═══════════════

┌─────────────────┐      ┌─────────────────┐
│  conversation   │      │   preferences   │
│     memory      │      │    (user)       │
│                 │      │                 │
│ • Past context  │      │ • Dietary       │
│ • Vector search │      │ • Allergies     │
│ • Expires       │      │ • Skill level   │
│                 │      │ • Household     │
└─────────────────┘      └─────────────────┘
```

---

### Entity Definitions

#### `ingredients` (Master Registry)

**Intent:** Canonical list of all known ingredients across the system.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Every ingredient Alfred knows about |
| **Seeded from** | Open Food Facts, Spoonacular |
| **User additions** | When recipes reference unknown ingredients |
| **Key fields** | name, aliases, category, nutrition, flavor_compounds, embedding |
| **Used by** | inventory (references), recipes (references), shopping_list |

**Design decisions:**
- `is_system` flag distinguishes seeded vs user-added
- `aliases` array enables "eggplant" = "aubergine" = "brinjal"
- Embeddings enable semantic search ("something like chicken")

---

#### `inventory` (User's Stock)

**Intent:** What the user actually HAS in their kitchen right now.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Current quantities of ingredients user owns |
| **References** | Links to `ingredients` via ingredient_id |
| **Key fields** | name (denormalized), quantity, unit, location, expiry_date |
| **Mutations** | Add (purchase), Remove (use/waste), Update (adjust) |

**Design decisions:**
- `ingredient_id` links to master for cross-references
- `name` is denormalized for fast queries (no join needed for display)
- `expiry_date` enables proactive alerts
- `location` (fridge/pantry/freezer) for organization

---

#### `recipes` (How to Make Things)

**Intent:** Instructions for preparing dishes, both system-seeded and user-created.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Complete recipe definitions |
| **Seeded from** | Spoonacular (500+ popular recipes) |
| **User additions** | Generated recipes user saves, manual entries |
| **Key fields** | name, ingredients (via junction), instructions[], embedding |
| **Used by** | meal_plans (references), shopping_list (generates from) |

**Design decisions:**
- `recipe_ingredients` junction table with quantities
- `instructions` as TEXT[] for step-by-step
- `embedding` enables semantic search ("something like tikka masala")
- `is_system` distinguishes seeded vs user recipes
- `source_url` for imported recipes

---

#### `meal_plans` (What to Eat When)

**Intent:** User's scheduled meals, organized by date.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Date + meal_type + recipe assignments |
| **Key fields** | date, meal_type (breakfast/lunch/dinner/snack), recipe_id, notes |
| **Generates** | Shopping lists (diff against inventory) |
| **Used by** | Proactive suggestions ("you can make X tonight") |

**Design decisions:**
- Date-based keys (not "monday" - that's ambiguous)
- `recipe_id` references recipes table
- `servings` for quantity adjustments
- Can have notes for variations ("extra spicy")

---

#### `shopping_list` (What to Buy)

**Intent:** Items user needs to purchase.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Ingredients to buy with quantities |
| **Generated from** | meal_plan ingredients - inventory = shopping list |
| **Key fields** | ingredient_id, name, quantity, unit, category, is_purchased |
| **Used by** | Inventory (purchased items get added) |

**Design decisions:**
- `source` field tracks origin (meal_plan, manual, auto_restock)
- `category` for grouping in store (produce, dairy, etc.)
- `is_purchased` for checking off items

---

#### `preferences` (User Dietary Profile)

**Intent:** User's dietary constraints and cooking context.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Dietary restrictions, allergies, skill level, household size |
| **Key fields** | dietary_restrictions[], allergies[], favorite_cuisines[], cooking_skill_level |
| **Used by** | Recipe generation, meal planning, substitution suggestions |

**Design decisions:**
- Always injected into agent context (small, always relevant)
- One row per user (UNIQUE constraint)
- Arrays for multi-value preferences

---

#### `flavor_preferences` (Learned Tastes)

**Intent:** What the user likes/dislikes, learned over time.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Per-ingredient preference scores |
| **Key fields** | ingredient_id, preference_score (-1 to 1), times_used |
| **Learned from** | Usage patterns, explicit feedback |
| **Used by** | Recipe suggestions, substitution choices |

**Design decisions:**
- Score range: -1 (hate) to 0 (neutral) to +1 (love)
- `times_used` tracks engagement
- Auto-updates via triggers on inventory/meal_plan changes

---

#### `conversation_memory` (Long-term Recall)

**Intent:** Facts and context Alfred should remember across sessions.

| Aspect | Description |
|--------|-------------|
| **What it stores** | Memorable facts, preferences, events |
| **Key fields** | content, memory_type, embedding, expires_at |
| **Retrieved via** | Vector similarity search on user query |
| **Used by** | Router node injects relevant memories into context |

**Design decisions:**
- `memory_type` categorizes (preference, fact, event, feedback)
- `expires_at` allows temporary memories
- Embeddings enable semantic retrieval

---

## Part 3: Cross-Entity Patterns

### Pattern: Recipe → Shopping List Generation

```
1. Get recipes from meal_plan for date range
2. Aggregate all recipe_ingredients
3. Subtract current inventory quantities
4. Remaining items → shopping_list
```

### Pattern: Ingredient Preference Learning

```
1. User adds ingredient to inventory → flavor_preferences += 0.1
2. User uses ingredient in meal_plan → flavor_preferences += 0.2
3. User wastes ingredient (removed unused) → flavor_preferences -= 0.1
4. User says "I hate X" → flavor_preferences = -1.0
```

### Pattern: Proactive Suggestion Generation

```
1. Check inventory for expiring items (expiry_date < today + 3)
2. Check recipes that use those ingredients
3. Check if user has other required ingredients
4. Surface: "Your milk expires tomorrow - make French toast!"
```

### Pattern: Cross-Domain Memory

```
1. Coach agent learns: "User training for marathon"
2. Memory stored with tags: {agent: "coach", type: "goal"}
3. Pantry agent queries memories for meal planning
4. Surfaces: "High-carb meal recommended for your training"
```

---

## Summary

**Core philosophy:**
1. Route fast, don't interrogate
2. Trust the model with clear instructions
3. Flair in presentation, facts from data
4. Coordinate across entities intelligently
5. Learn preferences passively over time

**Entity design:**
1. Master registries (ingredients) + user instances (inventory)
2. References via IDs, denormalized names for speed
3. Embeddings on searchable entities
4. Date-based organization for temporal data
5. Separation of system (seeded) vs user data


