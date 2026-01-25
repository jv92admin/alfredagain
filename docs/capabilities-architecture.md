# Alfred Capabilities Architecture

> **Scope:** This document describes *what* Alfred can do from a user's perspective. For *how* the AI works internally, see `architecture_overview.md` and `context-engineering-architecture.md`.

## Core Philosophy

Alfred is a **usable standalone app** with an **AI magic layer**.

| Layer | What it provides |
|-------|------------------|
| **Standalone App** | Full CRUD for kitchen data (recipes, inventory, shopping, meals, tasks). Works without AI. |
| **AI Magic Layer** | Natural language interface that understands context, generates content, and executes multi-step workflows. |

The two layers are **complementary, not dependent**. Users can:
- Use the app purely via direct UI manipulation
- Use the app purely via chat (AI handles everything)
- Mix both: make changes in UI, then ask AI to build on them

---

## Capability 1: Direct CRUD via UI

Users can create, read, update, and delete all entities through dedicated views.

### Supported Entities

| Entity | Key Fields | Special UI Components |
|--------|------------|----------------------|
| **Recipes** | name, description, ingredients[], steps[] | IngredientsEditor, StepsEditor |
| **Inventory** | name, quantity, unit, expiry_date | — |
| **Shopping List** | name, quantity, unit, checked | — |
| **Meal Plans** | date, meal_type, recipe_id | RecipePicker |
| **Tasks** | title, description, due_date, completed | RecipePicker, MealPlanPicker |

### Schema-Driven Forms

All entity forms are generated from a shared schema system:
- Field types: text, number, date, boolean, select, relation
- Validation: required fields, min/max constraints
- Relations: pickers for FK references (e.g., recipe in meal plan)

### AI Awareness of UI Changes

When users make changes via UI, the AI learns about them:

```
User creates "Butter Chicken" recipe via UI
    ↓
ChatContext tracks the change
    ↓
Next chat message includes ui_changes
    ↓
AI sees: "recipe_1: Butter Chicken [created:user]"
```

This enables natural conversations like:
- User: *creates recipe via form*
- User: "Add the ingredients from that recipe to my shopping list"
- AI: *knows about recipe_1, executes correctly*

---

## Capability 2: @-Mention Entity References

Users can explicitly reference entities in chat using `@` mentions.

### User Flow

```
1. User types "@" in chat input
2. Autocomplete dropdown appears (grouped by type)
3. User searches/selects entity
4. Mention inserted: @[Butter Chicken](recipe:uuid-123)
5. AI receives full entity data in context
```

### Why @-Mentions Matter

| Without @-mention | With @-mention |
|-------------------|----------------|
| "Update the chicken recipe" — which one? | "@[Butter Chicken] — add more garlic" |
| AI must search/guess | AI has exact entity + full data |
| Ambiguity, errors | Precise execution |

### Entity Types Available

| Type | Icon | Searchable Field |
|------|------|------------------|
| recipe | 🍳 | name |
| inv (inventory) | 📦 | name |
| shop (shopping) | 🛒 | name |
| task | ✅ | title |

---

## Capability 3: Natural Language Interface

The AI understands requests and executes multi-step workflows.

### Request Types

| Type | Example | AI Behavior |
|------|---------|-------------|
| **Simple query** | "What's in my inventory?" | Quick read, immediate response |
| **Content generation** | "Create a pasta recipe" | Generate, present for approval |
| **Multi-step workflow** | "Plan meals for the week using my inventory" | Think → Act loop with checkpoints |
| **Entity manipulation** | "Add eggs to shopping list" | Direct CRUD execution |

### Context Awareness

The AI maintains awareness of:
- **Recent entities** — Items read/created in last 2 turns
- **Generated content** — Recipes/plans created but not yet saved
- **User actions** — What the user did via UI between messages
- **Conversation history** — Compressed summary of prior turns

### Two Interaction Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Quick** | Simple requests | Single tool call, fast response |
| **Plan** | Complex tasks | Multi-step planning with user checkpoints |

---

## Capability 4: Content Generation & Approval

AI can generate new content (recipes, meal plans) with user approval before saving.

### Generation Flow

```
User: "Create a quick weeknight pasta recipe"
    ↓
AI generates recipe (stored as gen_recipe_1)
    ↓
AI presents recipe for review
    ↓
User: "Looks good, save it" OR "Make it vegetarian"
    ↓
AI saves or modifies accordingly
```

### Key Principle: Nothing Saves Without Approval

- Generated content is **pending** until user confirms
- User can request modifications before saving
- User can reject entirely

---

## Capability 5: Cross-Entity Intelligence

The AI understands relationships between entities and can work across them.

### Example Workflows

| Request | What AI Does |
|---------|--------------|
| "What can I make with my inventory?" | Reads inventory → matches to recipes → presents options |
| "Add ingredients for @[Butter Chicken] to shopping" | Reads recipe ingredients → checks inventory → adds missing to shopping |
| "Plan meals for next week" | Considers preferences, inventory, recipes → generates meal plan |
| "Create a task to prep for Sunday dinner" | Links task to meal plan, sets appropriate due date |

### Entity Relationships

```
recipes ←── recipe_ingredients ──→ ingredients
    ↑                                   ↓
meal_plans                          inventory
    ↑                              shopping_list
  tasks
```

---

## Implementation Status

| Capability | Status | Notes |
|------------|--------|-------|
| Direct CRUD via UI | ✅ Complete | All entities, schema-driven forms |
| UI changes → AI context | ✅ Complete | `pushUIChange()` + `register_from_ui()` |
| @-mention autocomplete | ✅ Complete | Grouped dropdown, keyboard nav |
| @-mention → AI context | ✅ Complete | Full entity data injection |
| Natural language interface | ✅ Complete | Understand → Think → Act → Reply |
| Content generation | ✅ Complete | `gen_*` refs, approval flow |
| Cross-entity intelligence | ✅ Complete | FK resolution, semantic search |

### Future Capabilities (Not Yet Built)

| Capability | Description |
|------------|-------------|
| **Context Bar UI** | Visual display of what AI currently knows about |
| **Pin/Unpin Entities** | User control over AI context retention |
| **Voice Input** | Speak requests instead of typing |
| **Notifications** | Proactive reminders (expiring items, meal prep) |

---

## Related Documentation

| Document | Focus |
|----------|-------|
| `architecture_overview.md` | LLM pipeline, node responsibilities |
| `context-engineering-architecture.md` | Context management, state vs context |
| `session-id-registry-spec.md` | Entity ref system, UUID translation |
