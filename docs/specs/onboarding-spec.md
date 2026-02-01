# Alfred Onboarding System Specification

**Date:** 2026-01-18  
**Status:** Draft v1.2  
**Scope:** Isolated onboarding module for new user setup

---

## Implementation Progress

### Built ✅

| Phase | Section | Status | Notes |
|-------|---------|--------|-------|
| A | Scaffolding | ✅ Done | `src/onboarding/` module, API router, migrations |
| B | Phase 1 - Constraints | ✅ Done | `forms.py`, validation, `/constraints` endpoint |
| C | Phase 2 - Discovery | ✅ Done | `pantry.py`, `cuisine_selection.py`, `ingredient_discovery.py` |
| D | Phase 3 - Style Interview | ✅ Done | `style_interview.py`, 4-page LLM Q&A → `subdomain_guidance` |
| **UI** | Onboarding UI | ✅ Done | `OnboardingFlow.tsx`, 5 step components (incl. StyleInterviewStep) |

**Current Flow (2026-01-19) - COMPLETE:**
1. **Basics** → Skill, diet, allergies, equipment, household size
2. **Favorites** → Search ingredients you love → then mark which you HAVE
3. **Cuisines** → Multi-select favorite cuisines
4. **Tastes** → Like/dislike ingredients (seeded by embeddings from step 2)
5. **Style Interview** ✅ → 3+1 pages of LLM-generated questions → synthesize to subdomain_guidance

**Output:** `subdomain_guidance` with personalized strings for recipes, meal_plans, tasks, shopping, inventory

### Built - Style Interview ✅ (2026-01-19)

| Component | Status | Notes |
|-----------|--------|-------|
| `style_interview.py` | ✅ Done | LLM prompts for question generation + guidance synthesis |
| Interview API endpoints | ✅ Done | `/interview/page/{n}` GET/POST, `/interview/synthesize` |
| `StyleInterviewStep.tsx` | ✅ Done | 3+1 page interview UI with free-text answers |
| Subdomain guidance output | ✅ Done | Synthesizes to `{recipes, meal_plans, tasks, shopping, inventory}` |

**Interview Flow:**
- Pages 1-3: LLM generates 3-4 questions per page based on user context + prior answers
- Page 4: Catch-all for anything missed
- Synthesis: LLM parses all free-text answers → structured subdomain_guidance strings

### Post-Onboarding ✅ (2026-02-01)

| Phase | Section | Status | Notes |
|-------|---------|--------|-------|
| **E** | **Post-Onboarding Education** | ✅ Done | Home dashboard, capabilities page, smart nudging |

After onboarding completes, users are redirected to `/home` (Home Dashboard) instead of `/about`. The dashboard shows kitchen state (stat cards) and smart nudge cards that guide users to their first recipe, pantry items, meal plan, or shopping list based on current state.

**See:** [post-onboarding-education-spec.md](post-onboarding-education-spec.md) for full details.

### Pending

| Phase | Section | Status | Notes |
|-------|---------|--------|-------|
| **I** | **8.x Integration** | **NEXT** | **Connect payload to Alfred preferences/prompts** |
| F+ | Sample Generation | Deferred | Recipe/MealPlan/Task samples for style feedback iteration |
| F+ | Sample Iteration | Deferred | User feedback → refine guidance loop |
| H | 7.x Preview | Deferred | Final preview before completion |

### Known Issues / Future Polish (SHELVED)

| Issue | Priority | Notes |
|-------|----------|-------|
| Ingredient search ordering | Low | "eggs" shows "century eggs" first - using `ingredient_lookup.py` now but DB needs cleanup |
| Discovery seeding quality | Low | Random fallback works, embedding seeding implemented but needs tuning |
| Ingredient DB structure | Medium | Flat categories, no popularity scoring - needs redesign for better UX |
| Recipe/MealPlan samples | Low | Could show generated samples for user feedback before finalizing guidance |
| Like/dislike UX | Low | Current tab-based flow works but could be more engaging |

### 🎯 Next Priority: Integration (Phase I)

**Goal:** Make collected onboarding data actually used by Alfred.

**Payload Output (stored in `onboarding_data` table):**
```json
{
  "constraints": { "cooking_skill_level", "dietary_restrictions", "allergens", "equipment", "household_size" },
  "cuisine_preferences": ["indian", "thai", ...],
  "initial_inventory": [{ "id", "name", "category", "in_pantry" }],
  "ingredient_preferences": { "likes": 25, "dislikes": 8 },
  "subdomain_guidance": {
    "recipes": "Step-by-step with why, visual cues...",
    "meal_plans": "Weekend batch cook, weekday assembly...",
    "tasks": "Beginner-friendly prep reminders...",
    "shopping": "Organized by section, weekly trip...",
    "inventory": "Track proteins/sauces/produce..."
  }
}
```

**Integration Points:**
1. **`preferences` table** ← `constraints`, `subdomain_guidance`
2. **`flavor_preferences` table** ← Already populated during onboarding
3. **`inventory` table** ← `initial_inventory` items marked as `in_pantry`
4. **Prompt injection** (`src/alfred/prompts/injection.py`) ← `subdomain_guidance` by subdomain

**Decision (2026-01-19):** Onboarding flow is complete and testable. Next session: wire up payload to Alfred's preferences system.

### API Endpoints Built (2026-01-19)

**Public (no auth):**
- `GET /api/onboarding/constraints/options` - Form options
- `GET /api/onboarding/cuisines/options` - Cuisine list with icons
- `GET /api/onboarding/pantry/search?q=` - Ingredient search
- `GET /api/onboarding/discovery/categories` - Discovery categories

**Authenticated - Discovery Phase:**
- `GET /api/onboarding/state` - Current onboarding progress
- `POST /api/onboarding/constraints` - Submit constraints form
- `POST /api/onboarding/pantry` - Submit pantry items
- `POST /api/onboarding/cuisines` - Submit cuisine selections
- `GET /api/onboarding/discovery/ingredients` - Get ingredients for discovery
- `POST /api/onboarding/discovery/preference` - Mark single like/dislike
- `POST /api/onboarding/discovery/preferences` - Batch preferences
- `GET /api/onboarding/discovery/summary` - Preferences summary
- `POST /api/onboarding/discovery/complete` - Move to next phase

**Authenticated - Style Interview Phase (NEW):**
- `GET /api/onboarding/interview/page/{n}` - Get interview page n (1-4) with LLM-generated questions
- `POST /api/onboarding/interview/page/{n}` - Submit answers for page n
- `POST /api/onboarding/interview/synthesize` - Synthesize all answers → subdomain_guidance

### ⚠️ API Contract Reference (MUST CHECK BEFORE WRITING FRONTEND)

**RULE: Always read the backend endpoint before writing frontend that calls it.**

| Endpoint | Response Format | Field Names |
|----------|-----------------|-------------|
| `/constraints/options` | Direct object | `dietary_restrictions: string[]`, `allergens: string[]`, `equipment: [{id, label, icon}]`, `skill_levels: [{id, label, description}]` |
| `/cuisines/options` | `{options: [...]}` | `[{id, label, icon}]` |
| `/pantry/search` | `{results: [...]}` | `[{id, name, category}]` |
| `/discovery/categories` | `{categories: [...]}` | `[{id, label, db_categories, description}]` |
| `/discovery/summary` | Direct object | `{total, likes, dislikes, top_likes, top_dislikes}` |

**Request field names (exact match required):**
- `cooking_skill_level` (not `skill_level`)
- `allergies` (not `allergens`)
- `available_equipment` (not `equipment`)
- `preference: "like"|"dislike"` (not `preference_score`)
- `items: [{name, category}]` for pantry (not `ingredient_ids`)

### Implementation Rules (Lessons Learned 2026-01-19)

1. **Read backend before frontend** - Check actual return types in `api.py`, not assumed conventions
2. **Check wrapper vs. direct returns** - APIs may return `[...]` or `{key: [...]}` - verify which
3. **Match field names exactly** - Copy from Pydantic models, don't assume `camelCase` or abbreviations
4. **TypeScript interfaces must match API** - Use `id` if backend uses `id`, not `value`
5. **Test with real API calls** - Don't assume, verify response shapes in browser Network tab

### Future Improvements (Backlog)

**Combined Likes + Inventory UX:**
- Instead of separate "what do you have" and "what do you like" steps
- Show ingredients where users can mark: 👍 like, 👎 dislike, ✓ have in pantry
- Captures preferences AND inventory in one cleaner flow

**Smarter Ingredient Seeding (requires data model):**
- Add `popularity_score` column to ingredients (exponential: 1.0 = very common, 0.0 = niche)
- Show high-popularity ingredients first in discovery
- Cuisine → ingredient mappings to seed relevant items after cuisine selection
- Dietary-aware filtering (vegetarian sees more veggie options, etc.)

**Ingredient DB Cleanup:**
- Current categories are flat and inconsistent (`vegetables` vs `vegetables_leafy`)
- Consider hierarchical categories or tags
- Standardize cuisine tagging across ingredients

### Spec Deviations

| Original Spec | Change | Reason |
|---------------|--------|--------|
| 5.4 Constraint filtering with hardcoded exclusion lists | **Removed** | Alfred LLM handles dietary/allergy logic naturally; no need to maintain exclusion dictionaries |
| 11.4 Skill-based defaults (`defaults.py`) | **Removed** | Alfred works fine without personalization; avoid maintaining hardcoded guidance text |
| 7. "Constraint filtering throughout" principle | **Simplified** | Constraints stored and passed to LLM, not used for deterministic filtering |
| 5.2-5.3 Graph-based ingredient + cuisine discovery | **Simplified** | See below |

### Simplified Pantry & Discovery Flow (Replaces Sections 5.1-5.3)

