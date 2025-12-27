# Alfred V2 - Architecture Overview

**Document Type:** Architecture Documentation  
**Last Updated:** December 26, 2024  
**Status:** Functional MVP with Dynamic Prompt Architecture

---

## 1. Project Summary

Alfred is a **multi-agent conversational assistant** built on a LangGraph architecture with generic CRUD tools and Supabase as the persistence layer.

### Agent Architecture

The system is designed to support multiple specialized agents, with **Router** classifying user intent and dispatching to the appropriate agent:

| Agent | Domain | Status |
|-------|--------|--------|
| **Pantry** | Kitchen: inventory, recipes, meal planning, shopping, tasks | ✅ Active |
| **Coach** | Fitness: workouts, nutrition tracking, goals | 🔲 Stub only |
| **Cellar** | Wine: collection, pairings, tasting notes | 🔲 Stub only |

The current implementation focuses on the **Pantry agent** as the proof-of-concept, but the architecture is agent-agnostic.

### Design Philosophy

| Principle | Implementation |
|-----------|----------------|
| Trust the LLM | Few examples, clear instructions (vs. v1's 261 examples) |
| Generic tools | 4 CRUD primitives instead of 40+ domain-specific tools |
| Subdomain filtering | LLM sees only relevant tables per step |
| Schema auto-generation | From database, never stale |
| Natural conversation | LangGraph handles multi-turn natively |
| Persona over rules | Identity-based guidance vs. exhaustive warnings |

---

## 2. Multi-Agent Structure

### Graph Flow

```
┌────────┐   ┌───────┐   ┌──────────────────┐   ┌───────┐   ┌───────────┐
│ ROUTER │──▶│ THINK │──▶│     ACT LOOP     │──▶│ REPLY │──▶│ SUMMARIZE │
└────────┘   └───────┘   │                  │   └───────┘   └───────────┘
                         │ • Get schema     │
                         │ • Inject persona │
                         │ • Execute CRUD   │
                         │ • Pass step notes│
                         │ • Loop or exit   │
                         └──────────────────┘
```

### Node Responsibilities

| Node | Purpose | Model Selection |
|------|---------|-----------------|
| **Router** | Classify intent, pick agent, set complexity | gpt-4.1-mini |
| **Think** | Plan steps with subdomain hints | Varies by complexity |
| **Act** | Execute steps via CRUD tools (loops within step) | Varies by complexity |
| **Reply** | Synthesize user-facing response | gpt-4.1-mini |
| **Summarize** | Compress conversation, track entities | gpt-4.1-mini |

### Step Types

| Type | When Used | What Act Does |
|------|-----------|---------------|
| `crud` | Read, create, update, delete data | Executes db_read/create/update/delete |
| `analyze` | Compare or reason over data | No DB calls — thinks and returns analysis |
| `generate` | Create content (recipe, plan) | No DB calls — generates and returns |

---

## 3. Dynamic Prompt Architecture

Act prompts are dynamically constructed based on subdomain and step type.

### Persona Groups

| Persona | Subdomains | Focus |
|---------|------------|-------|
| **Chef** | recipes | Creative generation, organizational CRUD, linked tables |
| **Ops Manager** | inventory, shopping, preferences | Cataloging, normalization, deduplication |
| **Planner** | meal_plan, tasks | Scheduling, dependencies, coordination |

### Recipe CRUD vs Generate Split

Recipes are uniquely complex — the Chef persona adapts:

| Step Type | Mode | Focus |
|-----------|------|-------|
| **CRUD** | Organizational | Clean naming, useful tags, linked tables |
| **Generate** | Creative | Flavor balance, dietary restrictions, personalization |

### Step Notes

CRUD steps can pass context to subsequent steps via `note_for_next_step`:

```
Step 1 (recipes): Creates recipe → note: "Recipe ID abc123"
Step 2 (meal_plan): Sees note → Creates meal plan entry → note: "Meal plan xyz789"
Step 3 (tasks): Sees note → Creates linked task
```

This enables multi-step workflows without re-reading data.

### Contextual Examples

Instead of static examples, relevant patterns are injected based on:
- Step verb ("add", "delete", "create")
- Subdomain context
- Previous step's subdomain (cross-domain patterns)

See [`docs/act_prompt_architecture.md`](act_prompt_architecture.md) for full details.

---

## 4. Think → Act Data Flow

### What Think Outputs

```python
class PlannedStep(BaseModel):
    description: str      # "Read all saved recipes"
    step_type: str        # "crud" | "analyze" | "generate"
    subdomain: str        # "recipes" | "inventory" | etc.
    complexity: str       # "low" | "medium" | "high"
```

### Dynamic Schema Injection

Act receives **only the schema for the current step's subdomain**:

```
Step 1 (subdomain: recipes)     → Act sees: recipes, recipe_ingredients, ingredients
Step 2 (subdomain: inventory)   → Act sees: inventory, ingredients
Step 3 (subdomain: shopping)    → Act sees: shopping_list, ingredients
```

### Step Result Caching

Each step's result is cached in `state.step_results[step_index]`:

- **Last 2-3 steps:** Full data
- **Older steps:** Summarized (table, count, sample IDs)

---

## 5. Model Routing

### Complexity-Based Selection

| Complexity | Model | Use Case |
|------------|-------|----------|
| **low** | gpt-4.1-mini | Simple CRUD, reads |
| **medium** | gpt-4.1 | Cross-domain operations |
| **high** | gpt-5.1 | Complex recipe generation, reasoning |

### Automatic Escalation

Think post-processes steps to auto-escalate complexity based on subdomain rules:

```python
# recipes mutations → high (linked tables)
# meal_plan mutations → medium
# simple reads → low (LLM decides)
```

---

## 6. Generic CRUD Tools

| Tool | Purpose | Key Params |
|------|---------|------------|
| `db_read` | Fetch rows | table, filters, or_filters, columns, limit |
| `db_create` | Insert row(s) | table, data (dict or array for batch) |
| `db_update` | Modify matching rows | table, filters, data |
| `db_delete` | Remove matching rows | table, filters |

### Filter Operators

```
=, >, <, >=, <=, in, ilike, is_null, contains
```

### Subdomain Registry

```python
SUBDOMAIN_REGISTRY = {
    "inventory": ["inventory", "ingredients"],
    "recipes": ["recipes", "recipe_ingredients", "ingredients"],
    "shopping": ["shopping_list", "ingredients"],
    "meal_plan": ["meal_plans", "tasks", "recipes"],
    "tasks": ["tasks", "meal_plans", "recipes"],
    "preferences": ["preferences", "flavor_preferences"],
    "history": ["cooking_log"],
}
```

---

## 7. Database Schema

### Current Tables

| Table | Purpose | User-Scoped |
|-------|---------|-------------|
| `users` | Authentication/identity | N/A |
| `ingredients` | Master ingredient catalog (~2000 seeded) | No |
| `inventory` | User's pantry items | Yes |
| `recipes` | User's saved recipes (supports variations via `parent_recipe_id`) | Yes |
| `recipe_ingredients` | Recipe→ingredient linking | Yes |
| `meal_plans` | Planned meals by date (breakfast/lunch/dinner/snack/other) | Yes |
| `tasks` | Freeform to-dos, can link to meal_plan or recipe | Yes |
| `shopping_list` | Shopping list items | Yes |
| `preferences` | Dietary, allergies, equipment, time budget, skill | Yes |
| `flavor_preferences` | Per-ingredient preference scores (auto-updated) | Yes |
| `cooking_log` | What was cooked, ratings, notes | Yes |

### Preferences Fields

```sql
dietary_restrictions TEXT[]     -- ["vegetarian", "low-sodium"]
allergies TEXT[]               -- ["peanuts", "shellfish"]
favorite_cuisines TEXT[]       -- ["italian", "indian"]
disliked_ingredients TEXT[]    -- ["cilantro", "olives"]
cooking_skill_level TEXT       -- 'beginner' | 'intermediate' | 'advanced'
household_size INT             -- 2
available_equipment TEXT[]     -- ["instant-pot", "air-fryer"]
time_budget_minutes INT        -- 30
nutrition_goals TEXT[]         -- ["high-protein", "low-carb"]
```

### Automated Triggers

| Trigger | Action |
|---------|--------|
| `cooking_log` insert | Updates `flavor_preferences` for used ingredients |

---

## 8. Conversation Context Management

### State Structure

```python
class ConversationContext:
    engagement_summary: str      # "Helping with meal planning..."
    recent_turns: list[dict]     # Last 2-3 full exchanges
    history_summary: str         # Compressed older turns
    active_entities: dict        # EntityRef tracking for "that recipe"
```

### Entity Tracking

```python
class EntityRef:
    type: str      # "recipe", "ingredient", "meal_plan", "task"
    id: str        # UUID
    label: str     # "Butter Chicken" (human-readable)
    source: str    # "db_lookup", "user_input", "generated"
```

Enables resolution of "that recipe", "those ingredients", etc.

### Content Archive

Generated content (recipes, meal plans) is archived for cross-turn retrieval:

```python
# User: "create a pasta recipe"
# → Recipe generated, archived under "generated_recipes"

# User: "save that recipe" (next turn)
# → Act retrieves from archive without regenerating
```

---

## 9. User Profile Injection

Generate and Analyze steps receive a compact user profile:

```markdown
## USER PROFILE
- Household: 2 | Diet: vegetarian | Allergies: peanuts
- Equipment: instant-pot, air-fryer | Time: 30 min
- Skill: beginner
```

This enables personalized recipe generation without verbose preference reads.

---

## 10. What Works Well

| Capability | Status |
|------------|--------|
| Simple CRUD (add to pantry, check inventory) | ✅ Solid |
| Multi-item batch operations | ✅ Solid |
| Cross-domain queries (inventory → recipe → shopping) | ✅ Works |
| Recipe generation with personalization | ✅ Works |
| Recipe CRUD with ingredient linking | ✅ Works |
| Shopping list management | ✅ Works |
| Meal planning with recipe linking | ✅ Works |
| Task creation linked to meal plans | ✅ Works |
| Recipe variations (parent_recipe_id) | ✅ Works |
| Multi-turn conversation with context | ✅ Works |
| Entity tracking ("that recipe") | ✅ Works |
| Cross-turn content retrieval | ✅ Works |
| Dynamic persona injection | ✅ Works |
| Step notes for multi-step workflows | ✅ Works |

---

## 11. Deployment

| Component | Platform |
|-----------|----------|
| Backend | Railway |
| Database | Supabase (Postgres) |
| Vectors | Supabase pgvector (seeded, not yet used for search) |
| Auth | Supabase Auth (basic) |
| UI | FastAPI web server (dev/testing) |
| Observability | LangSmith integration |

---

## 12. File Structure

```
alfred-v2/
├── src/alfred/
│   ├── graph/
│   │   ├── state.py          # AlfredState, step notes, content archive
│   │   ├── workflow.py       # LangGraph definition
│   │   └── nodes/
│   │       ├── router.py
│   │       ├── think.py      # Complexity adjustment
│   │       ├── act.py        # Dynamic prompt construction
│   │       ├── reply.py
│   │       └── summarize.py
│   ├── tools/
│   │   ├── crud.py           # db_read, db_create, db_update, db_delete
│   │   └── schema.py         # Personas, scope config, contextual examples
│   ├── llm/
│   │   ├── client.py         # Instructor-wrapped OpenAI
│   │   ├── model_router.py   # Complexity → model mapping
│   │   └── prompt_logger.py  # Debug logging
│   ├── memory/
│   │   └── conversation.py   # Context formatting, entity extraction
│   ├── db/
│   │   └── client.py         # Supabase client
│   └── web/
│       └── app.py            # FastAPI dev UI
├── prompts/
│   ├── router.md
│   ├── think.md
│   ├── act.md                # Core mechanics only (slim)
│   └── reply.md
├── scripts/
│   └── seed_ingredients.py   # Open Food Facts seeding
├── migrations/
│   └── *.sql                 # 13 migrations
└── docs/
    ├── architecture_overview.md      # This document
    ├── act_prompt_architecture.md    # Dynamic prompt details
    └── ux_learnings.md               # UX observations
```
