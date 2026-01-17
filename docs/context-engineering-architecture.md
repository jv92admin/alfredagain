# Alfred Context Engineering Architecture

> This document describes **how the system works**, not how it got here.
> No phases, no versions — just the current architecture.

---

## Philosophy

Alfred is a multi-agent system where LLMs interpret context but do not own state.

**Core Principle:** Deterministic systems manage state. LLMs interpret and decide.

| Layer | Responsibility | Deterministic? |
|-------|---------------|----------------|
| CRUD Layer | Database operations, ID translation, FK enrichment | ✅ Yes |
| Session Registry | Entity tracking, action history, context curation | ✅ Yes |
| Summarization | Conversation compression | Mostly ✅ |
| Understand | Context curation, entity resolution (Memory Manager) | 🤖 LLM |
| Think | Planning | 🤖 LLM |
| Act | Execution | 🤖 LLM |
| Reply | Response synthesis | 🤖 LLM |

---

## 1. Entity Management

### What is an Entity?

An entity is anything with an ID that persists: recipes, inventory items, meal plans, tasks.

### Single Source of Truth: `SessionIdRegistry`

**One system. No alternatives.**

```
┌─────────────────────────────────────────────────────────────┐
│                    SessionIdRegistry                        │
├─────────────────────────────────────────────────────────────┤
│ CORE ID MAPPING                                             │
│   ref_to_uuid:      recipe_1 → abc123-uuid...              │
│   uuid_to_ref:      abc123-uuid... → recipe_1              │
│                                                             │
│ ENTITY METADATA                                             │
│   ref_actions:      recipe_1 → "created"                   │
│   ref_labels:       recipe_1 → "Butter Chicken"            │
│   ref_types:        recipe_1 → "recipe"                    │
│                                                             │
│ TEMPORAL TRACKING                                           │
│   ref_turn_created: recipe_1 → 3                           │
│   ref_turn_last_ref: recipe_1 → 5                          │
│   ref_source_step:  gen_recipe_1 → 2                       │
│                                                             │
│ GENERATED CONTENT                                           │
│   pending_artifacts: gen_recipe_1 → {full JSON content}    │
│                                                             │
│ V5: CONTEXT CURATION                                        │
│   ref_active_reason: gen_meal_plan_1 → "User's ongoing goal"│
│   _lazy_enrich_queue: {ref: (table, name_col)} (transient) │
└─────────────────────────────────────────────────────────────┘
```

### Entity Lifecycle (Deterministic)

| Action | Set By | Where |
|--------|--------|-------|
| `read` | CRUD layer | `translate_read_output()` |
| `created` | CRUD layer | `register_created()` |
| `updated` | CRUD layer | After `db_update` succeeds |
| `deleted` | CRUD layer | After `db_delete` succeeds |
| `generated` | Act node | `register_generated()` |
| `linked` | CRUD layer | FK lazy registration |

**No LLM involvement in entity lifecycle tracking.**

### V5: FK Lazy Registration with Enrichment

When `db_read` returns records with FK fields (e.g., meal_plans with recipe_id):

1. **Lazy Registration:** Unknown FK UUIDs get refs immediately (no UUID leaks)
2. **Batch Enrichment:** `_enrich_lazy_registrations()` queries target tables for names
3. **Label Update:** `ref_labels` populated with real names ("Butter Chicken")
4. **Display Enrichment:** `_add_enriched_labels()` adds `_*_label` fields to result

**Works for:** recipes, ingredients, tasks (anything with name/title column)

### View Methods (Presentation, Not Storage)

Instead of separate data structures, `SessionIdRegistry` provides views:

| Method | Purpose |
|--------|---------|
| `format_for_understand_prompt()` | Full context with turn annotations |
| `format_for_think_prompt()` | Entity summary for planning (delineated sections) |
| `get_entities_this_turn()` | Filter by current turn |
| `get_active_entities(turns_window)` | Returns (recent_refs, retained_refs) tuple |

**Note:** Act's entity context is built by `_build_enhanced_entity_context()` in `act.py`, which merges registry data with step results from the last 2 turns.

