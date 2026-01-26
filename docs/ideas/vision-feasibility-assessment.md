# Product Vision Feasibility Assessment

**Date:** 2026-01-24
**Source:** [product vision.md](product%20vision.md)
**Status:** Phase 1 Foundation Complete, Phase 2a-2b Complete, Phase 2c Next

---

## Implementation Status (Updated 2026-01-24)

### ✅ Phase 1 Foundation - COMPLETE

| Component | File | Status |
|-----------|------|--------|
| Schema API endpoints | `src/alfred/web/schema_routes.py` | ✅ Done |
| Entity CRUD endpoints | `src/alfred/web/entity_routes.py` | ✅ Done |
| Auth utilities | `src/alfred/web/auth.py` | ✅ Done |
| useSchema hooks | `frontend/src/hooks/useSchema.ts` | ✅ Done |
| FieldRenderer | `frontend/src/components/Form/FieldRenderer.tsx` | ✅ Done |
| EntityForm + Modal | `frontend/src/components/Form/EntityForm.tsx` | ✅ Done |
| Inventory Create | `frontend/src/components/Views/InventoryView.tsx` | ✅ Done |

### ✅ Phase 1b - COMPLETE: Inventory Full CRUD

Inventory now has complete CRUD:
- **Create**: Modal via EntityFormModal
- **Update**: Inline quantity edit + full Edit modal (✏️ button)
- **Delete**: Row hover with confirmation
- All endpoints use `/api/entities/*`

### ✅ Phase 2a - COMPLETE: Shopping & Tasks CRUD

Simple entities now have full CRUD:
- **Shopping List**: Create/Edit modals, migrated to `/api/entities/*`
- **Tasks**: TaskCreate model added, Create/Edit modals, migrated to `/api/entities/*`

### ✅ Phase 2b - COMPLETE: FK Picker Components

Built reusable picker components for FK relationships:
- **RecipePicker**: Searchable dropdown with name + cuisine badge + difficulty
- **MealPlanPicker**: Date-grouped dropdown with meal_type badge
- **Integration**: Tasks form now has RecipePicker and MealPlanPicker via `customRenderers`

New files:
- `frontend/src/components/Form/pickers/RecipePicker.tsx`
- `frontend/src/components/Form/pickers/MealPlanPicker.tsx`
- `frontend/src/components/Form/pickers/index.ts`

### Current CRUD Audit (per Subdomain)

| View | Read | Create | Update | Delete | API Pattern |
|------|------|--------|--------|--------|-------------|
| **Inventory** | ✅ Table | ✅ Modal | ✅ Full modal + inline | ✅ Row hover | `/api/entities/*` |
| **Shopping** | ✅ List | ✅ Modal | ✅ Modal + Toggle | ✅ Row hover | `/api/entities/*` |
| **Tasks** | ✅ List | ✅ Modal | ✅ Modal + Toggle | ✅ Row hover | `/api/entities/*` |
| **Recipes** | ✅ Grid | ❌ | ❌ | ❌ | `/api/tables/*` |
| **Meal Plans** | ✅ Date-grouped | ❌ | ❌ | ❌ | `/api/tables/*` |
| **Preferences** | ✅ Tabs | N/A | ❌ | N/A | `/api/tables/*` |

### Model/Interface Gaps - RESOLVED

**Backend (`src/alfred/models/entities.py`):**
- ✅ `MealPlanCreate` exists with `recipe_id: UUID | None = None`
- ✅ `RecipeCreate` exists with `ingredients: list[RecipeIngredientCreate]`
- ✅ `TaskCreate` added with `recipe_id` and `meal_plan_id` FK fields

**Frontend (TypeScript interfaces):**
- ✅ TasksView `Task` interface updated with `recipe_id` and `meal_plan_id` FK columns

### FK Relationships Requiring Pickers

| Entity | FK Column | Target | Required? | Picker Needed |
|--------|-----------|--------|-----------|---------------|
| MealPlan | `recipe_id` | recipes | Optional | **RecipePicker** |
| Task | `recipe_id` | recipes | Optional | **RecipePicker** |
| Task | `meal_plan_id` | meal_plans | Optional | **MealPlanPicker** |

### Recipe + Ingredients Atomic Pattern

Already implemented in `entity_routes.py`:
- Endpoint: `POST /api/entities/recipes/with-ingredients`
- Frontend sends: `{ name, cuisine, instructions, ingredients: [{name, qty, unit}...] }`
- Backend creates recipe → gets UUID → creates recipe_ingredients with that UUID
- `RecipeIngredientCreate` does NOT require `ingredient_id` (optional for master linking)

