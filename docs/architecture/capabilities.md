# Alfred Capabilities Architecture

> What Alfred can do from a user's perspective.

---

## Core Philosophy

Alfred is a **usable standalone app** with an **AI magic layer**.

| Layer | What it provides |
|-------|------------------|
| **Standalone App** | Full CRUD for kitchen data. Works without AI. |
| **AI Magic Layer** | Natural language interface that understands context and executes workflows. |

The two layers are **complementary, not dependent**. Users can:
- Use the app purely via direct UI manipulation
- Use the app purely via chat
- Mix both: make changes in UI, then ask AI to build on them

---

## API Endpoints (Frontend → Backend)

### Chat Endpoint

```
POST /api/chat
```

| Field | Type | Description |
|-------|------|-------------|
| `message` | string | User's chat message |
| `conversation_id` | string? | Existing conversation to continue |
| `ui_changes` | UIChange[]? | Entity changes made via UI since last message |
| `mentioned_entities` | MentionedEntity[]? | @-mentioned entities with full data |

**Response:**
```json
{
  "response": "string",
  "conversation": { ... },
  "entities": [ ... ]
}
```

### CRUD Endpoints

```
GET    /api/{entity_type}         # List all
GET    /api/{entity_type}/{id}    # Get one
POST   /api/{entity_type}         # Create
PUT    /api/{entity_type}/{id}    # Update
DELETE /api/{entity_type}/{id}    # Delete
```

| Entity Type | URL Segment |
|-------------|-------------|
| Recipes | `/api/recipes` |
| Inventory | `/api/inventory` |
| Shopping List | `/api/shopping` |
| Meal Plans | `/api/meal-plans` |
| Tasks | `/api/tasks` |

### Session Endpoints

```
GET  /api/conversation/status    # Check session status (active/stale/none)
POST /api/chat/reset             # Reset conversation and start fresh
```

### Onboarding Endpoints

```
POST /api/onboarding/start       # Begin onboarding
POST /api/onboarding/step        # Submit step data
POST /api/onboarding/complete    # Finalize preferences
```

### Recipe Import Endpoints

```
POST /api/recipes/import          # Extract recipe from URL, return preview
POST /api/recipes/import/confirm  # Save reviewed recipe to database
```

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
- Relations: pickers for FK references

### AI Awareness of UI Changes

```
User creates "Butter Chicken" recipe via UI
    ↓
ChatContext tracks the change
    ↓
Next chat message includes ui_changes
    ↓
AI sees: "recipe_1: Butter Chicken [created:user]"
```

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

---

## Capability 3: Natural Language Interface

The AI understands requests and executes multi-step workflows.

### Request Types

| Type | Example | AI Behavior |
|------|---------|-------------|
| **Simple query** | "What's in my inventory?" | Quick read, immediate response |
| **Content generation** | "Create a pasta recipe" | Generate, present for approval |
| **Multi-step workflow** | "Plan meals for the week" | Think → Act loop with checkpoints |
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
| **Plan** | Complex tasks | Multi-step planning with checkpoints |

---

## Capability 4: Content Generation & Approval

AI can generate new content with user approval before saving.

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

**Key Principle:** Nothing saves without approval.

---

## Capability 5: Cross-Entity Intelligence

The AI understands relationships between entities.

### Example Workflows

| Request | What AI Does |
|---------|--------------|
| "What can I make with my inventory?" | Read inventory → match recipes → present options |
| "Add ingredients for @[Butter Chicken] to shopping" | Read recipe ingredients → check inventory → add missing |
| "Plan meals for next week" | Consider preferences, inventory, recipes → generate plan |

### Entity Relationships

```
                    ingredients (canonical)
                    ↑ parent_category, family, tier, cuisines
                    │
recipes ←── recipe_ingredients ──→ ingredient_id
    ↑                                   ↓
meal_plans                          inventory → ingredient_id
    ↑                              shopping_list → ingredient_id
  tasks
```

All user-facing ingredient tables link to the canonical `ingredients` table. Enriched metadata (category, family, tier) flows into LLM context automatically via CRUD join.

---

## Capability 6: Recipe Import from URL

Users can import recipes from external websites via URL.

### Import Flow

```
1. User clicks "Import" on Recipes view
2. User pastes URL (e.g., allrecipes.com/recipe/...)
3. System extracts recipe data:
   - Try recipe-scrapers (400+ sites)
   - Fall back to JSON-LD/Schema.org
4. Preview shown with editable fields
5. User reviews/edits, clicks Save
6. Recipe + ingredients saved to database
```

### LLM Ingredient Parsing

Raw ingredient strings are parsed into structured data:

| Raw String | Parsed Result |
|------------|---------------|
| "2 cloves garlic, minced" | name: garlic, qty: 2, unit: clove, notes: minced |
| "salt, to taste" | name: salt, notes: to taste, is_optional: false |
| "parsley (optional)" | name: parsley, notes: for garnish, is_optional: true |

**Key Rules:**
- "to taste" ≠ optional (flexible amount, still required)
- Only explicit "optional", "if desired" triggers `is_optional: true`
- Prep instructions (minced, diced) go in `notes`, not `name`

### Ingredient Linking

Parsed ingredients are linked to the master ingredients database:
- `lookup_ingredient()` matches canonical names
- `ingredient_id` stored for future nutrition/inventory integration
- Unmatched ingredients saved without link (graceful degradation)

### Fallback Behavior

If extraction fails:
- User sees fallback message with chat suggestion
- User can paste recipe text in chat for manual parsing

---

## Implementation Status

| Capability | Status |
|------------|--------|
| Direct CRUD via UI | Complete |
| UI changes → AI context | Complete |
| @-mention autocomplete | Complete |
| @-mention → AI context | Complete |
| Natural language interface | Complete |
| Content generation | Complete |
| Cross-entity intelligence | Complete |
| Recipe import from URL | Complete |

### Recently Added

| Capability | Description |
|------------|-------------|
| Ingredient Enrichment | Canonical ingredients with parent_category, family, tier, cuisines. Auto-joined into LLM context. See [spec](../specs/ingredient-enrichment.md). |
| Recipe Import from URL | Import recipes from 400+ sites with LLM ingredient parsing |
| Session Resume Prompt | After 30 min inactivity, prompt to resume or start fresh |
| Inline Progress Display | Real-time visibility into AI execution: phases, tool calls, context updates |
| AI Context Transparency | Entity badges showing what AI read/created during each step |
| Entity Display Summarization | Bulk entities (inventory >5 items) collapsed to summary chip with VIEW link. See [spec](../specs/streaming-ux.md). |
| Progressive Plan Reveal | Steps appear one-by-one as they execute, not all at once |
| Collapsible Reasoning | Reasoning trace preserved in message bubble, collapsed by default |

### Future Capabilities

| Capability | Description |
|------------|-------------|
| Chat History on Resume | Load and display prior messages when resuming session |
| Multi-Conversation History | Sidebar with conversation list, pins, search |
| Persistent Context Bar | Always-visible context panel (current: inline per-message) |
| Pin/Unpin Entities | User control over AI context retention |
| Voice Input | Speak requests instead of typing |
| Notifications | Proactive reminders |
