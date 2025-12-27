# Alfred V2 - Data Model Decisions

**Document Type:** Decision Brief  
**Last Updated:** December 25, 2024  
**Status:** Decisions Made (see Architectural Rationale)

---

## Executive Summary

Alfred's core LLM pipeline is functional. The next phase requires data model expansion to support richer personalization. This document outlines 7 decision areas with final recommendations informed by architectural review.

---

## Foundational Principle

> **LLM step types (CRUD / Analyze / Generate) describe cognition, not data derivation.**
> 
> Deterministic computation, aggregation, and summarization should not be forced into the online graph if they can be maintained asynchronously and injected as state.

This principle informs all decisions below.

---

## Table Classification

Not all tables should be treated equally at runtime:

| Class | Examples | Runtime Behavior |
|-------|----------|------------------|
| **Primary Objects** | inventory, recipes, meal_plans, shopping_list, tasks | Directly queryable by Act |
| **Event Logs** | cooking_log | Queryable, but summarized before injection |
| **State Artifacts** | user profile snapshots, aggregated food signals | Injected, never discovered via query |

This distinction allows the system to scale without runtime complexity.

---

## Decision 1: Prep Notes & Weekly Planning

### The Problem

Users want to plan prep work: "Marinate chicken on Sunday, use it Monday-Wednesday"

Currently, `meal_plans` only tracks: date + meal_type + recipe_id. No way to capture prep tasks.

### Core Intent

**Prep is not a new domain; it is a temporal annotation on planning.**

### Decision: Option C (prep as meal_type)

Prep is tightly coupled to *when* food is prepared, not to an abstract task system. Keeping prep within `meal_plans` preserves the mental model of "what happens on a given day."

Introducing a new prep table prematurely would fragment planning logic and increase LLM routing complexity.

**Architectural note:** Prep entries are annotated planning objects, not workflow primitives. Richer prep detail should live in annotations (e.g., `notes` column), not new tables.

### Migration

```sql
-- meal_type becomes: 'breakfast' | 'lunch' | 'dinner' | 'snack' | 'prep'
-- No new table required
```

---

## Decision 2: Recipe Variations

### The Problem

Users create variations: "This is my spicy version of butter chicken"

Currently, recipes are independent. No way to link a "base" recipe to its variants.

### Core Intent

**Variations represent lineage, not categorization.**

### Decision: Option B (parent_recipe_id column)

Variations are not tags; they are derivations. A simple parent pointer supports:
- "Show me all versions of X"
- "Start from the base recipe"

This avoids premature normalization (junction tables) while preserving queryability.

**Separation of concerns:** Variation linkage is a primary object relationship and should remain directly queryable at runtime. No summarization layer required.

### Migration

```sql
ALTER TABLE recipes ADD COLUMN parent_recipe_id UUID REFERENCES recipes(id);
```

---

## Decision 3: Cooking History / Logs

### The Problem

No way to track what was cooked, when, or how it went. Users can't answer:
- "What did I cook last week?"
- "How often do I make this?"
- "What's my highest-rated recipe?"

### Core Intent

**Cooking history is event data, not conversational data.**

### Decision: Option C (rich cooking_log)

This table underpins:
- Most-cooked recipes
- Frequency signals
- Preference learning
- Retrospective questions

Without it, all personalization must be inferred heuristically in conversation, which does not compound over time.

### Critical Architectural Distinction

`cooking_log` is an **Event Log** table:
- **Queryable** for direct questions ("what did I cook last week?")
- **NOT injected raw** into Generate steps

Instead:
- Deterministic aggregates (top recipes, recent cooking) computed **asynchronously**
- Generate and Analyze steps consume **summaries**, not raw logs

This prevents prompt bloat and latency spikes.

### Schema

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

---

## Decision 4: Daily/Weekly Task Checklists

### The Problem

Users want transient task lists:
- "Thaw chicken today"
- "Chop veggies for tomorrow"
- "Buy wine for Friday dinner"

These are different from:
- `shopping_list` (purchasing)
- `meal_plans` (what to eat)

### Core Intent

**Tasks are transient execution aids, not core planning objects.**

### Decision: Option B (simple tasks table)