---

## Implementation Order (Next Steps)

### ✅ Phase 1b: Complete Inventory CRUD - DONE
1. ✅ Add Edit modal to InventoryView (reuse EntityFormModal)
2. ✅ Verify Delete uses `/api/entities/*` endpoint
3. ✅ Test full CRUD cycle - working

### ✅ Phase 2a: Simple CRUD (Shopping, Tasks basics) - DONE
4. ✅ Shopping List: Added Create/Edit modals, migrated to `/api/entities/*`
5. ✅ Tasks: Added `TaskCreate` model, Create/Edit modals, migrated to `/api/entities/*`

### ✅ Phase 2b: FK Picker Components - DONE
6. ✅ Built RecipePicker (searchable dropdown with cuisine/difficulty badges)
7. ✅ Built MealPlanPicker (date-grouped dropdown with meal_type badges)
8. ✅ Integrated pickers with Tasks form via `customRenderers` prop

### Phase 2c: Complex CRUD (Meal Plans, Recipes)
9. Meal Plans: Add Create modal with RecipePicker
10. Recipes: Build IngredientsEditor, RecipeEditor, use atomic endpoint

---

## Implementation Plan: Schema-Driven CRUD

### Summary

Build schema-driven CRUD infrastructure that enables:
1. **Single source of truth** - Backend schemas exposed via API, no duplicate TypeScript types
2. **Generic form generation** - New entity forms require minimal code
3. **Phase 3 ready** - API responses include metadata for future context integration

**Scope:** Phase 1 (Schema API + Foundation) + Phase 2 (Entity Editors)
**Deferred:** Phase 3 (Context API integration for AI awareness)

