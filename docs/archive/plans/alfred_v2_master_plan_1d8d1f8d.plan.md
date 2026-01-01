---
name: Alfred V2 Master Plan
overview: "Consolidated master plan for Alfred V2. Phases 1-5 complete. Phase 6 adds complexity routing. Phase 7 expands data model (7a: LLM-facing schema, 7b: async enrichment). Phase 8 seeds data. Phase 9 polishes CLI, observability, and tests."
todos:
  - id: p6-complexity-rules
    content: Add complexity_rules to SUBDOMAIN_REGISTRY
    status: completed
  - id: p6-adjust-complexity
    content: Add adjust_step_complexity() in think.py
    status: completed
    dependencies:
      - p6-complexity-rules
  - id: p6-model-activation
    content: Enable model routing based on complexity
    status: completed
    dependencies:
      - p6-adjust-complexity
  - id: p7a-migration
    content: Create migration 009 for preferences, prep, variations, tasks
    status: completed
  - id: p7a-schema-update
    content: Update FALLBACK_SCHEMAS with new columns/tables
    status: completed
    dependencies:
      - p7a-migration
  - id: p7a-prompts
    content: Add prep, variation, task examples to think.md and act.md
    status: completed
  - id: p7a-validation
    content: Run validation tests for Phase 7a
    status: completed
    dependencies:
      - p7a-schema-update
      - p7a-prompts
  - id: p7b-migration
    content: Create migration 010 for cooking_log and flavor trigger
    status: completed
    dependencies:
      - p7a-validation
  - id: p7b-subdomain
    content: Add history subdomain and expose flavor_preferences
    status: completed
    dependencies:
      - p7b-migration
  - id: p7b-profile-builder
    content: Build async profile artifact generator
    status: completed
    dependencies:
      - p7b-subdomain
  - id: p7b-injection
    content: Inject compact profile into prompts
    status: completed
    dependencies:
      - p7b-profile-builder
  - id: p8-ingredients
    content: Create ingredient seeding script from Open Food Facts
    status: completed
  - id: p8-embeddings
    content: Generate embeddings for ingredients and recipes
    status: completed
    dependencies:
      - p8-ingredients
  - id: p9-observability
    content: Add LangSmith integration
    status: completed
  - id: p9-tests
    content: Add unit and integration tests
    status: completed
---

# Alfred V2 - Consolidated Master Plan

**Last Updated:** December 25, 2024---

## Plan Structure

| Phase | Focus | Status |

|-------|-------|--------|

| 1-5 | Foundation → Multi-Turn Conversation | ✅ Complete |

| 6 | Complexity Routing | ✅ Complete |

| 7a | Data Model: LLM-Facing Schema | ✅ Complete |

| 7b | Data Model: Async Enrichment | ✅ Complete |

| 8 | Data Seeding | ✅ Complete (scripts created) |

| 9 | Polish (CLI, Observability, Tests) | ✅ Complete |---

## Post-Phase Fixes (Dec 25, 2024)

Additional bug fixes and refinements discovered during testing:| Fix | Description | Files |

|-----|-------------|-------|

| `user_id` on `recipe_ingredients` | Denormalized for simpler CRUD deletes | migration 013, crud.py, schema.py |

| Step result preservation | CRUD steps keep actual tool results, not LLM summaries | act.py |

| Step result formatting | Recent steps (last 3) get full JSON, not truncated | act.py |

| Reply shows generated content | Don't summarize recipes/plans, show them | reply.md |

| Delete guidance | Single vs. all delete patterns, FK-safe order | schema.py, think.md |

| Smart shopping merges | Guidance to check existing list before adding | schema.py |

| `tasks` subdomain separation | Tasks are freeform, meal_type `prep` → `other` | schema.py, migration 011, 012 |

| Model routing | Medium = gpt-4.1 (not gpt-5-mini due to latency) | model_router.py |

| Date injection | Act/Think get current date to avoid hallucination | act.py, think.py |

| Content archive | Generated content archived for cross-turn retrieval | act.py, state.py |---

## Remaining / Future Work

| Item | Priority | Notes |

|------|----------|-------|

| Ingredient name normalization (UX-010) | Medium | "hard-boiled eggs" → "eggs" for shopping |