**Original spec** proposed graph-based discovery with embedding similarity. **Simplified approach:**

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Pantry Input                                        │
│  "What do you have?"                                         │
│  [Search box] → Add items (uses existing ingredient search)  │
│  → Stored in initial_inventory                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Favorite Cuisines                                   │
│  "What do you like to cook?"                                 │
│  [Thai] [Indian] [Italian] [Japanese] ...                    │
│  → Stored in cuisine_preferences                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Ingredient Preferences (Likes & Dislikes)           │
│                                                              │
│  Show 5-8 per category from ingredients table:               │
│                                                              │
│  PROTEINS: [Chicken 👍] [Salmon 👍] [Tofu 👎] [Beef] [Shrimp]│
│  VEGETABLES: [Spinach 👍] [Broccoli] [Bell peppers 👍] ...   │
│  FRUITS: [Lemon 👍] [Lime] [Mango 👎] ...                    │
│  SPICES: [Cumin 👍] [Coriander] [Turmeric] ...               │
│                                                              │
│  Skip staples: bread, flour, oils, salt, rice, pasta         │
│                                                              │
│  → Stored in flavor_preferences table (preference_score)     │
│    +1 = like, -1 = dislike                                   │
│                                                              │
│  After 20+ total selections, suggest "Continue" but allow    │
│  user to keep adding more.                                   │
└─────────────────────────────────────────────────────────────┘
```

**Categories to show** (from `ingredients.category`):
- Proteins: `poultry`, `beef`, `pork`, `fish`, `shellfish`, `lamb_game`
- Vegetables: `vegetables_leafy`, `vegetables_root`, `vegetables_nightshade`, `vegetables_cruciferous`
- Fruits: `fruits_citrus`, `fruits_berries`, `fruits_tropical`, `fruits_stone`
- Spices: `spices`, `herbs_fresh`

**Categories to SKIP** (too basic to be preference signals):
- `bread`, `pasta`, `rice`, `noodles_asian`
- `oils`, `vinegar`, `pantry_staples`
- `eggs`, `dairy_milk` (unless user has restrictions)

**Storage:**
- Pantry items → `initial_inventory` in payload (later: inventory table)
- Cuisines → `cuisine_preferences` in payload (later: preferences.favorite_cuisines)
- Likes/dislikes → `flavor_preferences` table with `preference_score` (+1/-1)

**Future expansion:**
- Use embeddings to suggest "more like these" based on likes
- Category browsing UI (show all proteins, etc.)
- Build detailed preference map as recommendation features develop

---

## 1. Executive Summary

This spec defines an adaptive onboarding system for Alfred that collects user preferences through a progressive flow—from deterministic form inputs to graph-based discovery to template-driven style selection—outputting a structured payload for Alfred integration.

### Design Principles

1. **Deterministic first, conversational second** — Hard constraints via forms, soft preferences via LLM dialogue
2. **Isolated module** — Lives outside Alfred's graph; outputs payload at end
3. **Minimal data model changes** — Use existing `preferences` schema + `subdomain_guidance` + `stylistic_examples`
4. **Iteratable foundation** — Each component can be tuned independently
5. **Show, don't ask** — LLM proposes examples with justification; user reacts, LLM adapts
6. **Pantry-aware generation** — Samples use user's actual ingredients for immediate value
7. **Constraint filtering throughout** — Phase 1 constraints filter all subsequent suggestions
8. **Store more than you wire** — Full interaction history archived; only summaries wired to Alfred

### Key Output

```python
OnboardingPayload = {
    "preferences": {...},           # Hard constraints
    "subdomain_guidance": {...},    # Narrative personalization (5 keys)
    "initial_inventory": [...],     # Pantry seed data
    "ingredient_preferences": [...], # Discovered taste profile
    "cuisine_preferences": [...],   # Selected cuisines (simple list)
}
```

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ONBOARDING SYSTEM                                    │
│                     (Isolated from Alfred Graph)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   PHASE 1          PHASE 2           PHASE 3          PHASE 4               │
│   ─────────        ─────────         ─────────        ─────────             │
│   Deterministic    Discovery &       Style            Final                 │
│   Forms            Seeding           Selection        Preview               │
│                                                                              │
│   ┌─────────┐     ┌─────────┐       ┌─────────┐      ┌─────────┐           │
│   │ Hard    │     │Pantry   │       │ Recipe  │      │ Sample  │           │
│   │Constr-  │────▶│ Seed    │──────▶│ Style   │─────▶│ Recipes │           │
│   │ aints   │     │         │       │(visual) │      │         │           │
│   └─────────┘     └─────────┘       └─────────┘      └─────────┘           │
│        │               │                 │                │                 │
│        │          ┌─────────┐       ┌─────────┐           │                 │
│        │          │Ingredient│      │MealPlan │           │                 │
│        │          │Discovery│       │ Style   │           │                 │
│        │          │(graph)  │       │(visual) │           │                 │
│        │          └─────────┘       └─────────┘           │                 │
│        │               │                 │                │                 │
│        │          ┌─────────┐       ┌─────────┐           │                 │
│        │          │ Cuisine │       │ Habits  │           │                 │
│        │          │(select) │       │(LLM,1-2 │           │                 │
│        │          └─────────┘       │ turns)  │           │                 │
│        │               │            └─────────┘           │                 │
│        │               │                 │                │                 │
│        ▼               ▼                 ▼                ▼                 │
│   ┌─────────────────────────────────────────────────────────────┐          │
│   │                    OUTPUT PAYLOAD BUILDER                    │          │
│   └─────────────────────────────────────────────────────────────┘          │
│                                    │                                        │
│                                    ▼                                        │
│                          ┌─────────────────┐                               │
│                          │  Alfred Apply   │                               │
│                          │    Payload      │                               │
│                          └─────────────────┘                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions (v1.2)

| Area | Decision | Rationale |
|------|----------|-----------|
| Cuisine discovery | Simple multi-select | Finite list, embeddings overkill |
| Style discovery | **LLM generation + feedback** | Users can't introspect preferences; LLM proposes, educates, adapts |
| Sample generation | **Pantry-aware** | Immediate value demonstration, builds trust |
| Preference storage | **Full interactions stored** | `stylistic_examples` wired; history archived for future |
| Feedback loop | Logged only (MVP) | Avoid complexity, iterate later |
| State management | Separate states per category | Cleaner transitions |
| Alfred integration | Inject examples as tone guides | Per-subdomain stylistic reference |

---

## 3. Code Organization

```
src/
├── alfred/                    # EXISTING - DO NOT MODIFY
│   └── ...
│
├── onboarding/                # NEW - Isolated module
│   ├── __init__.py
│   │
│   ├── # Shared
│   ├── constants.py           # Allergens, equipment, cuisines lists (reuse from Alfred if exists)
│   ├── filters.py             # Constraint filtering (exclude allergens, dietary conflicts)
│   ├── state.py               # Onboarding session state management
│   │
│   ├── # PHASE 1: Deterministic
│   ├── forms.py               # Form field definitions, validation
│   │
│   ├── # PHASE 2: Discovery & Seeding
│   ├── pantry.py              # Pantry seeding with ingredient search
│   ├── ingredient_discovery.py # Graph-based ingredient exploration (separate from cuisine)
│   ├── cuisine_selection.py   # Simple multi-select for cuisines
│   ├── similarity.py          # Embedding/category-based similarity (ingredients only)
│   │
│   ├── # PHASE 3: Style Selection
│   ├── style_templates.py     # Predefined guidance templates (no LLM)
│   ├── llm_habits.py          # LLM interpreter for free-form habits ONLY
│   │
│   ├── # PHASE 4: Final Preview
│   ├── preview_generator.py   # Sample recipe/meal plan generation
│   ├── feedback.py            # Feedback logging (no real-time adjustment for MVP)
│   │
│   ├── # Output
│   ├── payload.py             # Final payload assembly + apply function
│   └── api.py                 # HTTP endpoints
│
└── frontend/
    └── src/
        └── onboarding/        # React components (minimal for MVP)
            ├── OnboardingFlow.tsx
            ├── steps/
            │   ├── ConstraintsStep.tsx
            │   ├── PantryStep.tsx
            │   ├── IngredientDiscoveryStep.tsx
            │   ├── CuisineSelectionStep.tsx
            │   ├── StyleSelectionStep.tsx
            │   ├── HabitsStep.tsx
            │   └── PreviewStep.tsx
            └── components/
                ├── IngredientSearch.tsx
                ├── DiscoveryCards.tsx
                ├── CuisineChips.tsx
                └── StyleExampleCard.tsx
```

### Code Organization Principles

1. **Separate files for separate flows** — `ingredient_discovery.py` vs `cuisine_selection.py` (not one generic discovery)
2. **Shared utilities in dedicated files** — `constants.py`, `filters.py` 
3. **Clear LLM boundary** — Only `llm_habits.py` makes LLM calls; style selection uses templates
4. **Reuse Alfred constants where possible** — Don't duplicate allergen lists, equipment options

---

## 4. Phase 1: Deterministic Forms

### 4.1 Purpose

Collect hard constraints that:
- **Must be machine-readable** (for filtering)
- **Have clear, finite options** (no interpretation needed)
- **Are critical for safety** (allergies, restrictions)

### 4.2 Data Points

| Field | UI Type | Options | Required |
|-------|---------|---------|----------|
| `household_size` | Numeric stepper | 1-12 | Yes |
| `allergies` | Tokenized search | From common allergens list | No |
| `dietary_restrictions` | Multi-select chips | vegetarian, vegan, pescatarian, halal, kosher, gluten-free, dairy-free, low-carb | No |
| `cooking_skill_level` | Single select cards | beginner, intermediate, advanced | Yes |
| `available_equipment` | Visual checklist | instant-pot, air-fryer, slow-cooker, sous-vide, grill, blender, food-processor, dutch-oven | No |

### 4.3 Implementation

```python
# onboarding/forms.py

from pydantic import BaseModel, Field
from typing import Literal

class ConstraintsForm(BaseModel):
    """Phase 1: Hard constraints form data."""
    
    household_size: int = Field(ge=1, le=12, default=2)
    allergies: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    cooking_skill_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    available_equipment: list[str] = Field(default_factory=list)

# Validation
VALID_RESTRICTIONS = {
    "vegetarian", "vegan", "pescatarian", "halal", "kosher",
    "gluten-free", "dairy-free", "low-carb", "keto", "paleo"
}

COMMON_ALLERGENS = [
    "peanuts", "tree nuts", "shellfish", "fish", "eggs",
    "milk", "soy", "wheat", "sesame"
]

EQUIPMENT_OPTIONS = [
    {"id": "instant-pot", "label": "Instant Pot", "icon": "🍲"},
    {"id": "air-fryer", "label": "Air Fryer", "icon": "🍟"},
    {"id": "slow-cooker", "label": "Slow Cooker", "icon": "🥘"},
    {"id": "sous-vide", "label": "Sous Vide", "icon": "🌡️"},
    {"id": "grill", "label": "Grill/BBQ", "icon": "🔥"},
    {"id": "blender", "label": "Blender", "icon": "🥤"},
    {"id": "food-processor", "label": "Food Processor", "icon": "🔪"},
    {"id": "dutch-oven", "label": "Dutch Oven", "icon": "🫕"},
    {"id": "wok", "label": "Wok", "icon": "🥡"},
    {"id": "stand-mixer", "label": "Stand Mixer", "icon": "🎂"},
]
```

### 4.4 UI Flow

```
Screen 1: "Who are you cooking for?"
          [Numeric stepper: 1-12 people]
          [Skip → defaults to 2]

Screen 2: "Any food allergies?"
          [Tokenized input with autocomplete]
          [Common allergens as quick-add chips]
          [None button]

Screen 3: "Dietary preferences?"
          [Multi-select chips]
          [None/Skip button]

Screen 4: "How would you describe your cooking?"
          [3 cards with illustrations]
          - Beginner: "Learning the basics"
          - Intermediate: "Comfortable improvising"  
          - Advanced: "Techniques come naturally"

Screen 5: "What equipment do you have?"
          [Visual grid with icons]
          [Skip → assumes basic stovetop/oven]