---

## 2. ID Management

### The Problem We Solved

LLMs should never see UUIDs. They're hard to work with and easy to hallucinate.

### The Solution

| What LLMs See | What DB Uses | Translation Layer |
|---------------|--------------|-------------------|
| `recipe_1` | `abc123-...` | `SessionIdRegistry` |
| `gen_recipe_1` | (pending) | `SessionIdRegistry` |
| `inv_5` | `def456-...` | `SessionIdRegistry` |

### ID Flow

```
db_read → SessionIdRegistry.translate_read_output() → LLM sees recipe_1
       → _enrich_lazy_registrations() → FK names fetched
       → _add_enriched_labels() → result has _recipe_id_label

LLM says "delete recipe_1" → SessionIdRegistry.translate_filters() → db_delete with UUID
```

**100% deterministic. No LLM guessing IDs.**

---

## 3. Turn and Step Context Management

### Definitions

| Term | Scope | What It Contains |
|------|-------|------------------|
| **Session** | Multiple conversations | User preferences, persistent state |
| **Turn** | One user message → one assistant response | All steps executed |
| **Step** | One operation within a turn | Read/Write/Analyze/Generate |

### What Each Node Receives

| Node | Receives | Uses For |
|------|----------|----------|
| **Understand** | User message, annotated conversation, previous decisions | Context curation, entity resolution |
| **Think** | Goal, delineated entity context, dashboard | Planning steps |
| **Act** | Step description, prior step results, delineated entities | Executing one step |
| **Reply** | Execution summary, step results | Synthesizing response |
| **Summarize** | Full response, execution results, registry | Persisting state |

### V5: Understand as Memory Manager

Understand's primary role is **context curation**, not message rewriting.

**What Understand Does:**
- Reference resolution: "that recipe" → `recipe_1`
- Context curation: decide what stays active beyond 2-turn window
- Retention decisions: explain WHY older entities should persist
- Quick mode detection (single-part, single-domain READ only)

**What Understand Does NOT Do:**
- Rewrite/interpret user message (removed `processed_message`)
- Give instructions to Think
- Look up UUIDs

### Entity Context Delineation

Both Think and Act see entities in delineated sections:

```
## ⚠️ Generated (NOT YET SAVED)
- gen_recipe_1: Thai Curry (recipe) [needs save]

## Recent Context (last 2 turns)
**These entities are already loaded. Do NOT re-read them.**
Reference by ID (e.g., `recipe_3`) in step descriptions. Act can use them directly.

- recipe_1: Butter Chicken (recipe) [read]
- inv_1: Eggs (inv) [read]

## Long Term Memory (retained from earlier)
- gen_meal_plan_1: Weekly Plan (meal, turn 2) — *User's ongoing goal*
```

### V6: Recent Context Guidance

**Key insight:** Entities in Recent Context are already in memory.

| If Think sees... | Think should... |
|------------------|-----------------|
| `recipe_1` through `recipe_9` in Recent Context | Skip read step, plan analyze directly |
| User says "exclude recipe_5, recipe_6" | Plan: "Analyze recipes excluding recipe_5, recipe_6" |

**Act receives similar guidance:**
```
## Recent Context (last 2 turns)
**Already loaded — use IDs directly in filters instead of re-querying.**
Example: `{"field": "id", "op": "in", "value": ["recipe_3", "recipe_4"]}`
```

This prevents redundant database queries and ensures Act uses the correct filtering approach.

---

## 4. Dynamic Prompt Injection

### Step Type System

| Step Type | Purpose | Prompt Injections |
|-----------|---------|-------------------|
| `read` | Query database | Schema, filter examples |
| `write` | Modify database | Schema, FK patterns, content to save |
| `analyze` | Reason over data | Prior step results, analysis framework |
| `generate` | Create content | User preferences, constraints, examples |

### Subdomain System

Each subdomain (recipes, inventory, meal_plans, etc.) has:
- Schema information
- Domain-specific patterns
- Example queries/operations

