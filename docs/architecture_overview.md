# Alfred V2 - Architecture Overview

**Document Type:** Retrospective Architecture Documentation  
**Last Updated:** December 25, 2024  
**Status:** Functional MVP, Prompt Engineering Still Evolving

---

## 1. Project Summary

Alfred is a **multi-agent conversational assistant** built on a LangGraph architecture with generic CRUD tools and Supabase as the persistence layer.

### Agent Architecture

The system is designed to support multiple specialized agents, with **Router** classifying user intent and dispatching to the appropriate agent:

| Agent | Domain | Status |
|-------|--------|--------|
| **Pantry** | Kitchen: inventory, recipes, meal planning, shopping | ✅ Active prototype |
| **Coach** | Fitness: workouts, nutrition tracking, goals | 🔲 Stub only |
| **Cellar** | Wine: collection, pairings, tasting notes | 🔲 Stub only |

The current implementation focuses on the **Pantry agent** as the proof-of-concept, but the architecture is agent-agnostic. Router can be extended to dispatch to other agents as they're built.

### Design Philosophy

| Principle | Implementation |
|-----------|----------------|
| Trust the LLM | Few examples, clear instructions (vs. v1's 261 examples) |
| Generic tools | 4 CRUD primitives instead of 40+ domain-specific tools |
| Subdomain filtering | LLM sees only relevant tables per step |
| Schema auto-generation | From database, never stale |
| Natural conversation | LangGraph handles multi-turn natively |

---

## 2. Multi-Agent Structure

### Graph Flow

```
┌────────┐   ┌───────┐   ┌──────────────────┐   ┌───────┐   ┌───────────┐
│ ROUTER │──▶│ THINK │──▶│     ACT LOOP     │──▶│ REPLY │──▶│ SUMMARIZE │
└────────┘   └───────┘   │                  │   └───────┘   └───────────┘
                         │ • Get schema     │
                         │ • Execute CRUD   │
                         │ • Cache results  │
                         │ • Loop or exit   │
                         └──────────────────┘
```

### Node Responsibilities

| Node | Purpose | Model | Temperature |
|------|---------|-------|-------------|
| **Router** | Classify intent, pick agent, set complexity | gpt-4.1-mini | 0.15 |
| **Think** | Plan steps with subdomain hints | gpt-4.1-mini | 0.35 |
| **Act** | Execute steps via CRUD tools (loops within step) | gpt-4.1-mini | 0.25 |
| **Reply** | Synthesize user-facing response | gpt-4.1-mini | 0.6 |
| **Summarize** | Compress conversation, track entities | gpt-4.1-mini | 0.3 |

### Step Types

| Type | When Used | What Act Does |
|------|-----------|---------------|
| `crud` | Read, create, update, delete data | Executes db_read/create/update/delete |
| `analyze` | Compare or reason over data | No DB calls — thinks and returns analysis |
| `generate` | Create content (recipe, plan) | No DB calls — generates and returns |

### Step Type Boundaries

Each step type has distinct responsibilities regarding schema and signals:

| Step Type | Schema | Signals | Responsibility |
|-----------|--------|---------|----------------|
| **CRUD** | Schema-specific | Signal-free | Execute operations on specific tables |
| **Analyze** | Schema-aware | Signal-processing | Compare, filter, reason over data |
| **Generate** | Schema-free | Signal-rich | Create content from pre-digested context |

This separation ensures:
- CRUD steps don't interpret context, just execute
- Analyze steps handle ambiguity, not aggregation
- Generate steps consume artifacts, not raw data

---

## 3. Think → Act Data Flow

### What Think Outputs

Think receives a natural language goal from Router and outputs a **sequence of planned steps**:

```python
class PlannedStep(BaseModel):
    description: str      # NL: "Read all saved recipes and their ingredients"
    step_type: str        # "crud" | "analyze" | "generate"
    subdomain: str        # "recipes" | "inventory" | "shopping" | etc.
    complexity: str       # "low" | "medium" | "high"

class ThinkOutput(BaseModel):
    goal: str             # "Find recipe ingredients missing from pantry"
    steps: list[PlannedStep]
```

**Example Think output:**
```json
{
  "goal": "Add missing recipe ingredients to shopping list",
  "steps": [
    {"description": "Read recipe ingredients", "step_type": "crud", "subdomain": "recipes", "complexity": "low"},
    {"description": "Read current inventory", "step_type": "crud", "subdomain": "inventory", "complexity": "low"},
    {"description": "Compare to find missing ingredients", "step_type": "analyze", "subdomain": "shopping", "complexity": "medium"},
    {"description": "Add missing items to shopping list", "step_type": "crud", "subdomain": "shopping", "complexity": "low"}
  ]
}
```

### Dynamic Schema Injection

Act receives **only the schema for the current step's subdomain**. This is a key design choice:

1. **Think decides the subdomain** per step (e.g., `subdomain: "recipes"`)
2. **Act receives filtered schema** for only those tables
3. **Act cannot see other tables** unless it explicitly requests them

```
Step 1 (subdomain: recipes)     → Act sees: recipes, recipe_ingredients, ingredients
Step 2 (subdomain: inventory)   → Act sees: inventory, ingredients
Step 3 (subdomain: shopping)    → Act sees: shopping_list, ingredients
```

This prevents Act from getting confused by irrelevant tables and reduces token usage.

### Step Result Caching

Each step's result is cached in `state.step_results[step_index]`:

```python
step_results = {
    0: {"recipes": [...], "ingredients": [...]},  # Step 1 result
    1: {"inventory": [...]},                       # Step 2 result
    2: {"missing_ingredients": [...]},             # Step 3 (analyze) result
}
```

Later steps can reference earlier results. Act sees:
- **Last 2-3 steps:** Full data
- **Older steps:** Summarized (table, count, sample IDs)

### Multi-Tool Calls Within a Step

Act can make **multiple tool calls** within a single step before marking it complete:

```
Step: "Save recipe with ingredients"
  → db_create(table="recipes", data={...})  → returns recipe with ID
  → db_create(table="recipe_ingredients", data=[...with recipe_id...])
  → step_complete
```

This handles parent-child patterns (recipe → recipe_ingredients) in one logical step.

---

## 4. Generic CRUD Tools

### Generic CRUD Tools (4 total)

| Tool | Purpose | Key Params |
|------|---------|------------|
| `db_read` | Fetch rows | table, filters, or_filters, columns, limit |
| `db_create` | Insert row(s) | table, data (dict or array) |
| `db_update` | Modify matching rows | table, filters, data (dict only) |
| `db_delete` | Remove matching rows | table, filters |

### Filter Operators

```
=, >, <, >=, <=, in, ilike, is_null, contains
```

### Subdomain Registry

The LLM only sees tables relevant to the current step:

```python
SUBDOMAIN_REGISTRY = {
    "inventory": ["inventory", "ingredients"],
    "recipes": ["recipes", "recipe_ingredients", "ingredients"],
    "shopping": ["shopping_list", "ingredients"],
    "meal_plan": ["meal_plans", "recipes"],
    "preferences": ["preferences"],
}
```

---

## 5. Database Schema

### Current Tables (10)

| Table | Purpose | User-Scoped |
|-------|---------|-------------|
| `users` | Authentication/identity | N/A |
| `ingredients` | Master ingredient catalog | No |
| `inventory` | User's pantry items | Yes |
| `recipes` | User's saved recipes | Yes |
| `recipe_ingredients` | Recipe→ingredient linking | Via recipe |
| `meal_plans` | Planned meals by date | Yes |
| `shopping_list` | Shopping list items | Yes |
| `preferences` | Dietary, allergies, skill, household | Yes |
| `flavor_preferences` | Per-ingredient preference scores | Yes (unused) |
| `conversation_memory` | LLM memory storage | Yes (backend) |

### Preferences Table Fields

```sql
dietary_restrictions TEXT[]    -- ["vegetarian", "low-sodium"]
allergies TEXT[]              -- ["peanuts", "shellfish"]
favorite_cuisines TEXT[]      -- ["italian", "indian"]
disliked_ingredients TEXT[]   -- ["cilantro", "olives"]
cooking_skill_level TEXT      -- 'beginner' | 'intermediate' | 'advanced'
household_size INT            -- 2
```

---

## 6. Conversation Context Management

### State Structure

```python
class ConversationContext:
    engagement_summary: str      # "Helping with meal planning, saved 2 recipes..."
    recent_turns: list[dict]     # Last 2-3 full exchanges
    history_summary: str         # Compressed older turns
    active_entities: dict        # EntityRef tracking for "that recipe"
```

### Context Thresholds

| Node | Threshold | Format |
|------|-----------|--------|
| Router | 8K tokens | Condensed (summaries) |
| Think | 8K tokens | Condensed |
| Act | 25K tokens | Full (complete step results) |
| Reply | 8K tokens | Condensed |

### Summarization

- **End-of-exchange:** Always runs after Reply
  - Compresses oldest turn via LLM
  - Updates engagement summary
  - Extracts entities from step results

- **Mid-loop (if >6K tokens):**
  - Compresses step results older than last 2
  - Never touches conversation (that's for end-of-exchange)

### Entity Tracking

```python
class EntityRef:
    type: str      # "recipe", "ingredient", "meal_plan"
    id: str        # UUID
    label: str     # "Butter Chicken" (human-readable)
    source: str    # "db_lookup", "user_input", "generated"
```

Enables resolution of "that recipe", "those ingredients", etc.

---

## 7. Prompt Engineering

### Maturity: Evolving

The prompts have gone through multiple iterations and are functional but still being refined.

### Current Structure (Act Node Example)

```
═══════════════════════════════════════════════════════════
SYSTEM PROMPT (~224 lines)
═══════════════════════════════════════════════════════════
1. Role (brief)
2. Tools (table + data format + batch examples)
3. Actions (table)
4. How to Execute (CRUD, Analyze, Generate patterns)
5. Principles (4 items)
6. Exit Contract (when to complete)
7. Tool Selection (step verbs → tools)

═══════════════════════════════════════════════════════════
USER PROMPT (variable)
═══════════════════════════════════════════════════════════
## STATUS (orientation)
Step | 2 of 4
Goal | Read inventory
Progress | 1 tool calls → Last: db_read returned 7 records

## 1. Task
User said: "..."
Your job this step: **Read inventory**

## 2. Tool Results This Step
Quick Reference (IDs):
- `uuid-1` — milk
- `uuid-2` — eggs
<details>Full JSON</details>

## 3. Schema
[subdomain tables]

## 4. Previous Steps
[summaries or full data]

## 5. Context
[active entities, recent conversation]

## DECISION
What's next? [format examples]
```

### Key Patterns

1. **STATUS at top** - Immediate orientation
2. **Quick Reference** - IDs/names extracted before JSON dumps
3. **Collapsible details** - Large data in `<details>` blocks
4. **DECISION at end** - Format reminder right before LLM outputs

### Known Issues Being Addressed

| Issue | Status |
|-------|--------|
| LLM hallucinating malformed JSON | Pre-validation with auto-fix |
| CRUD steps not calling tools | Explicit warnings in prompt |
| Context truncation causing data loss | Removed arbitrary truncation |
| Shopping list duplicates | Added "read before add" guidance in Think |

---

## 8. Model Routing

### Current Setup: Static

All nodes currently use `gpt-4.1-mini` with node-specific temperatures.

```python
NODE_TEMPERATURE = {
    "router": 0.15,   # Deterministic classification
    "think": 0.35,    # Some creativity for planning
    "act": 0.25,      # Low for reliable CRUD
    "reply": 0.6,     # Natural conversation
    "summarize": 0.3, # Consistent compression
}
```

### Future Considerations

| Scenario | Model | Reasoning |
|----------|-------|-----------|
| Simple CRUD | gpt-4.1-mini | Fast, cheap |
| Complex planning | gpt-4o or o1 | Better reasoning |
| Recipe generation | gpt-4o | Creative |
| Summarization | gpt-4.1-mini | Cheap, consistent |

### Complexity Routing (Planned, Not Active)

```python
complexity_to_model = {
    "low": "gpt-4.1-mini",
    "medium": "gpt-4o",
    "high": "o1",
}
```

---

## 9. What Works Well

| Capability | Status |
|------------|--------|
| Simple CRUD (add to pantry, check inventory) | ✅ Solid |
| Multi-item batch operations | ✅ Solid |
| Cross-domain queries (inventory → recipe → shopping) | ✅ Works |
| Recipe generation from ingredients | ✅ Works |
| Recipe CRUD with ingredient linking | ✅ Works |
| Shopping list management | ✅ Works |
| Multi-turn conversation with context | ✅ Works |
| Entity tracking ("that recipe") | ✅ Basic |

---

## 10. Current Limitations

| Limitation | Impact | Priority |
|------------|--------|----------|
| No cooking history/logs | Can't track what was made | High |
| No prep planning | Can't plan Sunday prep | Medium |
| No recipe variations | Can't link spicy vs mild versions | Low |
| Limited preferences | Missing equipment, goals, frequency | Medium |
| Flavor preferences unused | Table exists but not exposed | Low |
| No fuzzy ingredient matching | "pepper" ≠ "black pepper" | Medium |

---

## 11. Deployment

| Component | Platform |
|-----------|----------|
| Backend | Railway |
| Database | Supabase (Postgres) |
| Vectors | Supabase pgvector (not yet used) |
| Auth | Supabase Auth (basic) |
| UI | FastAPI web server (dev/testing) |

---

## Appendix: File Structure

```
alfred-v2/
├── src/alfred/
│   ├── graph/
│   │   ├── state.py          # AlfredState, ConversationTurn
│   │   ├── workflow.py       # LangGraph definition
│   │   └── nodes/
│   │       ├── router.py
│   │       ├── think.py
│   │       ├── act.py
│   │       ├── reply.py
│   │       └── summarize.py
│   ├── tools/
│   │   ├── crud.py           # db_read, db_create, db_update, db_delete
│   │   └── schema.py         # SUBDOMAIN_REGISTRY, auto-generation
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
│   ├── act.md
│   └── reply.md
├── migrations/
│   └── 001_core_tables.sql
└── docs/
    ├── ux_learnings.md
    └── architecture_overview.md  # This document
```