```

---

## 5. Phase 2: Graph-Based Discovery

### 5.1 Pantry Seeding

**Purpose:** Get initial inventory + signal ingredient preferences.

**UI:**
```
┌─────────────────────────────────────────────────────────────────┐
│  What's in your pantry right now?                               │
│                                                                  │
│  [🔍 Search ingredients...                              ]       │
│                                                                  │
│  Quick add common staples:                                      │
│  [Olive oil] [Salt] [Pepper] [Garlic] [Onions] [Butter]        │
│  [Eggs] [Rice] [Pasta] [Chicken] [Soy sauce] [...more]         │
│                                                                  │
│  Your pantry (12 items):                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🥚 Eggs          🧈 Butter       🍚 Rice                │   │
│  │ 🍝 Pasta         🧄 Garlic       🧅 Onions              │   │
│  │ 🫒 Olive oil     🧂 Salt         🌶️ Chili flakes        │   │
│  │ 🍗 Chicken       🥫 Tomatoes     🥬 Spinach             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  [That's enough for now →]    (nudge after ~10-15 items)       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**

```python
# onboarding/pantry.py

from alfred.db.client import get_service_client

async def search_ingredients(query: str, limit: int = 10) -> list[dict]:
    """
    Search ingredients database for pantry seeding.
    Uses existing ingredients table with pg_trgm similarity.
    """
    client = get_service_client()
    
    # Use similarity search (already implemented in Alfred)
    result = client.rpc(
        "search_ingredients_fuzzy",
        {"search_query": query, "limit_count": limit}
    ).execute()
    
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "icon": get_category_icon(row["category"]),
        }
        for row in result.data
    ]

def get_common_staples(cuisines: list[str] | None = None) -> list[dict]:
    """
    Get common pantry staples, optionally weighted by cuisine preferences.
    """
    base_staples = [
        {"name": "olive oil", "category": "pantry"},
        {"name": "salt", "category": "spices"},
        {"name": "black pepper", "category": "spices"},
        {"name": "garlic", "category": "produce"},
        {"name": "onions", "category": "produce"},
        {"name": "butter", "category": "dairy"},
        {"name": "eggs", "category": "proteins"},
        {"name": "rice", "category": "grains"},
        {"name": "pasta", "category": "grains"},
        {"name": "chicken breast", "category": "proteins"},
    ]
    
    # TODO: Add cuisine-specific staples based on discovery
    # e.g., if cuisines includes "thai" → add fish sauce, coconut milk
    
    return base_staples

PANTRY_NUDGE_THRESHOLD = 12  # Suggest moving on after this many items
```

**Output:**
- `initial_inventory`: List of ingredients to seed into inventory table
- **Signal:** Which ingredients user has → influences discovery phase

### 5.2 Ingredient Discovery (Graph-Based)

**Purpose:** Explore user's taste preferences through similarity-guided selection.

**Algorithm:**

```python
# onboarding/discovery.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class DiscoveryRound:
    """One round of ingredient discovery."""
    round_num: int
    options: list[dict]        # 6 ingredients to show
    selections: list[str]      # User's picks (2-3)
    
@dataclass  
class DiscoveryState:
    """Tracks discovery progress."""
    category: Literal["ingredients", "cuisines"]
    rounds: list[DiscoveryRound]
    preference_vector: list[float] | None = None  # Built from selections

async def generate_discovery_round(
    state: DiscoveryState,
    embeddings_cache: dict,
) -> list[dict]:
    """
    Generate next round of options based on previous selections.
    
    Strategy:
    - Round 1: Diverse seed set (spread across embedding space)
    - Round 2+: 
        - 2-3 options SIMILAR to previous selections
        - 2-3 options DIFFERENT (explore new space)
    
    This creates a "taste map" of what user gravitates toward.
    """
    if state.rounds == []:
        # Round 1: Diverse seeding
        return await get_diverse_seed_options(state.category)
    
    # Build preference vector from all selections so far
    all_selections = []
    for round in state.rounds:
        all_selections.extend(round.selections)
    
    preference_vector = compute_preference_centroid(
        all_selections, 
        embeddings_cache
    )
    
    # Get similar options (close to preference vector)
    similar = await get_similar_options(
        preference_vector,
        exclude=all_selections,
        count=3,
    )
    
    # Get diverse options (far from preference vector, but not already shown)
    diverse = await get_diverse_options(
        preference_vector,
        exclude=all_selections + [o["id"] for o in similar],
        count=3,
    )
    
    return similar + diverse

def compute_preference_centroid(
    selections: list[str],
    embeddings: dict[str, list[float]],
) -> list[float]:
    """Average embedding of all selected items."""
    vectors = [embeddings[s] for s in selections if s in embeddings]
    if not vectors:
        return []
    
    # Simple centroid (could weight by recency)
    import numpy as np
    return np.mean(vectors, axis=0).tolist()
```

**UI Flow:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Which of these do you enjoy cooking with?                      │
│  (Pick 2-3 that appeal to you)                                  │
│                                                                  │
│  Round 1:                                                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                           │
│  │ 🍗      │ │ 🧈      │ │ 🐟      │                           │
│  │ Chicken │ │  Tofu   │ │ Salmon  │                           │
│  │         │ │ [✓]     │ │ [✓]     │                           │
│  └─────────┘ └─────────┘ └─────────┘                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                           │
│  │ 🥩      │ │ 🦐      │ │ 🫘      │                           │
│  │  Beef   │ │ Shrimp  │ │ Lentils │                           │
│  │         │ │ [✓]     │ │         │                           │
│  └─────────┘ └─────────┘ └─────────┘                           │
│                                                                  │
│  [Continue →]                                                   │
│                                                                  │
│  Round 2: (after selections)                                    │
│  Similar to your picks:   Different directions:                 │
│  [Cod] [Scallops] [Crab]  [Lamb] [Tempeh] [Chickpeas]          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Rounds:** 4-5 rounds typically sufficient to build preference profile.

### 5.3 Cuisine Selection (Simplified)

**Why not graph-based?** Cuisines are a finite, well-known list. Users already know what cuisines they like. Graph-based discovery adds complexity without proportional value here.

**Implementation: Simple multi-select with visual chips**

```python
# onboarding/cuisine_selection.py

CUISINE_OPTIONS = [
    {"id": "italian", "label": "Italian", "icon": "🇮🇹"},
    {"id": "thai", "label": "Thai", "icon": "🇹🇭"},
    {"id": "mexican", "label": "Mexican", "icon": "🇲🇽"},
    {"id": "indian", "label": "Indian", "icon": "🇮🇳"},
    {"id": "japanese", "label": "Japanese", "icon": "🇯🇵"},
    {"id": "mediterranean", "label": "Mediterranean", "icon": "🫒"},
    {"id": "chinese", "label": "Chinese", "icon": "🇨🇳"},
    {"id": "korean", "label": "Korean", "icon": "🇰🇷"},
    {"id": "french", "label": "French", "icon": "🇫🇷"},
    {"id": "middle-eastern", "label": "Middle Eastern", "icon": "🧆"},
    {"id": "vietnamese", "label": "Vietnamese", "icon": "🇻🇳"},
    {"id": "american", "label": "American", "icon": "🇺🇸"},
    {"id": "greek", "label": "Greek", "icon": "🇬🇷"},
    {"id": "spanish", "label": "Spanish", "icon": "🇪🇸"},
    {"id": "caribbean", "label": "Caribbean", "icon": "🏝️"},
]

MAX_CUISINE_SELECTIONS = 5  # Prevent "select all" syndrome

def validate_cuisine_selections(selections: list[str]) -> list[str]:
    """Validate and cap cuisine selections."""
    valid = [s for s in selections if s in {c["id"] for c in CUISINE_OPTIONS}]
    return valid[:MAX_CUISINE_SELECTIONS]
```

**UI:**

```
┌─────────────────────────────────────────────────────────────────┐
│  What cuisines do you enjoy cooking?                            │
│  (Select up to 5)                                               │
│                                                                  │
│  [🇮🇹 Italian]  [🇹🇭 Thai ✓]  [🇲🇽 Mexican]  [🇮🇳 Indian ✓]      │
│  [🇯🇵 Japanese ✓] [🫒 Mediterranean] [🇨🇳 Chinese] [🇰🇷 Korean]   │
│  [🇫🇷 French]  [🧆 Middle Eastern]  [🇻🇳 Vietnamese] [🇺🇸 American]│
│                                                                  │
│  Selected: Thai, Indian, Japanese (3/5)                         │
│                                                                  │
│  [Continue →]                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Output:** Simple list in payload: `cuisine_preferences: ["thai", "indian", "japanese"]`

**Note:** This list is used to:
1. Seed cuisine-specific staples in pantry suggestions
2. Inform recipe generation preferences
3. Populate subdomain_guidance["recipes"] narrative

### 5.4 Constraint Filtering (Critical)

**Principle:** Phase 1 constraints MUST filter all subsequent suggestions.

```python
# onboarding/filters.py

from typing import Set

# Ingredient exclusions by dietary restriction
RESTRICTION_EXCLUSIONS: dict[str, Set[str]] = {
    "vegetarian": {"chicken", "beef", "pork", "fish", "salmon", "shrimp", "lamb", "bacon"},
    "vegan": {"chicken", "beef", "pork", "fish", "salmon", "shrimp", "lamb", "bacon", 
              "eggs", "milk", "cheese", "butter", "cream", "yogurt", "honey"},
    "pescatarian": {"chicken", "beef", "pork", "lamb", "bacon"},
    "halal": {"pork", "bacon", "ham"},
    "kosher": {"pork", "bacon", "ham", "shellfish", "shrimp", "crab", "lobster"},
    "dairy-free": {"milk", "cheese", "butter", "cream", "yogurt", "sour cream"},
    "gluten-free": {"pasta", "bread", "flour", "couscous", "barley"},
}

def get_excluded_ingredients(
    dietary_restrictions: list[str],
    allergies: list[str],
) -> Set[str]:
    """
    Build set of ingredients to exclude based on user constraints.
    
    Used in:
    - Ingredient discovery (filter seed and subsequent options)
    - Common staples suggestions
    - Recipe generation
    """
    excluded = set()
    
    # Add dietary exclusions
    for restriction in dietary_restrictions:
        excluded.update(RESTRICTION_EXCLUSIONS.get(restriction.lower(), set()))
    
    # Add allergy exclusions (direct match + common derivatives)
    for allergen in allergies:
        allergen_lower = allergen.lower()
        excluded.add(allergen_lower)
        
        # Common allergen derivatives
        if allergen_lower == "peanuts":
            excluded.update({"peanut butter", "peanut oil", "peanut sauce"})
        elif allergen_lower == "tree nuts":
            excluded.update({"almonds", "walnuts", "cashews", "pecans", "pistachios"})
        elif allergen_lower == "shellfish":
            excluded.update({"shrimp", "crab", "lobster", "scallops", "clams", "mussels"})
        elif allergen_lower == "dairy":
            excluded.update({"milk", "cheese", "butter", "cream", "yogurt"})
    
    return excluded

def filter_ingredients(
    ingredients: list[dict],
    excluded: Set[str],
) -> list[dict]:
    """Filter ingredient list against exclusions."""
    return [
        ing for ing in ingredients
        if ing.get("name", "").lower() not in excluded
        and ing.get("id", "").lower() not in excluded
    ]
```

**Usage in discovery:**

```python
# In ingredient_discovery.py

async def generate_discovery_round(state, constraints):
    excluded = get_excluded_ingredients(
        constraints.get("dietary_restrictions", []),
        constraints.get("allergies", []),
    )
    
    # All options filtered before showing to user
    candidates = await get_candidate_ingredients(state)
    filtered = filter_ingredients(candidates, excluded)
    
    return select_diverse_options(filtered, count=6)
```

**This ensures:**
- Vegan users never see meat/dairy options
- Allergic users never see their allergens
- Recipe previews respect all constraints

### 5.5 State Management for Discovery

**Problem:** Sequential discovery flows (ingredients, then cuisines) need clear state transitions.

**Solution:** Separate state objects with explicit completion markers.

```python
# onboarding/state.py

from dataclasses import dataclass, field
from typing import Literal, Any
from enum import Enum

class OnboardingPhase(Enum):
    CONSTRAINTS = "constraints"
    PANTRY = "pantry"
    INGREDIENT_DISCOVERY = "ingredient_discovery"
    CUISINE_SELECTION = "cuisine_selection"
    STYLE_SELECTION = "style_selection"
    HABITS = "habits"
    PREVIEW = "preview"
    COMPLETE = "complete"

@dataclass
class IngredientDiscoveryState:
    """State for ingredient discovery only."""
    rounds: list[dict] = field(default_factory=list)
    completed: bool = False
    preference_scores: list[dict] = field(default_factory=list)

@dataclass
class OnboardingState:
    """
    Main onboarding session state.
    
    Key design: Separate state objects for each discovery type.
    When ingredient discovery completes, its results go to payload_draft
    BEFORE cuisine selection begins.
    """
    user_id: str
    current_phase: OnboardingPhase = OnboardingPhase.CONSTRAINTS
    
    # Phase 1 outputs
    constraints: dict = field(default_factory=dict)
    
    # Phase 2 states (separate, not overloaded)
    pantry_items: list[dict] = field(default_factory=list)
    ingredient_discovery: IngredientDiscoveryState = field(default_factory=IngredientDiscoveryState)
    cuisine_selections: list[str] = field(default_factory=list)
    
    # Phase 3 outputs (direct template assignment)
    style_selections: dict = field(default_factory=dict)  # {recipe: "chef", meal_plan: "balanced", ...}
    habits_summary: str = ""  # From LLM extraction
    
    # Accumulated payload (built incrementally)
    payload_draft: dict = field(default_factory=dict)
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""

def transition_phase(state: OnboardingState) -> OnboardingPhase:
    """
    Determine next phase based on current state.
    
    Each phase must be explicitly completed before moving on.
    This prevents state confusion between discovery flows.
    """
    phase = state.current_phase
    
    if phase == OnboardingPhase.CONSTRAINTS:
        if state.constraints:
            return OnboardingPhase.PANTRY
    
    elif phase == OnboardingPhase.PANTRY:
        # Pantry can be skipped, but trigger ingredient discovery
        return OnboardingPhase.INGREDIENT_DISCOVERY
    
    elif phase == OnboardingPhase.INGREDIENT_DISCOVERY:
        if state.ingredient_discovery.completed:
            # IMPORTANT: Save ingredient preferences to payload before moving on
            state.payload_draft["ingredient_preferences"] = state.ingredient_discovery.preference_scores
            return OnboardingPhase.CUISINE_SELECTION
    
    elif phase == OnboardingPhase.CUISINE_SELECTION:
        if state.cuisine_selections:
            state.payload_draft["cuisine_preferences"] = state.cuisine_selections
            return OnboardingPhase.STYLE_SELECTION
    
    # ... etc
    
    return phase  # Stay in current phase if not ready
```

**Persistence:**

```sql
-- Simple session table
CREATE TABLE onboarding_sessions (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    state JSONB NOT NULL,  -- Serialized OnboardingState
    current_phase TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update timestamp
CREATE TRIGGER update_onboarding_timestamp
    BEFORE UPDATE ON onboarding_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### 5.6 Ingredient Preferences Storage

**Open Question:** How do we store and use ingredient preferences?

**Options:**

| Approach | Pros | Cons |
|----------|------|------|
| **A) Store all as "preferred"** | Simple | No ranking, binary |
| **B) Store with selection order** | Implicit ranking | May not reflect true preference |
| **C) Store with round + position** | Rich signal | Complex to query |
| **D) Compute preference score** | Single value per ingredient | Requires scoring algorithm |