| Smart shopping list merging (UX-015) | Medium | Guidance added, needs testing |

| Entity tracking edge cases | Low | Audit for multi-entity scenarios |

| Seed scripts execution | Low | Scripts created but not run on prod |

| Embedding generation | Low | Scripts created but not populated |---

## Phases 1-5: Complete

Detailed session logs preserved in original plan file. Summary:| Phase | What Was Built |

|-------|----------------|

| 1 | Repo, Supabase, Railway deployment |

| 2 | Pydantic models, LLM client, model router |

| 3 | LangGraph (Router→Think→Act→Reply), CRUD tools, schema system |

| 4 | Prompt refinement, batch operations, step types |

| 5 | Multi-turn conversation, summarization, entity tracking |---

## Phase 6: Complexity Routing

**Goal:** Auto-escalate to stronger models for complex operations.

### 6.1 Subdomain Complexity Rules

Add `complexity_rules` to `SUBDOMAIN_REGISTRY`:

```python
SUBDOMAIN_REGISTRY = {
    "recipes": {
        "tables": ["recipes", "recipe_ingredients", "ingredients"],
        "complexity_rules": {"mutation": "high"},  # linked tables
    },
    "meal_plan": {
        "tables": ["meal_plans", "tasks", "recipes"],
        "complexity_rules": {"mutation": "medium"},
    },
    # inventory, shopping, preferences: no rules (LLM decides)
}
```



### 6.2 Think Post-Processing

Add `adjust_step_complexity()` in [`src/alfred/graph/nodes/think.py`](src/alfred/graph/nodes/think.py):

```python
def adjust_step_complexity(step: PlannedStep) -> PlannedStep:
    rules = SUBDOMAIN_REGISTRY.get(step.subdomain, {}).get("complexity_rules")
    if not rules:
        return step
    is_mutation = any(v in step.description.lower() 
                      for v in ["create", "save", "add", "update", "delete"])
    if is_mutation and rules.get("mutation"):
        step.complexity = rules["mutation"]
    return step
```



### 6.3 Model Activation

Enable routing in [`src/alfred/llm/model_router.py`](src/alfred/llm/model_router.py):| Complexity | Model |

|------------|-------|

| low | gpt-4.1-mini |

| medium | gpt-4.1 |

| high | gpt-5.1 |---

## Phase 7a: Data Model - LLM-Facing Schema

**Goal:** Expand schema for preferences, prep, variations, tasks. Test LLM interactions.

### 7a.1 Migration

**File:** `migrations/009_phase_7a_schema.sql`

```sql
-- Expanded preferences
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS
    nutrition_goals TEXT[] DEFAULT '{}',
    cooking_frequency TEXT,
    available_equipment TEXT[] DEFAULT '{}',
    time_budget_minutes INT DEFAULT 30,
    preferred_complexity TEXT DEFAULT 'moderate';

-- meal_type expanded (prep → other)
ALTER TABLE meal_plans DROP CONSTRAINT IF EXISTS meal_plans_meal_type_check;
ALTER TABLE meal_plans ADD CONSTRAINT meal_plans_meal_type_check 
    CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'other'));

-- Recipe variations
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS 
    parent_recipe_id UUID REFERENCES recipes(id);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_date DATE,
    category TEXT CHECK (category IN ('prep', 'shopping', 'cleanup', 'other')),
    completed BOOLEAN DEFAULT false,
    recipe_id UUID REFERENCES recipes(id),
    meal_plan_id UUID REFERENCES meal_plans(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```



### 7a.2 Schema Registry Update

Update [`src/alfred/tools/schema.py`](src/alfred/tools/schema.py):

- `tasks` as separate subdomain (not under meal_plan)
- Update FALLBACK_SCHEMAS with new columns

### 7a.3 Prompt Updates

- [`prompts/think.md`](prompts/think.md): Add prep, variation, task examples
- [`prompts/act.md`](prompts/act.md): Add task CRUD, prep meal_type docs

### 7a.4 Validation Gate

Must pass before Phase 7b:| Test Scenario | Validates |

|---------------|-----------|

| "Add prep work for Sunday" | Prep meal_type |

| "Make a spicy version of butter chicken" | parent_recipe_id |

| "I have an Instant Pot and air fryer" | Expanded preferences |