---

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
├─────────────────────────────────────────────────────────────┤
│  SchemaProvider ─────► useSchema() ─────► EntityForm        │
│                                           EntityList         │
│  FieldRenderer: type → widget                                │
│  ChangeTracker: captures edits for Phase 3                   │
└────────────────────────────┬────────────────────────────────┘
                             │ GET /api/schema/*
                             │ POST/PATCH/DELETE /api/entities/*
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Backend API (new)                        │
├─────────────────────────────────────────────────────────────┤
│  /api/schema/{subdomain}     → SUBDOMAIN_REGISTRY + enums   │
│  /api/schema/{subdomain}/form → Pydantic JSON Schema        │
│  /api/entities/{table}        → CRUD with change tracking   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Existing Infrastructure                                     │
│  - schema.py (SUBDOMAIN_REGISTRY, FIELD_ENUMS, FALLBACK_SCHEMAS)
│  - entities.py (Pydantic models with Create/Update variants)│
│  - Supabase (RLS-enforced tables)                           │
└─────────────────────────────────────────────────────────────┘
```

---

### Phase 3 Architectural Considerations

**What we need to capture for future context integration:**

| Event | Data to Capture | Where to Store |
|-------|-----------------|----------------|
| Entity created via UI | `{entity_type, ref, label, source: "user", timestamp}` | TBD: DB table or memory |
| Entity updated via UI | `{ref, fields_changed, source: "user", timestamp}` | TBD |
| Entity deleted via UI | `{ref, source: "user", timestamp}` | TBD |

**Architectural hooks to build now:**
1. **Middleware pattern** - All CRUD goes through a single layer that can emit events
2. **Response metadata** - API responses include `{ref, action, timestamp}` for frontend tracking
3. **Optional event emitter** - Backend can emit to a change log (disabled for now, enabled Phase 3)

**What we're NOT building yet:**
- The actual change log table
- Context injection of "user edited X"
- SessionIdRegistry awareness of UI-created entities

**Key principle:** Frontend CRUD should be indistinguishable from AI CRUD at the database level. Both write to the same tables. The difference is tracked at the *event* level, not the *data* level.

---

### Phase 1: Schema API + Foundation

#### 1.1 Schema Endpoints

**File:** `src/alfred/web/app.py` (extend existing FastAPI app)

```python
# New endpoints to add:

GET /api/schema
→ Returns all subdomains overview
{
  "subdomains": {
    "inventory": {"tables": ["inventory", "ingredients"], "primary": "inventory"},
    "recipes": {"tables": ["recipes", "recipe_ingredients"], "primary": "recipes"},
    ...
  }
}

GET /api/schema/{subdomain}
→ Returns full schema for a subdomain
{
  "subdomain": "recipes",
  "tables": ["recipes", "recipe_ingredients"],
  "columns": {...},  // From FALLBACK_SCHEMAS
  "enums": {...},    // From FIELD_ENUMS
  "scope": {...},    // From SUBDOMAIN_SCOPE
  "relationships": {...}  // FK info extracted
}

GET /api/schema/{subdomain}/form
→ Returns Pydantic JSON Schema for create form
{
  "create": RecipeCreate.model_json_schema(),
  "update": RecipeUpdate.model_json_schema() if exists
}
```

**Implementation:** Create `src/alfred/web/schema_routes.py`

**Schema Sources (in order of preference):**

| Data | Source | Method |
|------|--------|--------|
| Form fields | Pydantic models | `RecipeCreate.model_json_schema()` |
| Enums | FIELD_ENUMS | Direct dict export |
| Domain config | SUBDOMAIN_REGISTRY | Direct dict export |
| Scope/relationships | SUBDOMAIN_SCOPE | Direct dict export |

**Important:** Do NOT parse `FALLBACK_SCHEMAS` markdown. That's for LLM context only.

```python
# schema_routes.py
from alfred.models.entities import RecipeCreate, InventoryCreate, ...
from alfred.tools.schema import SUBDOMAIN_REGISTRY, FIELD_ENUMS, SUBDOMAIN_SCOPE

MODEL_REGISTRY = {
    "recipes": {"create": RecipeCreate, "update": RecipeUpdate},
    "inventory": {"create": InventoryCreate, "update": InventoryUpdate},
    # ...
}

@router.get("/schema/{subdomain}/form")
def get_form_schema(subdomain: str):
    models = MODEL_REGISTRY.get(subdomain)
    # Strip subdomain prefix from enum keys for cleaner frontend consumption
    # "recipes.cuisine" → "cuisine"
    enums = {
        k.split(".", 1)[1]: v
        for k, v in FIELD_ENUMS.items()
        if k.startswith(f"{subdomain}.")
    }
    return {
        "create": models["create"].model_json_schema(),
        "update": models["update"].model_json_schema() if models.get("update") else None,
        "enums": enums  # {"cuisine": [...], "difficulty": [...]}
    }
```

- Register routes on FastAPI app

#### 1.2 Entity CRUD Endpoints

**File:** `src/alfred/web/entity_routes.py` (new)

```python
# Unified CRUD for all entities:

GET    /api/entities/{table}           → List with filtering
GET    /api/entities/{table}/{id}      → Get single
POST   /api/entities/{table}           → Create (returns {data, meta: {action, timestamp}})
PATCH  /api/entities/{table}/{id}      → Update
DELETE /api/entities/{table}/{id}      → Delete

# Special: Recipe with ingredients (atomic)
POST   /api/entities/recipes/with-ingredients
→ Creates recipe + recipe_ingredients in transaction
```

**Response format (Phase 3 ready):**
```json
{
  "data": { /* entity */ },
  "meta": {
    "action": "created",
    "entity_type": "recipes",
    "id": "uuid",
    "timestamp": "2026-01-24T..."
  }
}
```

The `meta` field is the hook for Phase 3 - frontend can use this to track changes.

#### 1.3 Frontend SchemaProvider

**File:** `frontend/src/contexts/SchemaContext.tsx` (new)

```typescript
interface SchemaContextValue {
  schemas: Map<string, SubdomainSchema>
  getSchema: (subdomain: string) => SubdomainSchema | undefined
  getEnums: (subdomain: string, field: string) => string[] | undefined
  getFormSchema: (subdomain: string) => JSONSchema | undefined
  loading: boolean
}

// Fetches on mount, caches in memory
// Re-fetches only on explicit invalidation
```

#### 1.4 FieldRenderer Component

**File:** `frontend/src/components/Form/FieldRenderer.tsx` (new)

```typescript
interface FieldRendererProps {
  field: JSONSchemaProperty
  name: string
  value: any
  onChange: (value: any) => void
  enums?: Record<string, string[]>
  customRenderer?: React.ComponentType<FieldRendererProps>  // For complex fields
}

// Maps JSON Schema types → widgets:
// string → TextInput
// string + enum → Select/Dropdown
// string + format:date → DatePicker
// integer → NumberInput
// boolean → Checkbox
// array of string → MultiSelect/Chips
// array of objects → ⚠️ CUSTOM COMPONENT REQUIRED (see below)
```

**Array of Objects - Custom Components Required:**

FieldRenderer does NOT handle `array of objects` generically. These need custom editors:

| Field | Custom Component | Why |
|-------|------------------|-----|
| `recipe.ingredients` | `IngredientsEditor` | FK picker, add/remove rows, reorder |
| `recipe.instructions` | `StepsEditor` | Ordered list, reorder, rich text |
| `preferences.*_tags` | `ChipsEditor` | Simple array of strings (this one CAN be generic) |

When FieldRenderer encounters `{type: "array", items: {type: "object"}}`, it renders a slot for the `customRenderer` prop or shows "Custom editor required" placeholder.

#### 1.5 EntityForm Component

**File:** `frontend/src/components/Form/EntityForm.tsx` (new)

```typescript
interface EntityFormProps {
  subdomain: string
  mode: 'create' | 'edit'
  initialData?: Record<string, any>
  onSubmit: (data: Record<string, any>) => Promise<void>
  onCancel: () => void
}