Tasks are orthogonal to meals and shopping but still related. A minimal task table avoids overloading:
- `shopping_list` (purchase intent)
- `meal_plans` (consumption intent)

### Important Constraint

Tasks should remain **operational, not analytical**:
- Queried directly when needed
- Should NOT meaningfully influence personalization models
- Should NOT expand into a full task system

This keeps the system focused on cooking, not productivity.

### Schema

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_date DATE,
    category TEXT,  -- 'prep', 'shopping', 'cleanup', 'other'
    completed BOOLEAN DEFAULT false,
    recipe_id UUID REFERENCES recipes(id),
    meal_plan_id UUID REFERENCES meal_plans(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Decision 5: Expanded User Preferences

### The Problem

Current `preferences` table is limited:
- ✅ Dietary restrictions, allergies, favorite cuisines, disliked ingredients
- ✅ Cooking skill level, household size
- ❌ Nutrition goals
- ❌ Cooking frequency
- ❌ Available equipment
- ❌ Time budget per meal
- ❌ Complexity preference

### Core Intent

**Preferences are stable user constraints, not conversational context.**

### Decision: Option A (expand existing table)

These attributes are:
- 1:1 with user
- Low cardinality
- Frequently needed

Keeping them in one table avoids unnecessary joins and runtime reads.

### Two Usage Modes

Preferences serve two distinct purposes:

| Mode | Examples | Injection |
|------|----------|-----------|
| **Direct constraints** | Diet, equipment, time budget | Injected into Generate via compact profile |
| **Learning inputs** | Frequency, complexity tolerance | Used by offline jobs, not reasoned about live |

### Migration

```sql
ALTER TABLE preferences ADD COLUMN 
    nutrition_goals TEXT[] DEFAULT '{}',        -- ["high-protein", "low-carb"]
    cooking_frequency TEXT,                     -- 'daily', '3-4x/week', 'weekends-only'
    available_equipment TEXT[] DEFAULT '{}',    -- ["instant-pot", "air-fryer", "grill"]
    time_budget_minutes INT DEFAULT 30,         -- typical time per meal
    preferred_complexity TEXT DEFAULT 'moderate'; -- 'quick-easy', 'moderate', 'elaborate'
```

---

## Decision 6: Flavor Preferences & Learning

### The Problem

We have a `flavor_preferences` table that tracks per-ingredient preference scores, but:
1. It's not exposed to the LLM (not in SUBDOMAIN_REGISTRY)
2. It's never updated (no trigger or logging)
3. It's not used for recommendations

### Core Intent

**Flavor preference learning should be data-driven first, LLM-assisted second.**

### Decision: Option D (hybrid)

- Deterministic signals (usage counts, recency) updated **automatically** from `cooking_log`
- LLM **reads** preference state, not responsible for maintaining it
- Optional LLM involvement belongs in **asynchronous summarization**, not live writes

### Key Separation of Concerns

| Layer | Responsibility |
|-------|----------------|
| `flavor_preferences` table | System of record (counts, timestamps) |
| Async jobs | Higher-level interpretations ("you seem to like garlic") |
| LLM (runtime) | Reads summaries, does not compute or update |

### Migration

```sql
-- Add to subdomain registry
"preferences": ["preferences", "flavor_preferences"],

-- Trigger to auto-update from cooking_log
CREATE FUNCTION update_flavor_preferences()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO flavor_preferences (user_id, ingredient_id, times_used, last_used_at)
    SELECT NEW.user_id, ri.ingredient_id, 1, NOW()
    FROM recipe_ingredients ri
    WHERE ri.recipe_id = NEW.recipe_id
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

---

## Decision 7: Context Injection Strategy

### The Problem

As we add more data (preferences, cooking history, flavor data), we need a clear strategy for:
1. **What** to inject into each prompt
2. **When** to inject it
3. **How** to structure it so the LLM can parse effectively

### Core Intent

**Runtime LLM performance depends on pre-digested context, not exhaustive querying.**

### Decision: Always inject compact profile, but compute it asynchronously

A user profile summary should always be present. However, **that summary should not be composed at runtime**.

### Injection-Ready State Artifacts

Maintain pre-computed artifacts, updated asynchronously:

| Artifact | Contents | Update Trigger |
|----------|----------|----------------|
| **Profile summary** | Constraints, household, time budget | On preference change |
| **Food signals** | Top recipes, top ingredients, avoid list | On cooking_log insert |
| **Recent activity** | Last 3 cooked meals, current week's plan | Daily job or on-demand |

Generate steps consume these artifacts directly. Analyze steps are used only when reconciliation or judgment is required.

### Prompt Structure

```
═══════════════════════════════════════════════════════════
TASK BLOCK (first ~100 lines) ← LLM focuses here
═══════════════════════════════════════════════════════════
## STATUS
[step, goal, progress]

## USER PROFILE (pre-computed, always present)
- Household: 2 adults
- Diet: vegetarian | Allergies: peanuts
- Skill: intermediate | Time: 30 min/meal
- Equipment: instant-pot, air-fryer
- Top cuisines: italian, indian
- Top ingredients: garlic, tomatoes, chicken

## YOUR JOB
[1-2 sentences: exactly what to do]

═══════════════════════════════════════════════════════════
REFERENCE DATA (clearly demarcated)
═══════════════════════════════════════════════════════════
<reference_data>
### Tool Results
[JSON in collapsible blocks]

### Schema
[tables]

### Previous Steps
[summaries]
</reference_data>

═══════════════════════════════════════════════════════════
DECISION BLOCK (last ~50 lines) ← LLM focuses here
═══════════════════════════════════════════════════════════
## WHAT TO DO NEXT
[decision guidance, format examples]
```

This avoids pushing aggregation logic into the online graph while ensuring constraints are never violated.

---

## Summary: Decision Matrix

| # | Decision | Final Choice | Effort | Table Class |
|---|----------|--------------|--------|-------------|
| 1 | Prep notes | Extend meal_type to 'prep' | Low | Primary Object |
| 2 | Recipe variations | Add parent_recipe_id column | Low | Primary Object |
| 3 | Cooking history | Rich cooking_log table | Medium | Event Log |
| 4 | Task checklists | Simple tasks table | Medium | Primary Object |
| 5 | Expanded preferences | Add columns to preferences | Low | Primary Object |
| 6 | Flavor preferences | Hybrid: backend writes, LLM reads | Medium | State Artifact (derived) |
| 7 | Context injection | Pre-computed profile artifacts | Low | State Artifact |

---

## Implementation Phases

### Phase 7a: Foundation (Low Effort, High Impact)
1. Expand preferences table (Decision 5)
2. Add prep as meal_type (Decision 1)
3. Add parent_recipe_id to recipes (Decision 2)

### Phase 7b: Event Logging + Learning (Medium Effort, High Impact)
4. Create cooking_log table (Decision 3)
5. Create trigger for flavor_preferences (Decision 6)
6. Expose flavor_preferences to LLM (Decision 6)

### Phase 7c: Async Infrastructure (Medium Effort, Foundational)
7. Build profile snapshot job (Decision 7)
8. Build food signals aggregation (Decision 7)
9. Inject pre-computed artifacts into prompts (Decision 7)

### Phase 7d: Operational (Low Priority)
10. Create tasks table (Decision 4)

---

## Architectural Synthesis

### Data Principles

1. **Add tables where they represent durable truth** (history, preferences, workflow)

2. **Avoid forcing interpretation or aggregation into runtime LLM steps**

3. **Move deterministic derivation and summarization into asynchronous refinement**

### Step Type Boundaries

| Step Type | Schema | Signals | Responsibility |
|-----------|--------|---------|----------------|
| **CRUD** | Schema-specific | Signal-free | Execute operations on specific tables |
| **Analyze** | Schema-aware | Signal-processing | Compare, filter, reason over data |
| **Generate** | Schema-free | Signal-rich | Create content from pre-digested context |

4. **CRUD steps are schema-specific and signal-free** — they execute database operations, not interpret context

5. **Analyze steps handle ambiguity, not counting** — reserve for judgment calls, not aggregation

6. **Generate steps are schema-free and signal-rich** — they consume artifacts, not raw data

This approach preserves the integrity of the existing LangGraph architecture while enabling richer personalization, lower latency, and clearer separation of concerns.