**Recommended: Option D with simple scoring**

```python
# onboarding/ingredient_discovery.py

def compute_ingredient_preference_scores(
    discovery_state: IngredientDiscoveryState,
) -> list[dict]:
    """
    Compute preference scores from discovery rounds.
    
    Scoring:
    - Selected = +1 base
    - Earlier round selection = +0.2 bonus (stronger signal)
    - Selected over similar options = +0.1 bonus
    
    Output: List of {ingredient_id, name, preference_score} for score > 0
    """
    scores = {}
    total_rounds = len(discovery_state.rounds)
    
    for round_data in discovery_state.rounds:
        round_num = round_data.get("round_num", 0)
        round_bonus = (total_rounds - round_num) * 0.2
        
        for selection in round_data.get("selections", []):
            ing_id = selection.get("id") or selection
            scores[ing_id] = scores.get(ing_id, 0) + 1 + round_bonus
    
    return [
        {"ingredient_id": ing_id, "preference_score": round(score, 2)}
        for ing_id, score in scores.items()
    ]
```

**Storage options (for later Alfred integration):**

```sql
-- Option 1: New table (requires migration)
CREATE TABLE user_ingredient_preferences (
    user_id UUID REFERENCES users(id),
    ingredient_id UUID REFERENCES ingredients(id),
    preference_score NUMERIC DEFAULT 1.0,
    source TEXT DEFAULT 'onboarding',  -- 'onboarding', 'cooking_log', 'explicit'
    PRIMARY KEY (user_id, ingredient_id)
);

-- Option 2: Store in preferences.subdomain_guidance as structured text
-- "Preferred proteins: salmon, shrimp, tofu. Preferred produce: garlic, spinach..."
-- Less queryable but no schema change
```

**Decision:** For MVP, store in output payload. Alfred integration decides final storage. This keeps onboarding isolated.

---

## 6. Phase 3: Conversational Style Discovery

### 6.1 Purpose

Capture subjective preferences through **LLM-guided generation + feedback loops**:
- **Recipe style** (detail level, chef tips, etc.)
- **Meal planning style** (batch vs daily, leftovers, variety)
- **Task/reminder style** (detail level, timing)
- **Cooking & shopping habits** (frequency, leftovers, shopping routine)

### 6.2 Key Design: LLM Generation + Feedback Loop

**Why NOT use template selection?**
- Users don't know what kind of meal planner they are
- Predefined options are reductive — can't capture nuance
- Template selection puts burden on user to introspect
- LLM can propose, explain, and adapt based on feedback

**The pattern for each style domain:**

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM GENERATION                                                  │
│  ─────────────────                                              │
│  • Generate 2-3 samples in different styles                     │
│  • Use pantry items + cuisine preferences as ingredients        │
│  • Explain WHY each style might suit user                       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  USER FEEDBACK                                                   │
│  ─────────────────                                              │
│  • Pick favorite OR give natural language feedback              │
│  • "I like #1 but want more timing info"                        │
│  • Can ask for different options                                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  LLM SYNTHESIS                                                   │
│  ─────────────────                                              │
│  • Distill feedback into guidance narrative                     │
│  • Store selected example as stylistic reference                │
│  • → subdomain_guidance[domain]                                 │
│  • → stylistic_examples[domain]                                 │
└─────────────────────────────────────────────────────────────────┘
```

**LLM calls:** ~2 per domain (generate + synthesize) × 4 domains = **~8 calls**

This is fine. Each call creates durable value that shapes Alfred forever.

### 6.3 Why Pantry-Aware Generation Matters

The LLM generates samples using:
- **Pantry items** from Phase 2 ("using the shrimp you have")
- **Cuisine preferences** from Phase 2 ("Thai-inspired, as you mentioned")
- **Constraints** from Phase 1 (respects allergies, dietary restrictions)

**This creates immediate value:** User sees their data producing personalized output.
It validates the onboarding effort and builds trust.

### 6.4 The Conversational Aspect

Users shouldn't fill out forms about ambiguous concepts like "meal planning style."
The LLM should **educate** them on what's possible:

```
LLM: "Here are three ways I could plan your meals. Each has tradeoffs..."

Option A: "Batch & Flow" — Cook Sunday, eat variations all week
Option B: "Fresh Daily" — Cook each night, but I'll keep it quick
Option C: "Hybrid" — Big cook Sunday, one quick cook Wednesday

"Which feels more like you? Or tell me what you'd change."

User: "A, but I need flexibility for Thursdays — sometimes we eat out"

LLM: "Got it — batch cooking with Thursday flex. I'll plan around that."
```

The LLM isn't just capturing a choice — it's **teaching** the user what Alfred can do.

### 6.5 Recipe Style Discovery

```python
# onboarding/style_discovery.py

from pydantic import BaseModel
from alfred.llm.client import call_llm

class RecipeSample(BaseModel):
    """A generated recipe sample for style discovery."""
    id: str
    title: str
    style_name: str                    # "Quick & Clean", "Full Instructions", "Chef Mode"
    style_tags: list[str]              # ["concise", "chef_tips", "technique_focus"]
    recipe_text: str                   # The actual recipe content
    why_this_style: str                # LLM explains why user might like this

class RecipeStyleProposal(BaseModel):
    """LLM output for recipe style proposal."""
    samples: list[RecipeSample]
    intro_message: str                 # "Here are three ways I could write recipes..."

RECIPE_STYLE_PROMPT = """You are helping a new Alfred user discover their preferred recipe style.

**User Context:**
- Skill level: {skill_level}
- Pantry includes: {pantry_items}
- Likes cuisines: {cuisines}
- Dietary: {dietary}

Generate 3 recipe samples for the SAME dish (choose something that uses their pantry items).
Each sample should demonstrate a DIFFERENT style:

1. **Quick & Clean** — Minimal steps, just essentials, assumes competence
2. **Full Instructions** — Clear step-by-step, timing included, no assumptions
3. **Chef Mode** — Technique tips, "why" explanations, upgrades and hacks

For each, explain briefly why this style might suit them.

Make the recipes feel PERSONAL — use their actual ingredients."""

async def generate_recipe_style_samples(
    payload_draft: dict,
) -> RecipeStyleProposal:
    """
    Generate recipe samples for style discovery.
    
    Uses user's pantry + preferences to make it personal.
    """
    preferences = payload_draft.get("preferences", {})
    
    prompt = RECIPE_STYLE_PROMPT.format(
        skill_level=preferences.get("cooking_skill_level", "intermediate"),
        pantry_items=", ".join(
            item["name"] for item in payload_draft.get("initial_inventory", [])[:8]
        ) or "standard pantry staples",
        cuisines=", ".join(payload_draft.get("cuisine_preferences", [])) or "various",
        dietary=", ".join(preferences.get("dietary_restrictions", [])) or "none",
    )
    
    return await call_llm(
        response_model=RecipeStyleProposal,
        system_prompt=prompt,
        user_prompt="Generate 3 recipe style samples.",
        complexity="medium",
    )
```

**Example output:**

```
LLM: "Here are three ways I could write you a Thai Coconut Shrimp recipe — 
      using that shrimp and coconut milk in your pantry..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🥢 OPTION A: Quick & Clean
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thai Coconut Shrimp
• Sauté shrimp 2min/side → set aside
• Bloom curry paste in same pan (30 sec)
• Add coconut milk, simmer 3 min
• Return shrimp, toss with basil

*~12 min | Good for: experienced cooks who want speed*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 OPTION B: Full Instructions  
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thai Coconut Shrimp (Serves 2)
1. Pat 1lb shrimp dry with paper towels
2. Heat 1 tbsp oil over medium-high heat
3. Add shrimp in single layer, cook 2 min
4. Flip shrimp, cook 1 min more until pink
5. Transfer shrimp to plate
6. Add 1 tbsp curry paste to pan, stir 30 sec
7. Pour in 1 can coconut milk, stir to combine
8. Simmer 3 minutes until slightly thickened
9. Return shrimp, toss to coat
10. Garnish with fresh basil

*~15 min | Good for: clear guidance with no guesswork*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👨‍🍳 OPTION C: Chef Mode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thai Coconut Shrimp
1. **Dry shrimp** — moisture = no sear, sad shrimp
2. **High heat.** Oil shimmering. Single layer or they steam.
3. **Don't touch** for 2 min — let the Maillard do its thing
4. **Pull early** — carryover finishes them
5. **Same pan** — curry paste hits hot oil, blooms instantly
6. **Coconut milk** — stir from the edges, scrape the fond
7. **3 min simmer** — reduce slightly, not cement