| "Remind me to thaw chicken tomorrow" | Tasks table |

| Create recipe with 8 ingredients | Complexity auto-escalation |---

## Phase 7b: Data Model - Async Enrichment

**Goal:** Add event logging and derived data. LLM consumes summaries, not raw data.

### 7b.1 Cooking Log

**File:** `migrations/010_phase_7b_enrichment.sql`

```sql
CREATE TABLE cooking_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    recipe_id UUID REFERENCES recipes(id),
    cooked_at TIMESTAMPTZ DEFAULT NOW(),
    servings INT,
    rating INT CHECK (rating >= 1 AND rating <= 5),
    notes TEXT,
    from_meal_plan_id UUID REFERENCES meal_plans(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```



### 7b.2 Flavor Preferences Trigger

```sql
CREATE OR REPLACE FUNCTION update_flavor_preferences()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO flavor_preferences (user_id, ingredient_id, times_used, last_used_at)
    SELECT NEW.user_id, ri.ingredient_id, 1, NOW()
    FROM recipe_ingredients ri WHERE ri.recipe_id = NEW.recipe_id
    ON CONFLICT (user_id, ingredient_id) 
    DO UPDATE SET 
        times_used = flavor_preferences.times_used + 1,
        last_used_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_flavor_prefs
AFTER INSERT ON cooking_log
FOR EACH ROW EXECUTE FUNCTION update_flavor_preferences();
```



### 7b.3 Subdomain Update

```python
SUBDOMAIN_REGISTRY["history"] = {"tables": ["cooking_log"]}
SUBDOMAIN_REGISTRY["preferences"]["tables"].append("flavor_preferences")
```



### 7b.4 Profile Builder (Async)

**File:** `src/alfred/background/profile_builder.py`Pre-computes:| Artifact | Source | Trigger |

|----------|--------|---------|

| Profile summary | preferences | On change |

| Top recipes | cooking_log | On insert |

| Top ingredients | flavor_preferences | On trigger |

| Recent activity | cooking_log + meal_plans | Daily |

### 7b.5 Prompt Injection

Inject compact profile at top of Generate/Analyze prompts:

```markdown
## USER PROFILE
- Household: 2 | Diet: vegetarian | Allergies: peanuts
- Equipment: instant-pot, air-fryer | Time: 30 min
- Top cuisines: italian, indian
- Recent: butter chicken (★★★★★), pasta primavera
```

---

## Phase 8: Data Seeding

**Goal:** Seed ingredient catalog and optionally recipes from public APIs.

### 8.1 Ingredient Seeding

**Source:** Open Food Facts API

**File:** `scripts/seed_ingredients.py`

- Seed ~2000 common ingredients
- Include categories (produce, dairy, protein, etc.)
- Generate aliases ("bell pepper" → ["capsicum", "sweet pepper"])

### 8.2 Recipe Seeding (Optional)

**Source:** Spoonacular or Tasty APIConsider whether needed — users generate recipes via LLM anyway.

### 8.3 Embedding Generation

Generate embeddings for:

- Ingredient names + aliases
- Recipe names + tags

Store in Supabase pgvector for semantic search.---

## Phase 9: Polish

### 9.1 CLI Improvements

- Interactive mode with rich formatting
- `alfred serve` (done)
- `alfred seed` for seeding scripts
- `alfred chat` for terminal conversations

### 9.2 Observability

- LangSmith integration for tracing
- Cost tracking per request
- Latency metrics per node

### 9.3 Stub Agents

- Coach agent skeleton (fitness)
- Cellar agent skeleton (wine)
- Router dispatch logic for multiple agents

### 9.4 Tests

- Unit tests for CRUD tools
- Integration tests for Think→Act flows
- Prompt regression tests

---

## Files Summary

| Phase | Create | Modify |

|-------|--------|--------|

| 6 | — | schema.py, think.py, model_router.py |

| 7a | migrations/009 | schema.py, think.md, act.md |

| 7b | migrations/010, profile_builder.py | schema.py, act.py |

| 8 | seed_ingredients.py | — |

| 9 | — | main.py, various |---

## Archived

The following intermediate plan files can be deleted:

- `alfred_phase_6-9_consolidation_a0d7d975.plan.md`
- `alfred_phase_a-b_split_1e92172f.plan.md`