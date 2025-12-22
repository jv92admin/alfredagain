# Alfred V2 - Architecture Document

> A modern LangGraph-based multi-agent assistant with Supabase persistence, leveraging reasoning models, dynamic model selection, and hybrid SQL+vector retrieval.

---

## Design Philosophy

### Lessons Learned from v1

| Issue | What Went Wrong | v2 Solution |
|-------|-----------------|-------------|
| **Over-structured LLM** | 261 examples, rigid task codes - treated LLM like it needed hand-holding | Trust the model, clear instructions, few examples |
| **6-tier pipeline** | Concept was sound, implementation was archaic - manually coded what frameworks provide | Same tiers, LangGraph abstractions |
| **JSON file database** | Fragile, hard to query, no transactions | Supabase with proper ACID transactions |
| **Task codes (S-W-INVENTORY)** | Brittle encoding, LLM confusion, maintenance burden | Natural language intent |
| **Context injection** | Biggest pain - what stage? what functions? how much history? | On-demand retrieval, graph position IS context |

### What Makes Alfred V2 Magical

| Feature | Why It Matters | How We Achieve It |
|---------|---------------|-------------------|
| **Memory** | Truly remembers everything about you | Vector storage + conversation history via Responses API |
| **Cross-domain intelligence** | Meal plan affects workout suggestions | Shared state, agents read each other's data |
| **Proactive suggestions** | Notices things, suggests before you ask | Background analysis triggers, notification patterns |
| **Natural conversation** | No awkward clarification loops | LangGraph handles multi-turn natively |

### Non-Negotiable Requirements

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| **Data reliability** | Absolute | Supabase transactions, Pydantic validation, never lose data |
| **Observable** | Very important | LangSmith integration, structured logging from day 1 |
| **Extensible** | Iterate | Clean agent interface, < 1 day to add new domain |
| **Testable** | Iterate | Deterministic where possible, tests as we build |

---

## Orchestration Architecture

### Graph Flow

```
┌────────┐   ┌───────┐   ┌──────────────────┐   ┌───────┐
│ ROUTER │──▶│ THINK │──▶│     ACT LOOP     │──▶│ REPLY │
└────────┘   └───────┘   │                  │   └───────┘
     │            │      │ • Execute steps  │        │
     │            │      │ • Emit actions   │        │
     │            │      │ • Loop or exit   │        │
     │            │      └──────────────────┘        │
     │            │              │                   │
     └────────────┴──────────────┴───────────────────┘
                         │
                    SHARED STATE
```

### Node Responsibilities

| Node | Purpose | Inputs | Outputs |
|------|---------|--------|---------|
| **Router** | Classify intent, pick agent, set complexity | User message, preferences summary | `{ agent, goal, complexity, context_needs }` |
| **Think** | Domain-specific planning | Goal, RAG context for agent | `{ goal, steps[] }` with natural language steps |
| **Act Loop** | Execute steps via tools | Steps, tool access | Structured actions until terminal state |
| **Reply** | Synthesize user response | Execution results | Natural language response with agent persona |

### Key Design Decisions

1. **No task codes** - Natural language intent; deterministic `agent` + `complexity`
2. **No separate REFLECT node** - Reflection is embedded in Act loop's structured actions
3. **Complexity-driven model selection** - Router/Think set complexity → model router picks appropriate model
4. **Multi-agent (`call_agent`) is future scope** - MVP is single-agent per request
5. **`blocked` is first-class** - Agents emit structured "I'm stuck" signals; orchestrator decides policy
6. **EntityRef everywhere** - All object references use `{type, id, label, source}`; prevents ID brittleness
7. **Tool discipline** - Tools return IDs, accept IDs; LLMs never fabricate identifiers or write SQL

---

## Core Contracts

### Router Output

```python
class RouterOutput(BaseModel):
    agent: Literal["pantry", "coach", "cellar"]
    goal: str  # Natural language
    complexity: Literal["low", "medium", "high"]
    context_needs: list[str] = []  # ["inventory", "preferences", "recipes"]
```

### Think Output

```python
class ThinkOutput(BaseModel):
    goal: str
    steps: list[Step]

class Step(BaseModel):
    name: str  # "Check pantry for missing ingredients"
    complexity: Literal["low", "medium", "high"] = "medium"
```

### Act Loop Actions

The Act loop emits structured actions. Each action type has a specific schema:

```python
# Base action types
ActionType = Literal["tool_call", "step_complete", "ask_user", "blocked", "fail"]
# Future: add "call_agent" for multi-agent

class ToolCallAction(BaseModel):
    action: Literal["tool_call"]
    tool: str              # "find_ingredients", "add_to_inventory"
    arguments: dict        # Tool-specific args
    
class StepCompleteAction(BaseModel):
    action: Literal["step_complete"]
    step_name: str         # Which step was completed
    result_summary: str    # Brief description of outcome
    refs: list[EntityRef]  # Any entities created/modified

class AskUserAction(BaseModel):
    action: Literal["ask_user"]
    question: str          # Clear, single question
    context: str           # Why we need this info

class BlockedAction(BaseModel):
    action: Literal["blocked"]
    reason_code: Literal[
        "INSUFFICIENT_INFORMATION",  # Need user input
        "PLAN_INVALID",              # Current plan won't work
        "TOOL_FAILURE",              # Tool returned error
        "AMBIGUOUS_INPUT"            # Multiple interpretations possible
    ]
    details: str           # Human-readable explanation
    suggested_next: Literal["ask_user", "replan", "fail"]

class FailAction(BaseModel):
    action: Literal["fail"]
    reason: str            # Why we can't proceed
    user_message: str      # What to tell the user

# Future scope:
class CallAgentAction(BaseModel):
    action: Literal["call_agent"]
    target_agent: str      # "coach", "cellar"
    goal: str              # What the other agent should do
    handoff: AgentHandoff  # Refs and context to pass
```

---

## Orchestrator Policy

### Handling `blocked` Actions

When an agent emits `blocked`, the orchestrator applies a deterministic three-tier policy:

| Condition | Action | Example |
|-----------|--------|---------|
| Missing info is **user-owned** and clarifiable in one question | `ask_user` | "Do you prefer vegetarian lunches?" |
| **Plan invalidation** or tool failure that changes approach | `replan` | Tool returned "recipe not found" |
| **Neither feasible** | `fail` gracefully | Unrecoverable error |

The orchestrator reads `suggested_next` as a hint but makes the final decision based on policy.

### Replanning Scope

- **Default:** Replan only at agent boundaries (after agent completes or fails)
- **Exception:** Mid-agent replan only when `reason_code: "PLAN_INVALID"`

This preserves latency while retaining adaptiveness.

---

## Entity Reference Pattern

All meaningful objects passed through the system use EntityRef. This prevents "pass name strings and pray" brittleness.

```python
class EntityRef(BaseModel):
    type: str      # "ingredient", "recipe", "meal_plan", "pantry_item"
    id: str        # "ing_123", "rec_456"
    label: str     # "tomato" (human-readable for LLM context)
    source: str    # "db_lookup", "user_input", "generated"
```

### Rules

1. **Tools always return EntityRefs** (or lists of them)
2. **Tools accept IDs** for operations, not raw strings
3. **LLMs never fabricate IDs** - they come from tool responses
4. **LLMs never construct SQL** - they call tools

### Example Tool Contracts

```python
def find_ingredients(query: str) -> list[EntityRef]:
    """
    Resolves natural language to canonical ingredients.
    Returns multiple matches if ambiguous.
    """
    # Returns: [EntityRef(type="ingredient", id="ing_123", label="Tomato", source="db_lookup")]

def add_to_inventory(
    user_id: str,
    ingredient_id: str,  # Must be valid ID from find_ingredients
    quantity: float,
    unit: str
) -> EntityRef:
    """
    Adds item to user's inventory.
    Returns the created pantry item ref.
    """
    # Returns: EntityRef(type="pantry_item", id="pi_789", label="2 lbs Tomato", source="generated")

def upsert_recipe(recipe: RecipeInput) -> EntityRef:
    """
    Creates/updates recipe. Auto-resolves ingredient names to IDs.
    Creates missing ingredients in the ingredients table.
    """
    # Returns: EntityRef(type="recipe", id="rec_456", label="Pasta Carbonara", source="generated")
```

### Handoff Artifacts (Future Multi-Agent)

When one agent invokes another, it passes refs, not blobs:

```python
class AgentHandoff(BaseModel):
    source_agent: str           # "pantry"
    target_agent: str           # "coach"
    refs: list[EntityRef]       # IDs for target to query if needed
    context: dict = {}          # Small summary data only
    # Example context: {"calorie_target": 2200, "days": 5}
```

---

## Contract Summary (Quick Reference)

| Contract | Key Fields | Purpose |
|----------|------------|---------|
| **RouterOutput** | `agent`, `goal`, `complexity` | Route to correct agent with context |
| **ThinkOutput** | `goal`, `steps[]` | Natural language plan for execution |
| **ActAction** | `action` + type-specific fields | Structured execution signals |
| **BlockedAction** | `reason_code`, `suggested_next` | Deterministic "I'm stuck" signal |
| **EntityRef** | `type`, `id`, `label`, `source` | Safe object references everywhere |
| **AgentHandoff** | `refs[]`, `context` | Lightweight cross-agent communication |

---

## Dynamic Model Selection