🔥 **Upgrade:** Fish sauce + lime at the end. Trust me.
📦 **Tomorrow:** This sauce → noodle bowl
```

### 6.6 Meal Plan Style Discovery

Same pattern as recipes. LLM proposes planning approaches, explains tradeoffs, user picks or critiques.

```python
MEAL_PLAN_STYLE_PROMPT = """You are helping a new Alfred user discover their preferred meal planning style.

**User Context:**
- Household: {household_size} people
- Skill level: {skill_level}
- Cuisines: {cuisines}
- Pantry has: {pantry_items}

Generate 3 example MEAL PLANS (same week, different styles):

1. **Minimal** — Just meals and days, no logistics
2. **Practical** — Cooking days, batch notes, leftover flow
3. **Detailed** — Full calendar with prep tasks and shopping

Use their actual pantry items and cuisines where possible.
Explain why each style might suit them."""

class MealPlanSample(BaseModel):
    id: str
    style_name: str
    plan_text: str
    why_this_style: str
```

**Example conversation:**

```
LLM: "Here are three ways I could plan your meals this week..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 OPTION A: Minimal
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mon: Thai Shrimp Curry
Tue: Leftover curry
Wed: Quick pasta
Thu: Takeout
Fri: Fish tacos

*Good for: You decide the details. I just remind you what's cooking.*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 OPTION B: Practical
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Cook Sunday:** Thai Curry (makes 4 servings)
- Mon dinner: Curry
- Tue lunch: Curry + rice
- Tue dinner: Curry noodle bowl (transform!)

**Cook Wed:** Quick pasta (20 min)

Thu: Flex night
Fri: Fish tacos (fresh, 30 min)

*Good for: See the batch flow, know when to cook.*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 OPTION C: Detailed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
| Day | Lunch      | Dinner        | Prep          |
|-----|------------|---------------|---------------|
| Sun | —          | Thai Curry    | Cook PM       |
| Mon | Curry      | Curry         |               |
| Tue | Curry bowl | Pasta         | —             |
| Wed | Pasta      | Flex          | Thaw fish     |
| Thu | Leftovers  | Takeout       |               |
| Fri | Salad      | Fish Tacos    | Cook fresh    |

**Shopping:** Fish, tortillas, cilantro

*Good for: Full visibility. No surprises.*

User: "B is good, but can you include a shopping list summary?"

LLM: "Got it — practical plans with batch flow AND shopping list."
```

### 6.7 Feedback Synthesis (The Key Step)

After user gives feedback, LLM synthesizes into:
1. **Guidance narrative** → `subdomain_guidance[domain]`
2. **Stylistic example** → `stylistic_examples[domain]`

```python
# onboarding/style_discovery.py

class StyleFeedbackSynthesis(BaseModel):
    """LLM output after user provides feedback."""
    
    # What goes to subdomain_guidance
    guidance_summary: str  # "Prefers concise recipes with chef tips and timing cues."
    
    # The selected/refined example (for few-shot reference)
    stylistic_example: dict  # The sample they liked, possibly adjusted
    
    # Reflection for user
    acknowledgment: str  # "Got it — concise with technique notes."

SYNTHESIS_PROMPT = """The user just completed recipe style selection.

**Samples shown:**
{samples_shown}

**User's response:**
Selection: {selection}
Feedback: "{feedback}"

Synthesize their preference into:
1. A brief guidance summary (1-2 sentences) that Alfred can use to shape all future recipes
2. The stylistic example (either the one they picked, or adjusted based on feedback)
3. A short acknowledgment to show the user

Be specific and actionable."""

async def synthesize_style_feedback(
    domain: str,
    samples_shown: list[dict],
    user_selection: str | None,
    user_feedback: str,
) -> StyleFeedbackSynthesis:
    """
    Synthesize user feedback into guidance + example.
    
    This is the LLM call that converts the interaction into durable preference.
    """
    prompt = SYNTHESIS_PROMPT.format(
        samples_shown=format_samples(samples_shown),
        selection=user_selection or "None - gave feedback instead",
        feedback=user_feedback,
    )
    
    return await call_llm(
        response_model=StyleFeedbackSynthesis,
        system_prompt=prompt,
        user_prompt=f"Synthesize {domain} style preference.",
        complexity="low",
    )

def apply_style_synthesis(
    state: "OnboardingState",
    domain: str,
    synthesis: StyleFeedbackSynthesis,
    samples_shown: list[dict],
    user_feedback: str,
) -> None:
    """
    Apply synthesis to state and payload.
    
    - Guidance summary → subdomain_guidance
    - Stylistic example → stylistic_examples
    - Full interaction → preference_interactions (stored, not wired)
    """
    # WIRED TO ALFRED
    state.payload_draft.setdefault("subdomain_guidance", {})[domain] = synthesis.guidance_summary
    state.payload_draft.setdefault("stylistic_examples", {})[domain] = synthesis.stylistic_example
    
    # STORED FOR FUTURE (not wired yet)
    interaction = PreferenceInteraction(
        domain=domain,
        samples_shown=[StyleSample(**s) for s in samples_shown],
        user_selection=None,  # Will be set if they picked one
        user_feedback=user_feedback,
        llm_summary=synthesis.guidance_summary,
        stylistic_example=synthesis.stylistic_example,
    )
    state.payload_draft.setdefault("preference_interactions", {})[domain] = interaction
```

### 6.8 Task Style Discovery

Follows same pattern. Brief example:

```
LLM: "How should I remind you about prep tasks?"

A: Just the task — "Thaw chicken"
B: With timing — "Thaw chicken (move to fridge by 6pm)"  
C: Linked to meal — "Thaw chicken for tomorrow's stir-fry"

User: "B — I need the timing or I forget"

→ subdomain_guidance["tasks"] = "Include specific timing and deadlines in task reminders."
→ stylistic_examples["tasks"] = {"task": "Thaw chicken", "timing": "move to fridge by 6pm"}
```

### 6.9 Fallback Defaults (For Skipped Discovery)

If user skips style discovery, use skill-based defaults:

```python
# onboarding/defaults.py

SKILL_BASED_DEFAULTS = {
    "beginner": {
        "recipes": "Full step-by-step recipes. Explain techniques briefly. Include timing cues.",
        "meal_plans": "Simple meal plans. One new recipe per week max. Clear batch cooking notes.",
        "tasks": "Detailed task reminders with time estimates. Explain why each task matters.",
    },
    "intermediate": {
        "recipes": "Clear recipes, skip obvious steps. Include chef tips where relevant.",
        "meal_plans": "Practical plans with batch flow visible. Leftover transformations welcome.",
        "tasks": "Day-before reminders. Link prep to specific meals.",
    },
    "advanced": {
        "recipes": "Concise steps. Focus on technique nuances. Multi-component dishes okay.",
        "meal_plans": "Flexible plans. Assume good time management. Complex dishes welcome.",
        "tasks": "Brief reminders. I know what needs prep.",
    },
}

def get_default_guidance(skill_level: str, domain: str) -> str:
    """Get fallback guidance if user skips discovery."""
    return SKILL_BASED_DEFAULTS.get(skill_level, SKILL_BASED_DEFAULTS["intermediate"]).get(domain, "")
```

### 6.10 Habits Extraction (Final LLM Step)

Cooking and shopping habits are free-form and personal. We ask one open question and extract structured data + narrative summary.

```python
# onboarding/llm_habits.py

from pydantic import BaseModel
from alfred.llm.client import call_llm

class HabitsExtraction(BaseModel):
    """Structured extraction from habits conversation."""
    
    # Cooking habits
    cooking_frequency: str | None = None     # "2-3x/week", "daily", "weekends only"
    batch_cooking: bool | None = None        # Do they batch cook?
    cooking_days: list[str] | None = None    # ["sunday", "wednesday"]
    
    # Leftover preferences
    leftover_tolerance_days: int | None = None  # How many days is okay?
    
    # Shopping habits
    shopping_frequency: str | None = None    # "weekly", "2x/week", "as needed"
    primary_store: str | None = None         # Optional: where they shop
    
    # Inventory style (folded in to reduce questions)
    inventory_tracking: str | None = None    # "strict", "loose", "proteins_only"
    assumed_staples: list[str] | None = None # What they always have
    
    # Narrative summaries (for subdomain_guidance)
    meal_plans_summary: str = ""    # → subdomain_guidance["meal_plans"]
    shopping_summary: str = ""      # → subdomain_guidance["shopping"]  
    inventory_summary: str = ""     # → subdomain_guidance["inventory"]

HABITS_PROMPT = """You are helping onboard a new user to Alfred, a cooking assistant.

Based on their response, extract cooking, shopping, and inventory preferences.

**User's household:** {household_size} people
**Dietary restrictions:** {dietary_restrictions}
**Skill level:** {skill_level}

**User said:**
"{user_response}"

Extract concrete details. If something wasn't mentioned, leave it null.

Write THREE brief summaries (~30-50 words each):
1. meal_plans_summary: Their cooking rhythm and leftover preferences
2. shopping_summary: How/when they shop
3. inventory_summary: How strictly they track inventory, what staples to assume

Be specific and actionable. These summaries will guide Alfred's behavior."""

async def extract_habits(
    user_response: str,
    constraints: dict,
) -> HabitsExtraction:
    """
    Extract habits from user's free-form response.
    
    This complements the style discovery LLM calls.
    """
    prompt = HABITS_PROMPT.format(
        household_size=constraints.get("household_size", 2),
        dietary_restrictions=", ".join(constraints.get("dietary_restrictions", [])) or "None",
        skill_level=constraints.get("cooking_skill_level", "intermediate"),
        user_response=user_response,
    )
    
    return await call_llm(
        response_model=HabitsExtraction,
        system_prompt=prompt,
        user_prompt=user_response,
        complexity="low",
    )
```

**UI Flow:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Last question! Tell me about your cooking routine.             │
│                                                                  │
│  Things that help me help you:                                  │
│  • When do you usually cook? (certain days? weekends?)          │
│  • Do you batch cook or make fresh each time?                   │
│  • How do you feel about leftovers?                             │
│  • How often do you grocery shop?                               │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ I usually cook on Sundays - big batch for the week.     │   │
│  │ Maybe one quick thing Wednesday. Leftovers are fine     │   │
│  │ for 3-4 days. I shop once a week at Costco + farmers    │   │
│  │ market for fresh stuff.                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  [Continue →]                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Output applied:**
- `subdomain_guidance["meal_plans"]` += extracted meal_plans_summary
- `subdomain_guidance["shopping"]` = extracted shopping_summary (dedicated key)
- `subdomain_guidance["inventory"]` = extracted inventory_summary

**Note:** This single question covers what was previously 3 separate LLM nodes.

**Design decision:** Shopping habits get their own `subdomain_guidance["shopping"]` key rather than being folded into `meal_plans`. This keeps domain boundaries clean and makes future shopping-specific features easier to implement.

---

## 7. Phase 4: Final Preview

### 7.1 Purpose

- **Validate** that captured preferences produce good outputs
- **Demonstrate** immediate value ("Alfred gets me")
- **Log feedback** for future analysis (no real-time adjustment in MVP)

### 7.2 Simplified Feedback Strategy

**MVP Decision:** Feedback is **logged only**, not used to adjust guidance in real-time.

**Rationale:**
- Real-time adjustment creates a complex loop (regenerate → re-feedback → ...)
- Users may have feedback fatigue after the main flow
- Post-onboarding refinement is better suited for Alfred's ongoing usage

**Future consideration:** Feed logged feedback into a post-onboarding "preference tuning" flow, or let Alfred's agents learn from cooking history over time.

### 7.3 Sample Recipe Generation

```python
# onboarding/preview_generator.py