### V5: Step-Scoped Schema Injection

Act only sees schema for tables relevant to current step:
- meal_plans step → meal_plans schema only (not recipes)
- Prevents Act from overstepping step scope

### Display Formatting

| Entity Type | Display Format |
|-------------|----------------|
| Recipes | `- Butter Chicken total_time:45min id:recipe_1` |
| Meal Plans | `- 2026-01-12 [lunch] → Butter Chicken (recipe_1) id:meal_1` |
| Inventory | `- Eggs (12 count) [fridge] id:inv_1` |
| Tasks | `- Buy groceries @2026-01-15 [pending] id:task_1` |

---

## 5. Semantic Search Integration

### The Problem

Users express intent, not SQL:
- "something light for summer" — no column for "lightness"
- "quick comfort food" — vibes, not filters
- "healthy breakfast ideas" — semantic meaning

### The Solution: Hybrid Search

`db_read` supports a special `_semantic` filter that uses pgvector embeddings:

```python
# Intent-based query
filters=[{"field": "_semantic", "op": "similar", "value": "light summer dinner"}]

# Hybrid: semantic + exact (AND logic)
filters=[
    {"field": "_semantic", "op": "similar", "value": "light summer"},
    {"field": "name", "op": "ilike", "value": "%chicken%"}
]
```

### How It Works

| Step | What Happens |
|------|--------------|
| 1. Extract `_semantic` | Separate from other filters |
| 2. Generate embedding | OpenAI `text-embedding-3-small` on query |
| 3. Vector search | `match_recipe_semantic()` returns matching IDs |
| 4. Apply as filter | `WHERE id IN (semantic_matches)` |
| 5. Apply other filters | Remaining filters narrow further |

**Result:** Semantic narrows first, then exact filters refine.

### Currently Supported

| Table | Semantic Search | Why |
|-------|-----------------|-----|
| `recipes` | ✅ Yes | Has `embedding` column, rich text (name, description, tags) |
| `ingredients` | ✅ Yes | Has `embedding` column (used by ingredient_lookup) |
| `meal_plans` | ❌ No | Just date + recipe_id — no semantic content |
| `inventory` | ❌ No | Structured data (quantity, location) |

### Multi-Step Pattern for Meal Plans

For "light summer meals in my meal plan", Think plans two steps:

```
Step 1: [read/recipes] semantic search "light summer"
        → returns [recipe_1, recipe_5, recipe_8]

Step 2: [read/meal_plans] filter recipe_id IN [recipe_1, recipe_5, recipe_8]
        → returns meal plans with those recipes
```

**Think handles the sequential planning. Act executes each step.**

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Semantic + filter logic | AND (intersection) | "light chicken" means BOTH light AND chicken |
| Who decides search type | Think (LLM) | Flexibility for complex queries |
| Embedding model | `text-embedding-3-small` | Cost-effective, 1536 dimensions |
| Distance threshold | 0.6 (configurable) | Balance precision/recall |

### Future Consideration: Auto-Hybrid (OR logic)

If needed, could add union mode:
- Semantic matches OR exact matches
- Would broaden results instead of narrowing
- Not implemented yet — current AND logic covers most use cases

---

## 6. State vs Context

### Definitions

| Term | Meaning | Who Owns It |
|------|---------|-------------|
| **State** | Ground truth, persisted, deterministic | System (DB, Registry) |
| **Context** | Interpreted, curated, probabilistic | LLMs (Understand, Think) |

### Per-Node Breakdown

| Node | Reads State | Reads Context | Writes State | Writes Context |
|------|-------------|---------------|--------------|----------------|
| Understand | Entity registry | Conversation history | - | Entity curation decisions |
| Think | Dashboard, constraints | Entity context, user intent | - | Execution plan |
| Act | Schema, registry | Prior steps, step description | DB via CRUD | Step results |
| Reply | Execution results | - | - | Final response |
| Summarize | Execution facts | - | Conversation history, registry | - |

### The Key Insight

**State changes are deterministic:**
- `db_create` succeeded → entity is `created`
- `db_delete` succeeded → entity is removed
- No LLM decides this.