| Task Complexity | Model | Why |
|-----------------|-------|-----|
| Simple CRUD ("add milk") | `gpt-4o-mini` | Fast, cheap, sufficient |
| Standard queries | `gpt-4o` | Good balance |
| Complex planning (meal plan + shopping) | `o1` / `o3-mini` | Deep reasoning needed |
| Cross-domain analysis | `o1` | Multi-step reasoning |

The Router sets `complexity` and the model router maps it:

```python
def select_model(complexity: str) -> str:
    return {
        "low": "gpt-4o-mini",
        "medium": "gpt-4o", 
        "high": "o1"
    }.get(complexity, "gpt-4o")
```

---

## OpenAI Responses API

Instead of passing full conversation history every call, OpenAI stores conversation state:

```python
response = client.responses.create(
    model="gpt-4o",
    input=user_message,
    previous_response_id=last_response_id  # OpenAI remembers context
)
```

**Benefits:** Less tokens, auto-summarization, faster responses, built-in continuity.

---

## Project Structure

```
alfred-v2/
├── src/alfred/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point (Typer + Rich)
│   │
│   ├── graph/                  # LangGraph orchestration
│   │   ├── __init__.py
│   │   ├── state.py            # AlfredState TypedDict
│   │   ├── nodes/
│   │   │   ├── router.py       # Intent classification, agent + complexity selection
│   │   │   ├── think.py        # Domain planning, generates steps
│   │   │   ├── act.py          # Execution loop with structured actions
│   │   │   └── reply.py        # Synthesize final response
│   │   └── workflow.py         # Graph construction + edges
│   │
│   ├── agents/                 # Domain agents (prompts + tools)
│   │   ├── __init__.py
│   │   ├── base.py             # BaseAgent protocol
│   │   ├── pantry/             # Pantry agent (fully implemented)
│   │   ├── coach/              # Coach agent (stubbed)
│   │   └── cellar/             # Cellar agent (stubbed)
│   │
│   ├── llm/                    # LLM infrastructure
│   │   ├── __init__.py
│   │   ├── client.py           # Instructor-wrapped OpenAI client
│   │   ├── model_router.py     # Complexity → model mapping
│   │   └── responses.py        # OpenAI Responses API wrapper
│   │
│   ├── db/                     # Supabase integration
│   │   ├── __init__.py
│   │   ├── client.py           # Typed Supabase client
│   │   ├── models.py           # Pydantic models (all entities)
│   │   └── context.py          # Hybrid retrieval (SQL + vector)
│   │
│   ├── tools/                  # Tool definitions (return EntityRefs)
│   │   ├── __init__.py
│   │   ├── inventory.py
│   │   ├── recipes.py
│   │   └── meal_plans.py
│   │
│   ├── memory/                 # Long-term memory
│   │   ├── __init__.py
│   │   ├── store.py            # Embedding storage
│   │   └── retriever.py        # Vector similarity search
│   │
│   ├── proactive/              # Proactive suggestions
│   │   ├── __init__.py
│   │   ├── triggers.py         # Expiry alerts, restock, meal inspiration
│   │   └── analyzer.py         # Pattern detection
│   │
│   └── config.py               # Environment + settings (pydantic-settings)
│
├── scripts/
│   ├── seed_ingredients.py     # Seed from Open Food Facts
│   ├── seed_recipes.py         # Seed from Spoonacular
│   └── seed_flavors.py         # Seed from FlavorDB (optional)
│
├── migrations/                 # SQL migration files
│   ├── 001_core_tables.sql
│   ├── 002_vectors.sql
│   └── 003_triggers.sql
│
├── tests/
├── prompts/                    # Minimal prompt templates
├── pyproject.toml
├── .env.example
└── README.md
```

Note: No `reflect.py` - reflection is embedded in `act.py`'s action schema.

---

## Context Retrieval Strategy

The biggest frustration in v1 was context injection. v2 uses a **hybrid on-demand retrieval** pattern:

### The Problem We're Solving

| Challenge | v1 Approach | v2 Solution |
|-----------|-------------|-------------|
| "What stage are we in?" | Manual tracking in orchestrator | Graph position IS the stage |
| "What functions available?" | Complex YAML capability injection | Tools bound to nodes |
| "How much history?" | Manual truncation, custom summarizer | Responses API handles it |
| "Long ingredient lists" | Dump everything, hope it fits | Query only what's needed |
| "Recipe catalog search" | Load all, filter in prompt | Vector search, return top-k |

### Hybrid Retrieval Pattern