async def generate_sample_recipes(
    payload_draft: dict,
    count: int = 3,
) -> list[dict]:
    """
    Generate sample recipes using accumulated preferences.
    
    This uses Alfred's existing recipe generation but with the 
    onboarding payload as context.
    """
    # Build a pseudo user_profile from payload
    profile = {
        "dietary_restrictions": payload_draft["preferences"].get("dietary_restrictions", []),
        "allergies": payload_draft["preferences"].get("allergies", []),
        "cooking_skill_level": payload_draft["preferences"].get("cooking_skill_level", "intermediate"),
        "available_equipment": payload_draft["preferences"].get("available_equipment", []),
        "subdomain_guidance": payload_draft.get("subdomain_guidance", {}),
    }
    
    # Include ingredient preferences in prompt
    preferred_ingredients = [
        p["ingredient_id"] for p in payload_draft.get("ingredient_preferences", [])
    ]
    
    # Include cuisine preferences
    preferred_cuisines = payload_draft.get("cuisine_preferences", [])
    
    # Generate via LLM
    recipes = await generate_recipes_for_onboarding(
        profile=profile,
        preferred_ingredients=preferred_ingredients,
        preferred_cuisines=preferred_cuisines,
        count=count,
    )
    
    return recipes
```

### 7.4 Preview UI

```
┌─────────────────────────────────────────────────────────────────┐
│  Based on everything you've told me, here are some recipe       │
│  ideas you might enjoy:                                         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🍜 Thai Coconut Shrimp Curry                             │   │
│  │ Quick weeknight curry with the shrimp you love.          │   │
│  │ 25 min | Intermediate                                    │   │
│  │ [👍 Looks great!] [👎 Not for me]                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🥗 Miso-Glazed Salmon Bowl                              │   │
│  │ Japanese-inspired with that salmon you mentioned.        │   │
│  │ 30 min | Easy                                            │   │
│  │ [👍 Looks great!] [👎 Not for me]                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🧆 Crispy Chickpea Bowl (vegan shown if user is vegan)   │   │
│  │ Mediterranean spices with ingredients you have.          │   │
│  │ 20 min | Easy                                            │   │
│  │ [👍 Looks great!] [👎 Not for me]                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  [Finish Setup →]                                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.5 Feedback Handling (Logging Only)

```python
# onboarding/feedback.py

from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class PreviewFeedback:
    """Logged feedback on preview recipes."""
    user_id: str
    recipe_summary: str      # Brief description of recipe
    cuisines_used: list[str]
    ingredients_used: list[str]
    feedback: str            # "positive" or "negative"
    timestamp: str

def log_preview_feedback(
    user_id: str,
    recipes: list[dict],
    feedback: list[str],  # ["positive", "negative", "positive"]
) -> None:
    """
    Log feedback for future analysis.
    
    MVP: Log only, no real-time adjustment.
    
    Future use cases:
    - Analyze patterns in negative feedback
    - Identify recipe styles that don't resonate
    - Feed into post-onboarding preference tuning
    """
    for recipe, fb in zip(recipes, feedback):
        entry = PreviewFeedback(
            user_id=user_id,
            recipe_summary=recipe.get("name", "Unknown"),
            cuisines_used=recipe.get("cuisines", []),
            ingredients_used=[ing.get("name") for ing in recipe.get("ingredients", [])[:5]],
            feedback=fb,
            timestamp=datetime.utcnow().isoformat(),
        )
        
        # Log for now - could write to analytics table later
        logger.info(f"Preview feedback: {entry}")
    
    # Future: Write to onboarding_feedback table for analysis
    # await db.table("onboarding_feedback").insert([...]).execute()

def should_show_regenerate_option(feedback: list[str]) -> bool:
    """
    Determine if we should offer to regenerate previews.
    
    If all feedback is negative, something's wrong - offer retry.
    But don't force an iterative loop.
    """
    negative_count = sum(1 for f in feedback if f == "negative")
    return negative_count == len(feedback)  # All negative
```

**Note:** The "Show me different options" button from original spec is removed. If user clicks "Finish Setup", they proceed regardless of feedback. Feedback is purely informational for now.

---

## 8. Output Payload

### 8.1 Final Payload Structure

```python
# onboarding/payload.py

from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass
class StyleSample:
    """A sample shown to user during style selection."""
    id: str
    text: str                           # The actual content shown
    style_tags: list[str] = field(default_factory=list)  # e.g. ["concise", "chef_tips"]

@dataclass 
class PreferenceInteraction:
    """
    Full record of a style selection interaction.
    
    Stored for:
    - Future reference ("You preferred X...")
    - Style clustering / personalization research
    - Potential re-onboarding or preference evolution
    
    NOTE: Only `llm_summary` gets wired into Alfred's prompts.
    The rest is stored but NOT actively used yet.
    """
    domain: Literal["recipes", "meal_plans", "tasks"]
    
    # What LLM proposed (with justification)
    samples_shown: list[StyleSample] = field(default_factory=list)
    llm_justification: str = ""         # Why LLM proposed these options
    
    # User's response
    user_selection: str | None = None   # ID of selected sample (if picked)
    user_feedback: str = ""             # Natural language feedback
    
    # LLM synthesis
    llm_summary: str = ""               # → Goes to subdomain_guidance[domain]
    
    # The chosen example (schema-compliant for future few-shot use)
    stylistic_example: dict | None = None  # Schema TBD per domain

@dataclass
class OnboardingPayload:
    """
    Complete output from onboarding flow.
    
    This is the contract between onboarding and Alfred.
    All data linked by user_id at application time.
    
    WHAT GETS WIRED TO ALFRED (now):
    - preferences → preferences table
    - subdomain_guidance → preferences.subdomain_guidance
    - initial_inventory → inventory table
    - stylistic_examples → preferences.subdomain_guidance + future few-shot
    
    WHAT GETS STORED BUT NOT WIRED (yet):
    - preference_interactions → Full interaction history for future use
    - ingredient_preferences → For future ingredient-aware features
    """
    
    # =========================================================================
    # WIRED TO ALFRED
    # =========================================================================
    
    # Phase 1: Hard constraints (written to preferences table)
    preferences: dict = field(default_factory=lambda: {
        "household_size": 2,
        "allergies": [],
        "dietary_restrictions": [],
        "cooking_skill_level": "intermediate",
        "available_equipment": [],
    })
    
    # Phase 2-3: Narrative guidance (written to preferences.subdomain_guidance)
    # These are the LLM-synthesized summaries from preference_interactions
    subdomain_guidance: dict = field(default_factory=lambda: {
        "recipes": "",      # ← From preference_interactions["recipes"].llm_summary
        "meal_plans": "",   # ← From preference_interactions["meal_plans"].llm_summary
        "shopping": "",     # ← From habits extraction
        "inventory": "",    # ← From habits extraction
        "tasks": "",        # ← From preference_interactions["tasks"].llm_summary
    })
    
    # Phase 3: Stylistic examples per subdomain
    # These are the user-approved examples that define "good output" tone/style
    stylistic_examples: dict = field(default_factory=lambda: {
        "recipes": None,    # Schema-compliant recipe example
        "meal_plans": None, # Schema-compliant meal plan example
        "tasks": None,      # Schema-compliant task example
    })
    
    # Phase 2: Initial pantry (written to inventory table)
    initial_inventory: list[dict] = field(default_factory=list)
    # Each: {"name": str, "category": str, "location": str}
    
    cuisine_preferences: list[str] = field(default_factory=list)
    # List of cuisine IDs in preference order
    
    # =========================================================================
    # STORED BUT NOT WIRED YET
    # =========================================================================
    
    # Full interaction history (for future use)
    preference_interactions: dict[str, PreferenceInteraction] = field(default_factory=dict)
    # Keys: "recipes", "meal_plans", "tasks"
    
    # Phase 2: Discovered ingredient preferences
    ingredient_preferences: list[dict] = field(default_factory=list)
    # Each: {"ingredient_id": uuid, "preference_score": float}
    # Future: Powers ingredient-aware recipe suggestions
    
    # =========================================================================
    # METADATA
    # =========================================================================
    
    onboarding_completed: bool = False
    onboarding_version: str = "1.1"
    
    def to_dict(self) -> dict:
        """Serialize for storage/transfer."""
        return {
            # Wired
            "preferences": self.preferences,
            "subdomain_guidance": self.subdomain_guidance,
            "stylistic_examples": self.stylistic_examples,
            "initial_inventory": self.initial_inventory,
            "cuisine_preferences": self.cuisine_preferences,
            # Stored (not wired)
            "preference_interactions": {
                k: v.__dict__ for k, v in self.preference_interactions.items()
            },
            "ingredient_preferences": self.ingredient_preferences,
            # Metadata
            "onboarding_completed": self.onboarding_completed,
            "onboarding_version": self.onboarding_version,
        }
```

### 8.2 Payload Application (Alfred Integration Point)

```python
# onboarding/payload.py (continued)

async def apply_onboarding_payload(
    user_id: str,
    payload: OnboardingPayload,
) -> None:
    """
    Apply onboarding payload to Alfred's data model.
    
    This is the ONLY integration point with Alfred.
    Called once at end of onboarding flow.
    
    WRITES:
    - preferences table (hard constraints + subdomain_guidance + stylistic_examples)
    - inventory table (initial pantry)
    - onboarding_data table (full payload for future reference)
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    # 1. Update preferences (WIRED TO ALFRED)
    await client.table("preferences").upsert({
        "user_id": user_id,
        **payload.preferences,
        "subdomain_guidance": payload.subdomain_guidance,
        "stylistic_examples": payload.stylistic_examples,  # New field
        "onboarding_completed": True,
    }).execute()
    
    # 2. Seed inventory (WIRED TO ALFRED)
    if payload.initial_inventory:
        inventory_rows = [
            {
                "user_id": user_id,
                "name": item["name"],
                "quantity": 1,
                "unit": "item",
                "location": item.get("location", "pantry"),
            }
            for item in payload.initial_inventory
        ]
        await client.table("inventory").insert(inventory_rows).execute()
    
    # 3. Store full payload for future reference (NOT WIRED YET)
    # This preserves preference_interactions, ingredient_preferences, etc.
    await client.table("onboarding_data").upsert({
        "user_id": user_id,
        "payload": payload.to_dict(),
        "version": payload.onboarding_version,
    }).execute()
```

### 8.3 How Alfred Uses Stylistic Examples

Once onboarding completes, Alfred's generation prompts inject both guidance AND examples:

```python
# In Alfred's prompt injection (src/alfred/prompts/injection.py)

def build_generation_context(user_prefs: Preferences, subdomain: str) -> str:
    """
    Build context section for generation prompts.
    
    Includes:
    1. Narrative guidance (how to behave)
    2. Stylistic example (what good output looks like)
    """
    guidance = user_prefs.subdomain_guidance.get(subdomain, "")
    example = user_prefs.stylistic_examples.get(subdomain)
    
    context = f"""
## User Style Preferences ({subdomain})

{guidance}
"""
    
    if example:
        context += f"""
## Example of User's Preferred Style

{format_example(example)}

Use this as a tone and format reference.
"""
    
    return context
```

**Key insight:** The stylistic example acts as a **few-shot tone guide** — it shows the LLM what "good" looks like for this specific user, without requiring exact schema compliance in the prompt.

---

## 9. API Endpoints