// Fetches form schema from SchemaProvider
// Renders fields via FieldRenderer
// Handles validation from JSON Schema
// Submits to entity CRUD endpoint
```

#### 1.6 Authentication Integration

All entity routes use existing auth infrastructure:

```python
# Entity routes follow same pattern as existing /api/tables/* endpoints
@router.post("/entities/{table}")
async def create_entity(table: str, data: dict, request: Request):
    # Auth middleware already validated token and set context
    client = get_client()  # Auto-uses authenticated client via request context
    # RLS enforced automatically - user can only see/modify their own data
    result = client.table(table).insert(data).execute()
    return {"data": result.data[0], "meta": {...}}
```

**Auth behavior:**
- Routes use existing JWT middleware (same as `/api/tables/*`)
- `get_client()` called inside handlers → RLS enforced
- `get_service_client()` NEVER used for user-facing CRUD
- 401 returned if no valid token
- RLS silently filters results to user's data only

#### 1.7 Error Response Contract

All entity endpoints return consistent error shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable message",
    "details": {"field": "name", "issue": "required"}
  }
}
```

**HTTP status codes:**
| Status | Code | When |
|--------|------|------|
| 400 | `validation_error` | Missing/invalid field |
| 401 | `not_authenticated` | No/invalid token |
| 404 | `not_found` | Entity doesn't exist (or RLS hides it) |
| 409 | `conflict` | Duplicate unique key |
| 500 | `internal_error` | Unexpected failure |

**Note:** 403 shouldn't occur - RLS returns empty results rather than forbidden.

---

### Phase 2: Entity Editors

#### 2.1 Simple Entities (Schema-Only)

These entities can be fully rendered from schema without custom components:

| Entity | Custom Needs |
|--------|--------------|
| Inventory | None - pure schema form |
| Shopping List | None - pure schema form |
| Tasks | None - pure schema form |
| Preferences | Grouped sections (Profile/Vibes/Rhythm) |

**Implementation:** Use EntityForm directly with subdomain schema.

#### 2.2 Recipe Editor (Custom + Schema)

**File:** `frontend/src/components/Editors/RecipeEditor.tsx` (new)

```typescript
// Combines:
// 1. Schema-driven fields for metadata (name, cuisine, difficulty, times)
// 2. Custom IngredientsEditor sub-form
// 3. Custom StepsEditor (ordered list with reorder)

interface RecipeEditorProps {
  mode: 'create' | 'edit'
  recipeId?: string  // For edit mode
  onSuccess: (recipe: Recipe) => void
  onCancel: () => void
}
```

**Sub-components:**

`IngredientsEditor.tsx`:
- Ingredient autocomplete (uses existing `/api/ingredients/search`)
- Quantity + unit inputs
- Notes field
- Optional checkbox
- Add/remove/reorder rows

#### Recipe Ingredient Handling

When creating/editing recipes:

| Scenario | Behavior |
|----------|----------|
| **User selects from autocomplete** | `ingredient_id` populated, `name` from selected ingredient |
| **User types free-form name** | `ingredient_id = null`, `name` stored directly |
| **No exact match in DB** | Allow free-form (no auto-create of ingredients) |

**Rationale:** This matches existing AI behavior where recipes can have free-form ingredient names. The `ingredients` table is a master list for normalization/search, not a strict constraint.

**Schema supports this:**
```sql
recipe_ingredients:
  ingredient_id UUID | Yes  ← FK is nullable
  name TEXT | No           ← Always required
```

`StepsEditor.tsx`:
- Ordered list of instruction steps
- Add/remove steps
- Reorder (up/down buttons or drag-drop)

#### 2.3 Meal Plan Editor

**File:** `frontend/src/components/Editors/MealPlanEditor.tsx` (new)

```typescript
// Schema-driven fields + custom RecipePicker

interface MealPlanEditorProps {
  date?: Date  // Pre-fill date
  mode: 'create' | 'edit'
  mealPlanId?: string
  onSuccess: (mealPlan: MealPlan) => void
}
```

Custom component: `RecipePicker` - search/select from user's recipes.

#### 2.4 Integration Points

**RecipesView.tsx** - Add "New Recipe" button → opens RecipeEditor modal
**MealPlanView.tsx** - Add "Plan Meal" button → opens MealPlanEditor modal
**InventoryView.tsx** - Add "Add Item" button → opens EntityForm modal

---

### File Changes Summary

#### New Files (Backend)

| File | Purpose |
|------|---------|
| `src/alfred/web/schema_routes.py` | Schema API endpoints |
| `src/alfred/web/entity_routes.py` | Unified CRUD endpoints |

#### New Files (Frontend)

| File | Purpose |
|------|---------|
| `src/contexts/SchemaContext.tsx` | Schema provider + hooks |
| `src/components/Form/FieldRenderer.tsx` | Type → widget mapping |
| `src/components/Form/EntityForm.tsx` | Generic schema-driven form |
| `src/components/Form/fields/*.tsx` | Individual field widgets |
| `src/components/Editors/RecipeEditor.tsx` | Recipe-specific editor |
| `src/components/Editors/IngredientsEditor.tsx` | Recipe ingredients sub-form |
| `src/components/Editors/StepsEditor.tsx` | Instructions list editor |
| `src/components/Editors/MealPlanEditor.tsx` | Meal plan editor |
| `src/components/Editors/RecipePicker.tsx` | Recipe search/select |

#### Modified Files

| File | Changes |
|------|---------|
| `src/alfred/web/app.py` | Register new route modules |
| `frontend/src/components/Views/RecipesView.tsx` | Add "New Recipe" button |
| `frontend/src/components/Views/MealPlanView.tsx` | Add "Plan Meal" button |
| `frontend/src/components/Views/InventoryView.tsx` | Add "Add Item" button |

---

### What We're Locking In vs Flexible

#### Locked In (API Contracts)
- `/api/schema/*` endpoint structure
- Response `meta` field format: `{action, entity_type, id, timestamp}`
- Pydantic models as source of JSON Schema
- SUBDOMAIN_REGISTRY as domain configuration

#### Stays Flexible (Design Choices)
- UI component library, styling, layouts
- Field → widget mapping (can swap components anytime)
- Form library choice (vanilla, react-hook-form, etc.)
- Entity-specific editor implementations

---

### Verification

#### Phase 1 Verification

```bash
# Test schema endpoints
curl http://localhost:8000/api/schema
curl http://localhost:8000/api/schema/recipes
curl http://localhost:8000/api/schema/recipes/form

# Test entity CRUD
curl -X POST http://localhost:8000/api/entities/inventory \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "eggs", "quantity": 12, "unit": "count"}'
```

#### Phase 2 Verification

1. Open RecipesView → Click "New Recipe" → Fill form → Submit → Recipe appears in list
2. Open InventoryView → Click "Add Item" → Fill form → Submit → Item appears in list
3. Edit existing recipe → Changes persist
4. Delete recipe → Removed from list

---

# Feasibility Assessment

## Executive Summary

The product vision document outlines 7 major initiatives to transform Alfred from a chat-centric AI app to a standalone application with AI as an enhancement layer. **Overall: architecturally sound, well-aligned with existing patterns, but scope is ambitious.**

---

## Feasibility Analysis by Section

### 1. Core Motivation: Decouple UI from AI ✅ HIGH FEASIBILITY
**Architecture Alignment:** Perfect. The vision explicitly references Alfred's core principle: "LLMs interpret, don't own." The backend already enforces deterministic state via CRUD + SessionIdRegistry.

**Current State:**
- 7 CRUD views already exist (Inventory, Recipes, Meals, Shopping, Tasks, Ingredients, Preferences)
- All views have functional read operations
- Some have inline edit (inventory quantities, shopping toggle)

**Gap:** Missing create/edit forms for complex entities (recipes, meal plans). Preferences view is read-only.

**Effort:** Medium - infrastructure exists, need form components.

---

### 2. CRUD Interface for All Entities ✅ HIGH FEASIBILITY
**What Exists:**
| Entity | Read | Create | Update | Delete |
|--------|------|--------|--------|--------|
| Inventory | ✅ | ❌ | ✅ (qty only) | ✅ |
| Recipes | ✅ | ❌ | ❌ | ❌ |
| Meal Plans | ✅ | ❌ | ❌ | ❌ |
| Shopping | ✅ | ❌ | ✅ (toggle) | ✅ |
| Tasks | ✅ | ❌ | ✅ (toggle) | ✅ |
| Preferences | ✅ | N/A | ❌ | N/A |

**Key Gap:** Recipe Editor (complex form with ingredients, steps, images). This is the hardest CRUD screen.

**Change Tracking for AI Context:** Feasible via SessionIdRegistry's existing `last_action` field. Would need minor extension to track "user-modified" source.

**Effort:** Medium-High - Recipe editor is substantial work.

---

### 3. Context Management Enhancements ⚠️ MEDIUM FEASIBILITY
**@-Mention Entity Tagging:**
- Frontend already parses `@[Label](type:id)` mentions in chat (MentionCard.tsx)
- Backend SessionIdRegistry supports refs
- **Gap:** No autocomplete dropdown for @ mentions, no "pin to context" UI

**Context Segmentation:**
- Backend already has three-layer model (Entity, Conversation, Reasoning)
- `active_reason` field exists in registry for retention logic
- **Gap:** No frontend "Context Bar" to show/manage pinned entities

**Risk:** Complexity in Understand node to respect user-pinned entities vs auto-curated. May require prompt changes.

**Effort:** Medium - Backend mostly ready, frontend UI work needed.

---

### 4. Home/Dashboard Experience ⚠️ MEDIUM FEASIBILITY
**Current State:** No dashboard. App opens to Chat view via sidebar navigation.

**Widget Architecture:**
- Vision proposes: Meal Plan widget, Inventory (low/expiring), Shopping count, Tasks, Recipes
- Would need new API endpoints (e.g., `/dashboard/meal_plan_summary`)
- Component patterns exist (cards, lists) - reusable

**Chat Integration Options:**
- Current: Chat is a dedicated sidebar view
- Vision: Floating bubble/drawer pattern
- **Risk:** Major UX shift. Floating chat adds complexity (z-index, overlay state, context preservation)

**Configuration-Driven Widgets:** Ambitious. Would need Widget Registry pattern. Current codebase has no dynamic registration patterns.

**Effort:** High - New page, new APIs, potential chat redesign.

---

### 5. Schema-Driven UI Architecture ✅ HIGH FEASIBILITY (revised)

**Initial Assessment Was Wrong.** The backend already has extensive schema infrastructure:

| Component | Location | What It Provides |
|-----------|----------|------------------|
| `SUBDOMAIN_REGISTRY` | schema.py | Domain → tables mapping |
| `FIELD_ENUMS` | schema.py | Dropdown values (location, cuisine, difficulty, meal_type) |
| `FALLBACK_SCHEMAS` | schema.py | Column definitions, types, nullability, FK relationships |
| `SEMANTIC_NOTES` | schema.py | Field descriptions and special handling |
| `SUBDOMAIN_EXAMPLES` | schema.py | CRUD examples per domain |
| Pydantic models | entities.py | Type contracts, can generate JSON Schema |
| `EntitySnapshot` | entity.py | Structured metadata (type, label, status) |

**The Gap:** No HTTP endpoints expose this to the frontend. The infrastructure exists but is internal-only.

**Revised Effort:** Medium - Expose existing schemas via API, build generic components.

**Recommendation:** This is now a strong foundation for the CRUD UI work.

---

### 6. Modes and Interaction Simplification ✅ HIGH FEASIBILITY
**Current State:**
- Quick mode already implemented (Understand → Act Quick → Reply)
- Plan mode is default flow (Understand → Think → Act Loop → Reply)
- Frontend has mode toggle in ChatInput.tsx (⚡ quick vs 📋 plan)

**Cooking Mode:**
- Vision: Streamlined UI, faster responses, voice-ready
- Backend: Could skip Understand, use smaller model
- **Gap:** No "focused recipe view + mini chat" UI exists

**Brainstorm/Create Mode:**
- Maps to existing `generate` step type
- Model routing already exists (low/medium/high complexity → model selection)

**Mode Selection UI:** Already partially exists. Expanding it is straightforward.

**Effort:** Low-Medium - Mostly UI polish and minor backend tuning.

---

### 7. Additional Features

| Feature | Feasibility | Effort | Notes |
|---------|-------------|--------|-------|
| **Onboarding/Tutorials** | ✅ High | Low | Onboarding flow exists. Add UI walkthrough tooltips. |
| **Recipe Import (URL parser)** | ⚠️ Medium | Medium | Already in backlog. LLM-powered parsing. Need scraper + form pre-fill. |
| **Ingredient DB Cleanup** | ✅ High | Medium | Data migration + add `canonical_name`, `popularity` fields. Backend work. |

---

## Prioritization Recommendation

### Tier 1: Quick Wins (1-2 weeks each)
1. **Preferences Edit UI** - Complete the CRUD loop for existing view
2. **Mode toggle polish** - Cooking mode with simplified UI
3. **UI walkthrough tooltips** - Low effort, high onboarding value

### Tier 2: High-Value Medium Effort (2-4 weeks each)
4. **Dashboard v1** - Simple widget grid (upcoming meals, low inventory, pending tasks)
5. **Recipe Import from URL** - Already in backlog, reduces friction significantly
6. **@-mention autocomplete** - Improves chat UX, leverages existing infrastructure

### Tier 3: Substantial Investment (4-8 weeks)
7. **Recipe Editor (full CRUD)** - Complex form, but core value prop
8. **Floating chat bubble** - UX redesign, test carefully
9. **Context Bar UI** - Pinned entities management

### Tier 4: Defer
10. **Schema-driven UI framework** - Wait for multi-domain expansion
11. **Multi-user households** - Requires auth/RLS rethink
12. **Voice input** - Platform-dependent, future enhancement

---

## Key Dependencies

```
Dashboard ← requires summary API endpoints
Recipe Editor ← requires ingredient autocomplete (already exists in IngredientsView)
Floating Chat ← requires context preservation across views
Schema-driven UI ← requires stabilized entity schemas + backend exposure
```

---

## Risk Factors

1. **Scope Creep:** Document covers transformative changes. Recommend phased approach.
2. **Chat UX Disruption:** Moving from dedicated view to floating bubble is high-risk. User test first.
3. **Schema-Driven Premature Optimization:** Only one domain exists. Don't build for hypothetical fitness/finance.
4. **Recipe Editor Complexity:** Ingredients sub-form, step ordering, image upload. Largest single feature.

---

## Summary

| Section | Feasibility | Priority | Recommendation |
|---------|-------------|----------|----------------|
| 1. Decouple UI from AI | ✅ High | — | Already aligned |
| 2. Full CRUD | ✅ High | High | Focus on Recipe Editor |
| 3. Context Management | ⚠️ Medium | Medium | @-mention autocomplete first |
| 4. Dashboard | ⚠️ Medium | High | Start with v1 widgets |
| 5. Schema-Driven UI | ✅ High | High | Foundation for CRUD work |
| 6. Modes | ✅ High | Medium | Polish existing |
| 7. Additional Features | Mixed | Mixed | Recipe import highest value |

---

## Deep Dive: Recipe Editor

### Current State

**Data Model (DB):**
```
recipes
├── id, user_id, name, description, cuisine, difficulty
├── prep_time_minutes, cook_time_minutes, servings
├── instructions TEXT[]  (array of steps)
├── tags, occasions, health_tags, flavor_tags, equipment_tags (all TEXT[])
├── source_url, embedding, is_system, parent_recipe_id
└── created_at

recipe_ingredients (junction table)
├── id, recipe_id (FK CASCADE), ingredient_id (FK to ingredients)
├── name, quantity, unit, notes, is_optional, category
```

**Frontend:**
- `RecipesView.tsx` - Card grid, read-only, opens detail modal
- `RecipeDetail.tsx` - Display + delete only, no edit

**Backend APIs:**
| Endpoint | Status |
|----------|--------|
| `GET /api/tables/recipes` | ✅ Exists |
| `GET /api/tables/recipes/{id}/ingredients` | ✅ Exists |
| `GET /api/ingredients/search?q=` | ✅ Exists |
| `DELETE /api/tables/recipes/{id}` | ✅ Exists |
| `POST /api/tables/recipes` | ❌ Need to expose |
| `PATCH /api/tables/recipes/{id}` | ⚠️ Generic exists, may need recipe-specific |

### Components to Build

| Component | Purpose | Complexity |
|-----------|---------|------------|
| **RecipeForm.tsx** | Main create/edit form | High |
| **IngredientsEditor.tsx** | Sub-form for ingredients list | High |
| **RecipeFormModal.tsx** | Modal wrapper, triggers from grid | Low |
| **StepsEditor.tsx** | Ordered list of instruction steps | Medium |

### RecipeForm Fields

**Basic Info:**
- `name` (required, text)
- `description` (optional, textarea)
- `cuisine` (optional, text or dropdown)
- `source_url` (optional, URL input)

**Timing & Difficulty:**
- `prep_time_minutes` (number)
- `cook_time_minutes` (number)
- `servings` (number)
- `difficulty` (dropdown: easy/medium/hard)

**Tags (multi-select chips):**
- `occasions` - weeknight, batch-prep, hosting, weekend, comfort
- `health_tags` - high-protein, low-carb, vegetarian, vegan, etc.
- `flavor_tags` - spicy, mild, savory, sweet, tangy, etc.
- `equipment_tags` - air-fryer, instant-pot, one-pot, grill, etc.

**Complex Sub-forms:**
- `instructions[]` - Ordered list of steps (add/remove/reorder)
- `ingredients[]` - Each with: name, quantity, unit, notes, is_optional

### IngredientsEditor Subform

Each ingredient row:
```
[ Ingredient search autocomplete ] [ Qty ] [ Unit dropdown ] [ Notes ] [Optional?] [×]

[+ Add Ingredient]
```

**Ingredient Naming Rules (from prompts):**
- Use grocery store names: "chicken breast" not "Crispy herb chicken"
- Put prep in notes: `name="chickpeas"`, `notes="drained and roasted"`
- Keep meaningful descriptors: "fresh basil" vs "dried oregano" (different products)

### Existing Patterns to Reuse

| Pattern | Source | Reuse For |
|---------|--------|-----------|
| Search + autocomplete | `IngredientsView.tsx` | Ingredient picker |
| Form state + submit | `ConstraintsStep.tsx` (onboarding) | Recipe form |
| Modal overlay | `FocusOverlay.tsx` | Edit modal |
| Delete confirmation | `RecipeDetail.tsx` | Already exists |
| Chip multi-select | `PantryStep.tsx` | Tag selection |

### Estimated Effort

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: Create Recipe (MVP) | 2-3 days | POST endpoint |
| Phase 2: Ingredients Editor | 3-4 days | Ingredient autocomplete |
| Phase 3: Full Edit | 2-3 days | PATCH + linked updates |
| Phase 4: Polish | 2-3 days | None |
| **Total** | **~2 weeks** | |

---

## Deep Dive: Schema-Driven UI Architecture

### What Already Exists (Backend)

**1. SUBDOMAIN_REGISTRY** (`schema.py:99-129`)
```python
SUBDOMAIN_REGISTRY = {
    "inventory": {"tables": ["inventory", "ingredients"]},
    "recipes": {"tables": ["recipes", "recipe_ingredients", "ingredients"],
                "complexity_rules": {"mutation": "high"}},
    "shopping": {"tables": ["shopping_list", "ingredients"]},
    "meal_plans": {"tables": ["meal_plans"]},
    "tasks": {"tables": ["tasks"]},
    "preferences": {"tables": ["preferences", "flavor_preferences"]},
}
```

**2. FIELD_ENUMS** (`schema.py:432-457`) - Ready for dropdowns
```python
FIELD_ENUMS = {
    "inventory.location": ["pantry", "fridge", "freezer", ...],
    "recipes.cuisine": ["italian", "mexican", "chinese", ...],
    "recipes.difficulty": ["easy", "medium", "hard"],
    "meal_plans.meal_type": ["breakfast", "lunch", "dinner", "snack"],
    ...
}
```

**3. FALLBACK_SCHEMAS** (`schema.py:616-833`) - Column definitions
```
inventory:
  - id (UUID, PK)
  - name (TEXT, NOT NULL)
  - quantity (NUMERIC, NOT NULL)
  - unit (TEXT, NOT NULL)
  - location (TEXT, nullable) ← uses FIELD_ENUMS
  - expiry_date (DATE, nullable)
  - ingredient_id (UUID) ← FK to ingredients
```

**4. Pydantic Models** (`entities.py`) - **Primary source for form schemas**
```python
RecipeCreate.model_json_schema()  # Returns full JSON Schema for create forms
# Includes: field types, required vs optional, nested $refs
```

**Note:** `FALLBACK_SCHEMAS` markdown is for LLM context only. API exposes Pydantic schemas directly.

### Field Type → Widget Mapping

| Field Type | Widget | Source |
|------------|--------|--------|
| `TEXT NOT NULL` | Text input (required) | Column def |
| `TEXT nullable` | Text input (optional) | Column def |
| `NUMERIC` | Number input | Column def |
| `DATE` | Date picker | Column def |
| `TEXT[]` | Multi-select chips | Column def |
| `TEXT` with enum | Dropdown | FIELD_ENUMS |
| `UUID FK` | Autocomplete picker | FK relationship |

### Key Insight

**This is NOT "building a UI framework from scratch."** It's:
1. Exposing existing backend schemas via REST
2. Building ~5 generic components that consume JSON Schema
3. Using those components for all entities

**Effort Revised:** 2-3 weeks for core infrastructure, then entity forms become trivial