**Context is interpreted:**
- "that recipe" → Understand resolves to `recipe_1`
- "I want something spicy" → Think incorporates into plan
- LLMs make these calls.

---

## 7. V5 Enhancements Summary

| Feature | Implementation |
|---------|----------------|
| Understand as Memory Manager | Removed `processed_message`, added context curation |
| Long-term entity retention | `ref_active_reason` stores WHY older entities stay active |
| FK lazy registration | Unknown FK UUIDs get refs immediately |
| Batch name enrichment | `_enrich_lazy_registrations()` queries for names |
| Post-process labels | `_add_enriched_labels()` adds labels after enrichment |
| Delineated entity sections | Pending → Recent → Long Term Memory |
| Entity-type labels | `_compute_entity_label()` for type-specific formatting |
| Meal plan display | `date [slot] → recipe_name (ref) id:meal_X` |
| Multi-part query exclusion | "X and Y" explicitly not quick mode |

---

## 8. V6 Enhancements Summary

| Feature | Implementation |
|---------|----------------|
| Think as conversation architect | Redesigned prompt with Kitchen UX principles, propose/clarify emphasis |
| Recent Context guidance | Explicit "already loaded, don't re-read" instructions in prompts |
| Smart inventory/shopping search | `name = "chicken"` uses `ingredient_lookup` for fuzzy matching |
| Entity retention on analyze | `touch_refs_from_step_data()` keeps mentioned entities active |
| Off-by-one fix | `<=` instead of `<` for 2-turn window (inclusive) |
| Reply prompt redesign | Presentation agent with explicit formatting rules |

---

## 9. V7 Enhancements Summary (Context API)

| Feature | Implementation |
|---------|----------------|
| **Three-layer Context API** | `src/alfred/context/` module with entity, conversation, reasoning builders |
| **TurnExecutionSummary** | Pydantic model capturing Think decision, steps, phase, curation |
| **Reasoning Trace** | Last 2 turn summaries passed to Think for continuity |
| **Prior Turn Steps** | Act sees last 2 steps from previous turn |
| **Conversation Continuity** | Reply sees phase/tone for natural flow |
| **Generate entity context fix** | Generate steps now see entity refs (for meal plan recipe_ids) |
| **Artifact promotion tracking** | `ref_turn_promoted` + `clear_turn_promoted_artifacts()` for linked tables |
| **Recipe data levels guidance** | Think knows when to request "with instructions" |

### Context API Files

```
src/alfred/context/
├── __init__.py
├── entity.py        # get_entity_context(), format_entity_context()
├── conversation.py  # get_conversation_history(), format_conversation()
├── reasoning.py     # get_reasoning_trace(), format_reasoning()
└── builders.py      # build_think_context(), build_act_context(), build_reply_context()
```

### TurnExecutionSummary Structure

```python
class TurnExecutionSummary(BaseModel):
    turn_num: int
    think_goal: str
    think_decision: str           # "plan_direct" | "propose" | "clarify"
    conversation_phase: str       # "exploring" | "narrowing" | "confirming" | "executing"
    user_expressed: str
    steps: list[StepExecutionSummary]
    curation: CurationSummary | None
```

### Known Gaps (Documented)

1. **Recent Context ≠ Data Loaded**: Refs in "Recent Context" don't mean full data is available to Act
2. **Solution path**: Consider storing condensed snapshots alongside refs

### Smart Inventory/Shopping Search

`db_read` for `inventory` and `shopping_list` tables now uses intelligent ingredient matching:

```python
# LLM requests
{"field": "name", "op": "=", "value": "chicken"}

# System does (behind the scenes)
1. lookup_ingredient("chicken") → finds ingredient_id for chicken, chicken breasts, etc.
2. Builds query: WHERE ingredient_id IN (...) OR name ILIKE '%chicken%'
3. Returns all matching items
```

| Operator | Behavior |
|----------|----------|
| `op: "="` | Smart single match via ingredient lookup |
| `op: "similar"` | Returns top N candidates (with `limit` param) |