```python
# onboarding/api.py

from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# =============================================================================
# State Management
# =============================================================================

class OnboardingState(BaseModel):
    """Current state of onboarding flow."""
    user_id: str
    current_phase: int  # 1-4
    current_step: str
    payload_draft: dict
    discovery_state: dict | None = None

@router.get("/state")
async def get_onboarding_state(user_id: str) -> OnboardingState:
    """Get current onboarding progress."""
    # Load from session storage
    pass

# =============================================================================
# Phase 1: Forms
# =============================================================================

@router.post("/constraints")
async def submit_constraints(user_id: str, form: ConstraintsForm):
    """Submit hard constraints form."""
    state = await get_state(user_id)
    state.payload_draft["preferences"] = form.dict()
    await save_state(state)
    return {"next_step": "pantry"}

# =============================================================================
# Phase 2: Discovery
# =============================================================================

@router.get("/ingredients/search")
async def search_ingredients(query: str, limit: int = 10):
    """Search ingredients for pantry seeding."""
    return await pantry.search_ingredients(query, limit)

@router.get("/ingredients/staples")
async def get_staples(cuisines: list[str] | None = None):
    """Get common pantry staples."""
    return pantry.get_common_staples(cuisines)

@router.post("/pantry")
async def submit_pantry(user_id: str, items: list[dict]):
    """Submit initial pantry items."""
    state = await get_state(user_id)
    state.payload_draft["initial_inventory"] = items
    await save_state(state)
    return {"next_step": "ingredient_discovery"}

@router.get("/discovery/round")
async def get_discovery_round(user_id: str, category: str):
    """Get next discovery round options."""
    state = await get_state(user_id)
    options = await discovery.generate_discovery_round(
        state.discovery_state,
        category,
    )
    return {"options": options, "round": len(state.discovery_state.rounds) + 1}

@router.post("/discovery/select")
async def submit_discovery_selection(
    user_id: str, 
    category: str, 
    selections: list[str]
):
    """Submit discovery round selections."""
    state = await get_state(user_id)
    # Update discovery state
    # Check if discovery complete
    return {"next_step": "...", "discovery_complete": False}

# =============================================================================
# Phase 3: LLM-Guided
# =============================================================================

@router.get("/examples/{node_id}")
async def get_visual_examples(node_id: str):
    """Get visual examples for a decision node."""
    node = DECISION_TREE[node_id]
    return {"options": node.options}

@router.post("/choice/{node_id}")
async def submit_visual_choice(user_id: str, node_id: str, choice: str):
    """Submit visual example choice."""
    node = DECISION_TREE[node_id]
    template = node.options[choice]["guidance_template"]
    
    state = await get_state(user_id)
    # Apply template to appropriate subdomain_guidance key
    return {"next_step": get_next_step(node_id)}

@router.post("/chat")
async def onboarding_chat(user_id: str, message: str, topic: str):
    """Handle LLM-guided conversation."""
    extraction = await interpreter.extract_from_response(message, topic)
    
    state = await get_state(user_id)
    # Update payload based on extraction
    
    return {
        "response": extraction.summary,
        "extracted": extraction.dict(),
        "topic_complete": True,
    }

# =============================================================================
# Phase 4: Final Preview
# =============================================================================

@router.get("/preview/recipes")
async def preview_recipes(user_id: str, count: int = 3):
    """Generate sample recipes based on current payload."""
    state = await get_state(user_id)
    recipes = await preview_generator.generate_sample_recipes(state.payload_draft, count)
    return {"recipes": recipes}

@router.post("/preview/feedback")
async def submit_preview_feedback(
    user_id: str,
    feedback: list[dict],  # [{recipe_id, sentiment}]
):
    """
    Submit feedback on preview recipes.
    
    MVP: Logs feedback only, no real-time adjustment.
    """
    state = await get_state(user_id)
    log_preview_feedback(user_id, feedback)  # Log only
    await save_state(state)
    return {"status": "logged"}

# =============================================================================
# Complete
# =============================================================================

@router.post("/complete")
async def complete_onboarding(user_id: str):
    """
    Finalize onboarding and apply payload to Alfred.
    
    This is the integration point - applies payload to preferences, 
    inventory, etc.
    """
    state = await get_state(user_id)
    
    # Ensure all required fields have values
    payload = ensure_payload_completeness(state.payload_draft)
    
    # Apply to Alfred
    await apply_onboarding_payload(user_id, payload)
    
    # Clear onboarding session
    await clear_state(user_id)
    
    return {
        "status": "complete",
        "redirect": "/home",  # or wherever
    }
```

---

## 10. Edge Cases & Error Handling

### 10.1 Interrupted Sessions

**Problem:** User drops off mid-onboarding and returns later.

**Solution:**

```python
# onboarding/state.py

async def get_or_create_session(user_id: str) -> OnboardingState:
    """
    Load existing session or create new one.
    
    Called at start of any onboarding endpoint.
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    # Try to load existing session
    result = client.table("onboarding_sessions").select("*").eq("user_id", user_id).execute()
    
    if result.data:
        session_data = result.data[0]
        state = OnboardingState(**json.loads(session_data["state"]))
        return state
    
    # Create new session
    state = OnboardingState(
        user_id=user_id,
        created_at=datetime.utcnow().isoformat(),
    )
    await save_session(state)
    return state

async def save_session(state: OnboardingState) -> None:
    """
    Save session state to database.
    
    Called after every step to ensure durability.
    """
    client = get_service_client()
    
    state.updated_at = datetime.utcnow().isoformat()
    
    await client.table("onboarding_sessions").upsert({
        "user_id": state.user_id,
        "state": json.dumps(asdict(state)),
        "current_phase": state.current_phase.value,
        "updated_at": state.updated_at,
    }).execute()
```

**Frontend handling:**
- On app load, check `GET /onboarding/state`
- If `current_phase != COMPLETE`, redirect to onboarding at that phase
- Show "Welcome back! Let's continue setting up Alfred."

### 10.2 API Errors & Transactions

**Problem:** Partial writes on error (e.g., preferences saved but inventory fails).

**Solution:**

```python
# onboarding/payload.py

async def apply_onboarding_payload(
    user_id: str,
    payload: OnboardingPayload,
) -> dict:
    """
    Apply payload with transaction-like semantics.
    
    Strategy: All-or-nothing with manual rollback capability.
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    applied_steps = []
    
    try:
        # Step 1: Update preferences
        await client.table("preferences").upsert({
            "user_id": user_id,
            **payload.preferences,
            "subdomain_guidance": payload.subdomain_guidance,
        }).execute()
        applied_steps.append("preferences")
        
        # Step 2: Seed inventory (if any)
        if payload.initial_inventory:
            inventory_rows = [
                {
                    "user_id": user_id,
                    "name": item["name"],
                    "quantity": 1,
                    "unit": "item",
                    "location": item.get("location", "pantry"),
                }
                for item in payload.initial_inventory
            ]
            await client.table("inventory").insert(inventory_rows).execute()
            applied_steps.append("inventory")
        
        # Step 3: Mark onboarding complete
        await client.table("preferences").update({
            "onboarding_completed": True,
        }).eq("user_id", user_id).execute()
        applied_steps.append("complete_flag")
        
        # Clean up session
        await client.table("onboarding_sessions").delete().eq("user_id", user_id).execute()
        
        return {"success": True, "applied": applied_steps}
        
    except Exception as e:
        # Log what succeeded for debugging
        logger.error(f"Onboarding apply failed after {applied_steps}: {e}")
        
        # Note: True rollback would require Postgres transactions
        # For MVP, log and surface error to user to retry
        return {
            "success": False,
            "error": str(e),
            "partial_applied": applied_steps,
        }
```

**Retry strategy:**
- If `apply_onboarding_payload` fails, user sees "Setup couldn't complete. Try again?"
- Re-running is safe (upsert for preferences, inventory inserts are idempotent if we add conflict handling)

### 10.3 Empty or Invalid Inputs

**Validation rules:**

| Input | Validation | Default/Fallback |
|-------|------------|------------------|
| `household_size` | Required, 1-12 | 2 |
| `allergies` | Optional, validate against known list | [] |
| `dietary_restrictions` | Optional, validate against enum | [] |
| `skill_level` | Required, must be in enum | "intermediate" |
| `pantry_items` | Optional, can be empty | [] |
| `ingredient_discovery` | Min 1 selection per round to continue | Skip discovery if 0 |
| `cuisine_selections` | Optional, max 5 | [] |
| `style_selections` | Required for each, provide defaults | "standard" for all |
| `habits_response` | Optional, min 20 chars if provided | Skip → use skill defaults |

```python
# onboarding/forms.py

def validate_constraints(form: ConstraintsForm) -> tuple[bool, list[str]]:
    """Validate constraints form with specific error messages."""
    errors = []
    
    if not 1 <= form.household_size <= 12:
        errors.append("Household size must be between 1 and 12")
    
    if form.cooking_skill_level not in ["beginner", "intermediate", "advanced"]:
        errors.append("Please select a skill level")
    
    # Allergies: warn on unknown but don't block
    unknown_allergens = set(form.allergies) - set(COMMON_ALLERGENS)
    if unknown_allergens:
        # Log for review, but accept (user might have niche allergy)
        logger.info(f"Unknown allergens submitted: {unknown_allergens}")
    
    # Dietary restrictions: must be from enum
    invalid_restrictions = set(form.dietary_restrictions) - VALID_RESTRICTIONS
    if invalid_restrictions:
        errors.append(f"Unknown dietary restrictions: {invalid_restrictions}")
    
    return (len(errors) == 0, errors)
```

### 10.4 Missing Embeddings / Unknown Ingredients

**Problem:** User adds ingredient not in our database, or embedding lookup fails.

```python
# onboarding/similarity.py

def compute_preference_centroid_safe(
    selections: list[str],
    embeddings: dict[str, list[float]],
) -> list[float] | None:
    """
    Compute centroid, handling missing embeddings gracefully.
    
    Returns None if no valid embeddings found.
    """
    vectors = []
    for selection in selections:
        if selection in embeddings:
            vectors.append(embeddings[selection])
        else:
            # Log and skip
            logger.debug(f"No embedding for ingredient: {selection}")
    
    if not vectors:
        return None  # Caller should fall back to diverse random selection
    
    import numpy as np
    return np.mean(vectors, axis=0).tolist()

async def get_next_discovery_options(
    state: IngredientDiscoveryState,
    constraints: dict,
    embeddings: dict,
) -> list[dict]:
    """
    Get next round options with fallback for edge cases.
    """
    excluded = get_excluded_ingredients(
        constraints.get("dietary_restrictions", []),
        constraints.get("allergies", []),
    )
    
    if not state.rounds:
        # Round 1: Diverse seed
        return await get_diverse_seed_options(excluded)
    
    # Compute preference from selections
    all_selections = []
    for round_data in state.rounds:
        all_selections.extend(round_data.get("selections", []))
    
    centroid = compute_preference_centroid_safe(all_selections, embeddings)
    
    if centroid is None:
        # Fallback: No valid embeddings, just show diverse options
        logger.warning("No valid embeddings for selections, falling back to diverse")
        return await get_diverse_seed_options(excluded)
    
    # Normal flow: similar + diverse mix
    similar = await get_similar_options(centroid, excluded, count=3)
    diverse = await get_diverse_options(centroid, excluded, count=3)
    
    # If we can't find enough options, pad with random
    if len(similar) + len(diverse) < 6:
        padding = await get_random_options(
            excluded, 
            count=6 - len(similar) - len(diverse)
        )
        return similar + diverse + padding
    
    return similar + diverse
```

---

## 11. Open Questions & Decisions

### 11.1 Ingredient Preferences Storage