```python
class ContextRetriever:
    """On-demand context retrieval - never dump, always query."""
    
    async def get_context(self, query: str, user_id: str, needs: list[str]) -> dict:
        context = {}
        
        # Structured queries for exact data
        if "inventory" in needs:
            context["inventory"] = await self.sql_query(
                "SELECT * FROM inventory WHERE user_id = $1 AND quantity > 0",
                user_id
            )
        
        # Semantic search for fuzzy matching  
        if "recipes" in needs:
            query_embedding = await self.embed(query)
            context["relevant_recipes"] = await self.vector_search(
                "recipes", query_embedding, limit=5
            )
        
        # Always include preferences (small, always relevant)
        context["preferences"] = await self.get_preferences(user_id)
        
        # Relevant conversation memory
        context["memory"] = await self.vector_search(
            "conversation_memory", 
            await self.embed(query), 
            limit=3
        )
        
        return context
```

### When to Use What

| Data Type | Retrieval Method | Why |
|-----------|-----------------|-----|
| User inventory | SQL with filters | Structured, exact matches |
| Preferences | SQL (always inject) | Small, always relevant |
| Recipe search | Vector similarity | Semantic ("something like curry") |
| Ingredient lookup | SQL + vector fallback | Exact first, fuzzy if no match |
| Conversation memory | Vector similarity | Find relevant past context |
| Shopping list | SQL | Structured list |

---

## Proactive Suggestions System

Alfred shouldn't just respond - it should **notice and suggest**:

### Trigger Types

| Trigger | Example | Implementation |
|---------|---------|----------------|
| **Expiry alerts** | "Your milk expires tomorrow" | Background job checks inventory.expiry_date |
| **Restock suggestions** | "You're low on eggs (used 3x this week)" | Track usage patterns, threshold alerts |
| **Meal inspiration** | "You have ingredients for pasta carbonara" | Match inventory → recipes periodically |
| **Preference learning** | "You seem to love Thai food lately" | Analyze meal_plan patterns |
| **Shopping optimization** | "Add these 3 items to complete your meal plan" | Diff meal_plan ingredients vs inventory |

### Delivery

Suggestions surface naturally in conversation:
- When user starts a session, include relevant suggestions in context
- "By the way, your milk expires tomorrow and you could make French toast with what you have"

---

## Data Seeding Strategy

Alfred is more useful with baseline data. We'll seed from public APIs:

### Data Sources

| Source | What We Get | Free Tier |
|--------|-------------|-----------|
| [Spoonacular](https://spoonacular.com/food-api) | 5,000+ recipes, ingredients, nutrition | 150 calls/day |
| [Open Food Facts](https://world.openfoodfacts.org/data) | Ingredient database, barcodes | Unlimited (open data) |
| [FlavorDB](https://cosylab.iiitd.edu.in/flavordb/) | Flavor compound pairings | Academic/free |
| [Edamam](https://developer.edamam.com/) | Recipe search, nutrition analysis | 10,000 calls/month |

### User Data Layering

```
┌─────────────────────────────────────────────┐
│           USER DATA (personal)               │
│  • Their inventory                           │
│  • Their created recipes                     │
│  • Their preferences & restrictions          │
│  • Their flavor preferences (learned)        │
├─────────────────────────────────────────────┤
│         SYSTEM DATA (seeded)                 │
│  • 2000+ ingredients with nutrition          │
│  • 500+ popular recipes                      │
│  • Flavor compound pairings                  │
│  • Category taxonomies                       │
└─────────────────────────────────────────────┘
```

---

## Tech Stack Summary

| Layer | Technology | Why |
|-------|------------|-----|
| **Orchestration** | LangGraph | Graph-based thinking loop, state management |
| **Structured Output** | Instructor | Guaranteed schema, retries |
| **Database** | Supabase (Postgres) | SQL + vectors + auth in one |
| **Vector Search** | pgvector | No separate vector DB needed |
| **Conversation Memory** | OpenAI Responses API | Stored state, auto-summarization |
| **Models** | gpt-4o-mini / gpt-4o / o1 | Dynamic selection by complexity |
| **Validation** | Pydantic | Single source of truth for schemas |
| **CLI** | Typer + Rich | Modern Python CLI |
| **Observability** | LangSmith | Trace every LLM call |

---

## Success Criteria

### Must Have (Launch Criteria)

| Criteria | Metric |
|----------|--------|
| **Data reliability** | Zero data loss in 100 mutation tests |
| **Memory works** | Can recall facts from 10 turns ago |
| **Cross-domain** | Meal plan correctly considers preferences |
| **Natural conversation** | No forced clarification loops in happy path |
| **Observable** | Can trace any request through full flow |

### Should Have (Quality Bar)

| Criteria | Metric |
|----------|--------|
| **Simplicity** | < 2,500 Python LOC (vs 8,000+) |
| **Extensibility** | New agent in < 1 day |
| **Response quality** | LLM picks right model 90%+ |
| **Proactive** | At least 2 suggestion types working |

### Nice to Have (Stretch)

| Criteria | Metric |
|----------|--------|
| **Speed** | < 2s typical response |
| **Full seeding** | 2000+ ingredients, 500+ recipes |
| **Flavor pairing** | Compound-based suggestions working |