**LLMs don't need to know the mechanics.** Simple `name = "chicken"` works.

### Entity Retention on Analyze/Generate

When `step_complete` returns for analyze or generate steps:
- System extracts all entity refs from `data` and `result_summary`
- Calls `touch_ref()` on each to update `last_ref_turn`
- Entities stay in Recent Context for subsequent steps

This fixes the problem where recipes mentioned in Analyze output would "fall out" of context before Generate could use them.

---

## Critical Insights

### Three-Layer Context Model (V7)

Alfred uses a Context API with three layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT API                                   │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: ENTITY         │  LAYER 2: CONVERSATION  │  LAYER 3: REASONING    │
│  "What exists"           │  "What was said"        │  "What LLMs decided"   │
│  Owner: SessionIdRegistry│  Owner: Summarize       │  Owner: Summarize      │
│  + Understand curation   │                         │  (TurnExecutionSummary)│
└─────────────────────────────────────────────────────────────────┘
```

| Layer | Survives Turns | Contains |
|-------|----------------|----------|
| **Entity** | ✅ Yes | Refs, labels, types, turn numbers, retention reasons |
| **Conversation** | ✅ Yes | User/assistant messages, compressed history |
| **Reasoning** | ✅ Yes (last 2) | TurnExecutionSummary: decision, steps, phase, curation |

**Node-specific builders:** `src/alfred/context/builders.py`
- `build_think_context()` — Entity (refs+labels) + Conversation + Reasoning
- `build_act_context()` — Entity (refs+labels) + Prior turn steps + Step results
- `build_reply_context()` — Entity (labels only) + Conversation phase/tone

### Refs vs Content (The Gap)

**What SessionIdRegistry stores per entity:**
- ✅ Ref → UUID mapping
- ✅ Label (e.g., "Butter Chicken")
- ✅ Type, last action, turn info
- ❌ Full entity content (metadata, ingredients, instructions)

**What step_results stores:**
- ✅ Full entity content from reads
- ❌ Does NOT survive turns (wiped when Think creates new plan)

**Implication for Think's planning:**

| Step Type | What Act Needs | Refs Sufficient? |
|-----------|----------------|------------------|
| write/delete | Just the ref | ✅ Yes |
| generate (meal plan with IDs) | Refs to use as recipe_id | ✅ Yes |
| generate (with diffs/substitutions) | **Full instructions** | ❌ No — read with instructions! |
| analyze (compare/match) | **Full row data** | ❌ No — read first! |

### ✅ The Recent Context Gap (FIXED in V7.1)

**The problem (was):**
1. Think sees "Recent Context": `recipe_1: Chicken Tikka (recipe) [read]`
2. Think assumes data is "loaded" and plans: `analyze recipes for inventory match`
3. Act runs analyze step... but only has the REF, not the actual recipe data!
4. If recipe was read in Turn N-1 (not this turn), step_results was already wiped.

**V7.1 Fix:**
- `Summarize` now persists `step_results` → `conversation["turn_step_results"]`
- Keeps last 2 turns of data
- `Act` merges prior turn data with current step_results
- Full entity data (including instructions) now visible for active entities

**Current behavior:**
- "Recent Context (last 2 turns)" = refs + labels + **full data available**
- "Long Term Memory" = refs only (need re-read)

**Think should plan reads when:**
- Entity is in Long Term Memory (>2 turns old)
- Entity was never read (only linked via FK)

### Dashboard ≠ Context

**Dashboard** shows what exists in the database (e.g., "1 saved recipe").
**Entities in Context** shows what has refs registered in SessionIdRegistry.

If an entity appears in Dashboard but NOT in "Entities in Context":
- Think cannot use a ref for it (e.g., `recipe_1` doesn't exist)
- Think must search by NAME, not by ref

### Recent Context = Already Loaded (V6)

**This is the most important optimization insight:**

If Think sees `recipe_1` through `recipe_9` in "Recent Context (last 2 turns)":
- ❌ DON'T: Plan a read step to "read all recipes"
- ✅ DO: Plan an analyze step referencing those entities

Act sees the same context with explicit guidance:
- ❌ DON'T: Query `name not_ilike '%cod%'`  
- ✅ DO: Filter `id in ['recipe_3', 'recipe_4', ...]`

**Result:** Fewer database calls, correct entity filtering, better performance.

### Linked Entities

Entities discovered via FK (e.g., recipe_id in meal_plans):
- Registered with action `linked`
- Filtered from active entity lists
- Shown inline with parent records only

---

## 10. V7.1 Enhancements Summary (2026-01-15)

| Feature | Implementation |
|---------|----------------|
| **Turn counter fix** | Fixed double-increment bug in summarize.py (was adding +1 when workflow already did) |
| **step_results persistence** | Summarize saves to `conversation["turn_step_results"]`, prunes to last 2 turns |
| **Full instructions in Act** | `_format_recipe_data()` now shows actual instruction text, not just count |
| **Act prompt refactor** | Centralized in `injection.py` via `build_act_user_prompt()` (~280 lines removed from act.py) |
| **Act Quick criteria** | Tightened: single-table, read-only, data-lookup (no knowledge questions) |
| **Entity context consolidation** | `_build_enhanced_entity_context()` merges current + prior turn data |

### Key Bug Fixes

| Bug | Impact | Fix |
|-----|--------|-----|
| Turn counter double-increment | Entity recency miscalculated, cross-turn data misaligned | Remove extra `+1` in summarize.py |
| Instructions hidden | Act saw "7 steps [FULL DATA AVAILABLE]" but not actual text | Show full instruction content |
| Act Quick subdomain hallucination | Unknown subdomains crashed | Tighten Understand criteria (knowledge questions NOT quick) |

### Files Changed

| File | Changes |
|------|---------|
| `src/alfred/graph/nodes/summarize.py` | Persist step_results, fix turn counter |
| `src/alfred/graph/nodes/act.py` | `_build_enhanced_entity_context()`, `_format_recipe_data()` shows instructions |
| `src/alfred/prompts/injection.py` | `build_act_user_prompt()` main entry point |
| `prompts/understand.md` | Tightened quick mode criteria |

---

## 11. V7.2 Enhancements Summary (2026-01-16)

| Feature | Implementation |
|---------|----------------|
| **Profile for write steps** | Act now receives full user profile (skill, equipment, household) for write steps, not just analyze/generate |
| **Recipe ingredient refs** | `_format_recipe_data()` includes `ri_X` refs inline with ingredients for targeted updates |
| **Nested ID registration** | `translate_read_output()` registers nested `recipe_ingredients` IDs when recipes read with full details |
| **Meal plans clarification** | Subdomain guidance clarifies meal_plans stores recipe_id refs, NOT ingredient data |
| **Recipe creation guidance** | Act guidance for input normalization when creating recipes from varied formats |

### Bug Fixes

| Bug | Impact | Fix |
|-----|--------|-----|
| Summary duplication | Conversation summary doubled on each compression | Don't prepend existing_summary (LLM already incorporates it) |
| Double instruction numbering | Recipe steps showed "3. 3. Do something" | Check if instruction already starts with number |
| Reply hallucination | Reply invented recipe details not in execution data | Witness Principle in prompt + data injection fix |
| Act skipping reads | Act was told to skip db_read if data "in context" | Removed skip guidance, context is reference only |
| Wrong update pattern | examples.py said delete+create for ingredient updates | Changed to db_update by row ID |

### Dead Code Removed

| File | Removed |
|------|---------|
| `injection.py` | `build_v4_context_sections()`, `build_write_context()`, `build_entity_context_for_understand()`, `build_summarize_context()` |
| `id_registry.py` | `format_for_act_prompt()` (replaced by `_build_enhanced_entity_context()` in act.py) |
| `schema.py` | Duplicate `get_contextual_examples()` |

---

*Last updated: 2026-01-16* (V7.2: Profile for writes, nested IDs, dead code cleanup, bug fixes)