**Current approach:** Store in payload, decide storage later.

**Options for Alfred integration:**
1. **New table** (`user_ingredient_preferences`) — Most queryable, requires migration
2. **Encode in subdomain_guidance** — No schema change, less queryable
3. **Store as preferences column** — e.g., `favorite_ingredients TEXT[]`

**Recommendation:** Start with option 2 for MVP. The guidance string can include "Preferred proteins: salmon, shrimp, tofu..." which the LLM can interpret. Add structured storage when we have a clear query use case.

### 11.2 Embedding Infrastructure

For graph-based discovery to work well, we need:
- Embeddings for ingredients (could use category + name)

**MVP approach:** Use category-based similarity (proteins cluster together, etc.) rather than true embeddings. Upgrade to embeddings later.

```python
# MVP: Category-based similarity
CATEGORY_GROUPS = {
    "proteins": ["chicken", "beef", "pork", "fish", "salmon", "shrimp", "tofu", "tempeh"],
    "grains": ["rice", "pasta", "quinoa", "couscous", "bread"],
    "dairy": ["cheese", "milk", "yogurt", "butter", "cream"],
    "produce": ["tomatoes", "onions", "garlic", "peppers", "spinach", "kale"],
    "aromatics": ["garlic", "ginger", "scallions", "shallots", "lemongrass"],
}

def get_similar_by_category(ingredient: str, all_ingredients: list) -> list:
    """Simple category-based similarity for MVP."""
    # Find ingredient's category
    ingredient_category = None
    for category, members in CATEGORY_GROUPS.items():
        if ingredient.lower() in [m.lower() for m in members]:
            ingredient_category = category
            break
    
    if not ingredient_category:
        return []  # Unknown ingredient, no similarity
    
    # Return other items in same category
    return [
        ing for ing in all_ingredients
        if ing.lower() in [m.lower() for m in CATEGORY_GROUPS[ingredient_category]]
        and ing.lower() != ingredient.lower()
    ]
```

**Note:** Cuisine discovery is a simple multi-select (see 5.3), so no cuisine embeddings needed.

### 11.3 Session Persistence

Already addressed in Section 10.1 (Interrupted Sessions). Session table definition:

```sql
CREATE TABLE onboarding_sessions (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    state JSONB NOT NULL,
    current_phase TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 11.4 Subdomain Guidance Defaults

If user skips sections, we need sensible defaults based on skill level:

```python
# onboarding/defaults.py

DEFAULT_GUIDANCE_BY_SKILL = {
    "beginner": {
        "recipes": "Explain techniques briefly. Keep to 5-7 steps. Include timing cues. Metric measurements.",
        "meal_plans": "Simple meals preferred. Don't assume mise en place skills. One new recipe per week max.",
        "shopping": "Group by store section. Include quantities. Note common substitutions.",
        "inventory": "Track the basics. Assume common staples (oil, salt, basic spices) available.",
        "tasks": "Detailed reminders with time estimates. Explain why each task matters.",
    },
    "intermediate": {
        "recipes": "Skip obvious steps. Include chef tips where relevant. 6-8 steps typical.",
        "meal_plans": "Balance variety and efficiency. Batch-friendly suggestions appreciated.",
        "shopping": "Consolidate similar items. Note when items are interchangeable.",
        "inventory": "Track proteins and produce carefully. Loose on pantry staples.",
        "tasks": "Day-before reminders. Link prep to specific meals.",
    },
    "advanced": {
        "recipes": "Concise steps. Focus on technique nuances and timing. Multi-component dishes okay.",
        "meal_plans": "Complex dishes welcome. Assume good time management. Flexibility appreciated.",
        "shopping": "By category. Note quality preferences. Bulk options where sensible.",
        "inventory": "Assume well-stocked. Flag specialty items only.",
        "tasks": "Brief reminders. Link to meals. I know what needs prep.",
    },
}

def apply_skill_defaults(
    subdomain_guidance: dict,
    skill_level: str,
) -> dict:
    """Fill missing subdomain guidance with skill-appropriate defaults."""
    defaults = DEFAULT_GUIDANCE_BY_SKILL.get(skill_level, DEFAULT_GUIDANCE_BY_SKILL["intermediate"])
    
    for subdomain, default_text in defaults.items():
        if subdomain not in subdomain_guidance or not subdomain_guidance[subdomain]:
            subdomain_guidance[subdomain] = default_text
    
    return subdomain_guidance
```

### 11.5 Post-Onboarding Updates

**Question:** What if user wants to change preferences after onboarding?

**Answer:** Onboarding writes to standard `preferences` table. User can update via:
1. Settings UI (future feature)
2. Conversational updates with Alfred ("I'm going vegetarian now")
3. Re-running onboarding (if we add that option)

**Design principle:** Don't treat onboarded data as special. It's just initial values in the preferences table.

### 11.6 Logging & Analytics

```python
# onboarding/analytics.py

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

def log_onboarding_event(
    user_id: str,
    event_type: str,
    phase: str,
    data: dict = None,
) -> None:
    """
    Log onboarding analytics event.
    
    MVP: Logger only.
    Future: Write to analytics table or external service.
    """
    logger.info(f"Onboarding event: {event_type} | user={user_id} | phase={phase} | data={data}")

# Key events to track:
# - "phase_started" / "phase_completed" (funnel analysis)
# - "discovery_selection" (taste profile patterns)
# - "style_selected" (which templates are popular)
# - "preview_feedback" (recipe quality signal)
# - "abandonment" (where do users drop off)
```

---

## 12. Implementation Phases

### Phase A: Scaffolding (1-2 days)
- [ ] Create `src/onboarding/` directory structure
- [ ] Set up API router (separate from Alfred)
- [ ] Define `OnboardingState`, `OnboardingPayload`, `PreferenceInteraction` dataclasses
- [ ] Create `onboarding_sessions` + `onboarding_data` table migrations
- [ ] Implement `constants.py` and `filters.py`

### Phase B: Deterministic Forms (2-3 days)
- [ ] Implement `ConstraintsForm` validation
- [ ] Create constraint endpoints (`/submit/constraints`)
- [ ] Basic frontend form components
- [ ] Constraint filtering logic for later phases

### Phase C: Pantry Seeding (2-3 days)
- [ ] Ingredient search integration (reuse Alfred's)
- [ ] Common staples list (filtered by constraints)
- [ ] Pantry submission endpoint (`/submit/pantry`)
- [ ] Frontend pantry UI with multi-select search

### Phase D: Ingredient Discovery (3-4 days)
- [ ] `IngredientDiscoveryState` management
- [ ] Category-based similarity (MVP, no embeddings)
- [ ] Round generation algorithm with constraint filtering
- [ ] Discovery endpoints (`/discovery/round`, `/discovery/submit`)
- [ ] Frontend discovery cards UI

### Phase E: Cuisine Selection (1 day)
- [ ] Simple multi-select UI with chips
- [ ] Validation (max 5 selections)
- [ ] Submit endpoint (`/submit/cuisines`)

### Phase F: Style Discovery — LLM Generation + Feedback (4-5 days)
- [ ] `RecipeStyleProposal`, `MealPlanStyleProposal` models
- [ ] Prompts for pantry-aware sample generation
- [ ] `StyleFeedbackSynthesis` model and synthesis prompt
- [ ] Endpoints: `/style/propose/{domain}`, `/style/feedback/{domain}`
- [ ] Frontend: Sample display cards, feedback input, acknowledgment
- [ ] Store `PreferenceInteraction` records in state
- [ ] Apply synthesis → `subdomain_guidance` + `stylistic_examples`

### Phase G: Habits Extraction (2 days)
- [ ] `HABITS_PROMPT` and `HabitsExtraction` model
- [ ] LLM call for free-form habits
- [ ] Apply to `subdomain_guidance["meal_plans"]`, `["shopping"]`, `["inventory"]`
- [ ] Frontend open-ended text input with prompts

### Phase H: Final Preview (2 days)
- [ ] Sample recipe generation (pantry-aware, style-aware)
- [ ] Feedback logging for future analysis
- [ ] Preview endpoints (`/preview/recipes`)
- [ ] Frontend preview cards with feedback buttons

### Phase I: Integration (2-3 days)
- [ ] `apply_onboarding_payload` with error handling
- [ ] Store full payload to `onboarding_data` table
- [ ] `apply_skill_defaults` for missing guidance
- [ ] Update Alfred prompt injection to use `stylistic_examples`
- [ ] End-to-end flow testing
- [ ] Redirect to Alfred post-completion

---

## 13. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Completion rate | >70% | Users who finish all phases |
| Time to complete | <10 min | Median duration |
| Pantry items seeded | >5 | Average items added |
| Discovery engagement | >3 rounds | Rounds completed before skip |
| Recipe preview approval | >2/3 | Positive feedback on samples |
| First-day retention | >50% | Users who return within 24h |

---

## 14. Revision History

### v1.1 (2026-01-18) - Simplification Update

Based on complexity review:

**Cuisine Discovery → Simple Multi-Select**
- Finite list, no graph needed
- Reduced code paths and state complexity

**Style Selection → Direct Template Assignment**  
- No LLM calls for visual choices
- Predefined templates assigned directly
- LLM only for free-form habits (1 call)

**Feedback Loop → Logging Only (MVP)**
- Removed real-time preference adjustment
- Feedback logged for future analysis
- Avoids complex regeneration loops

**State Management Clarified**
- Separate state objects per discovery type
- Clear phase transitions with completion markers
- Explicit payload draft building at each step

**Edge Cases Documented**
- Interrupted sessions (Section 10.1)
- API errors and transactions (Section 10.2)
- Empty/invalid inputs (Section 10.3)
- Missing embeddings fallback (Section 10.4)

**Constraint Filtering Added**
- Phase 1 constraints filter all subsequent options
- Allergens and dietary restrictions respected throughout

**Domain Clarity**
- Shopping habits get dedicated `subdomain_guidance["shopping"]` key
- Avoids blurring domain lines with meal_plans

**Logging & Analytics**
- Added `log_onboarding_event()` hook for funnel analysis
- Track key events: phase completion, selections, feedback

### v1.2 (2026-01-18) - Conversational Style Discovery

Based on architecture discussion:

**Template Selection → LLM Generation + Feedback Loop**
- Users don't know what kind of meal planner they are
- LLM proposes 2-3 samples with justification
- User picks or gives feedback
- LLM synthesizes into guidance + stylistic example
- ~8 LLM calls per onboarding (acceptable for durable value)

**Pantry-Aware Sample Generation**
- Recipe/meal plan samples use pantry items from Phase 2
- Creates immediate value demonstration ("using your shrimp...")
- Validates onboarding effort, builds trust

**Preference Interactions Storage**
- Added `PreferenceInteraction` model
- Stores: samples shown, user feedback, LLM synthesis
- `stylistic_examples` → wired to Alfred for tone guidance
- Full interaction history → stored but not wired (future use)

**Alfred Integration Enhanced**
- Move tonal guidance from hardcoded prompts → `subdomain_guidance`
- `stylistic_examples[domain]` acts as few-shot tone guide
- Each subdomain can reference user's preferred output format

**Payload Structure Updated**
- Added `stylistic_examples` (wired to Alfred)
- Added `preference_interactions` (stored, not wired)
- Clear separation: what's wired vs what's archived

**Micro-Onboarding Pattern** (noted, not implemented)
- Future features use 2-3 turn flows to fill new guidance keys
- Avoids schema risk and full re-onboarding

---

*This spec is designed to be built incrementally. Each phase produces value independently. The output payload is the single integration contract with Alfred.*
