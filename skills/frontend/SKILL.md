# Frontend Skill

> **Scope:** UI development — React components, API consumption, design patterns

This skill applies when working on the React frontend, component development, or UI/UX implementation.

---

## Technology Stack

- **React 19** + TypeScript
- **Vite** for bundling
- **TailwindCSS v4** for styling
- **Framer Motion** for animations
- **React Router** for navigation
- **Supabase JS** for auth and data

---

## Project Structure

```
frontend/src/
├── components/
│   ├── Chat/           # Chat interface
│   ├── Form/           # Schema-driven forms
│   ├── Views/          # Entity CRUD views
│   ├── Focus/          # Detail overlays
│   ├── Onboarding/     # User setup flow
│   ├── Auth/           # Login
│   └── Layout/         # App shell
├── context/            # React Context providers
├── hooks/              # Custom hooks
└── lib/                # Utilities
```

---

## API Consumption

### Chat Endpoint

```typescript
POST /api/chat
Body: {
  message: string,
  conversation_id?: string,
  ui_changes?: UIChange[]
}
Response: {
  response: string,
  conversation: object,
  entities?: object[]
}
```

### CRUD Endpoints

```typescript
GET    /api/{entity_type}         // List all
GET    /api/{entity_type}/{id}    // Get one
POST   /api/{entity_type}         // Create
PUT    /api/{entity_type}/{id}    // Update
DELETE /api/{entity_type}/{id}    // Delete
```

Entity types: `recipes`, `inventory`, `shopping`, `meal-plans`, `tasks`

### Auth Header

All requests include: `Authorization: Bearer <supabase_token>`

---

## Component Patterns

### Schema-Driven Forms

Forms are generated from shared entity schemas:

| File | Purpose |
|------|---------|
| `Form/FieldRenderer.tsx` | Renders field by type (text, number, date, select, relation) |
| `Form/EntityForm.tsx` | Wraps fields with validation and submit |
| `Form/pickers/RecipePicker.tsx` | FK picker for recipes |
| `Form/pickers/MealPlanPicker.tsx` | FK picker for meal plans |
| `Form/editors/IngredientsEditor.tsx` | Multi-row ingredient editor |
| `Form/editors/StepsEditor.tsx` | Ordered steps editor |

### Entity Views

| View | Entity | Key Features |
|------|--------|--------------|
| `RecipesView.tsx` | recipes | Card grid, search, filters |
| `InventoryView.tsx` | inventory | Location grouping |
| `ShoppingView.tsx` | shopping_list | Checkbox toggle |
| `MealPlanView.tsx` | meal_plans | Calendar view |
| `TasksView.tsx` | tasks | Due date sorting |

### Focus Overlays

Detail views that slide over the current view:
- `FocusOverlay.tsx` — Container with backdrop
- `RecipeDetail.tsx` — Full recipe with ingredients/steps
- `MealPlanDetail.tsx` — Meal plan with linked recipe

---

## Chat Interface

| Component | Purpose |
|-----------|---------|
| `ChatView.tsx` | Main chat container |
| `ChatInput.tsx` | Message input with @-mention support |
| `MessageBubble.tsx` | User/assistant message display |
| `MentionCard.tsx` | @-mention chip display |
| `EntityCard.tsx` | Entity status cards in messages |
| `ProgressTrail.tsx` | Step execution visualization |

---

## @-Mention System

Users can reference entities in chat using `@` mentions.

### Flow

1. User types `@` in ChatInput
2. Autocomplete dropdown appears (grouped by entity type)
3. User searches/selects entity
4. Mention inserted: `@[Butter Chicken](recipe:uuid-123)`
5. AI receives full entity data in context

### Entity Types

| Type | Icon | Searchable Field |
|------|------|------------------|
| recipe | - | name |
| inv (inventory) | - | name |
| shop (shopping) | - | name |
| task | - | title |

---

## State Management

### ChatContext

```typescript
// context/ChatContext.tsx
const { messages, sendMessage, pushUIChange } = useChatContext();

// Notify AI of user actions
pushUIChange({
  entity_type: "recipe",
  entity_id: uuid,
  action: "created",
  label: "Butter Chicken"
});
```

### useEntities Hook

```typescript
const {
  entities,
  loading,
  create,
  update,
  delete: remove
} = useEntities("recipes");
```

---

## AI Context Integration

The frontend notifies the AI of user actions so it maintains awareness.

### UI Changes → AI Context

When users CRUD via UI, track changes for the next chat message:

```typescript
// After creating/updating/deleting via EntityForm or Views
pushUIChange({
  entity_type: "recipe",
  entity_id: uuid,
  action: "created",  // "created" | "updated" | "deleted"
  label: "Butter Chicken"
});
```

These are sent with chat messages and registered as `created:user`, `updated:user`, `deleted:user` in the AI's context.

### @-Mentions → AI Context

When users @-mention, the full entity data is injected:

```typescript
// ChatInput builds mentioned_entities from @-mentions
{
  "mentioned_entities": [{
    "ref_type": "recipe",
    "uuid": "uuid-123",
    "label": "Butter Chicken",
    "data": { /* full recipe data */ }
  }]
}
```

The AI sees this as `mentioned:user` with full data available.

### What AI Sees

| UI Action | AI Context Tag | Data Available |
|-----------|----------------|----------------|
| User creates via form | `created:user` | Ref + label |
| User edits via form | `updated:user` | Ref + label |
| User deletes | `deleted:user` | Ref + label |
| User @-mentions | `mentioned:user` | Full entity data |

See [docs/architecture/context-and-session.md](../../docs/architecture/context-and-session.md) for backend details.

---

## UX Rules

- Entity cards show status badges (`created`, `updated`, `deleted`)
- Loading states use skeleton components
- Errors display inline with retry option
- Forms validate on blur, submit on Enter
- Toast notifications for success/error feedback

---

## Mobile Responsiveness Patterns

### Breakpoints

Using Tailwind defaults: `sm` (640px), `md` (768px), `lg` (1024px)

### Action Button Visibility

Edit/Delete buttons use hover-reveal on desktop, always visible on mobile:

```tsx
className="md:opacity-0 md:group-hover:opacity-100 ..."
```

### Text Truncation in Flex Containers

For flex items with variable-length text:

```tsx
<div className="flex items-center gap-3 min-w-0">     {/* min-w-0 allows shrinking */}
  <span className="shrink-0 ...">Badge</span>          {/* Prevent badge shrinking */}
  <span className="truncate ...">Long text here</span> {/* Truncate with ellipsis */}
</div>
```

### Responsive Layouts

Tables don't work well on mobile. Use dual layouts:

```tsx
{/* Mobile: Cards */}
<div className="md:hidden space-y-3">
  {items.map(item => <Card key={item.id} />)}
</div>

{/* Desktop: Table */}
<div className="hidden md:block">
  <table>...</table>
</div>
```

Examples: `InventoryView.tsx`, `ShoppingView.tsx`

---

## Commands

```bash
cd frontend
npm install            # Install deps
npm run dev            # Vite dev server
npm run build          # Production build
npm run lint           # ESLint
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/App.tsx` | Router, providers |
| `src/main.tsx` | Entry point |
| `src/context/ChatContext.tsx` | Chat state management |
| `src/components/Layout/AppShell.tsx` | Main layout |

---

## Related Docs

- [docs/architecture/capabilities.md](../../docs/architecture/capabilities.md) — User-facing capabilities
- [docs/specs/onboarding-spec.md](../../docs/specs/onboarding-spec.md) — Onboarding flow
