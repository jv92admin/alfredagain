# Alfred Context Engineering Architecture

> This document describes **how the system works**, not how it got here.
> No phases, no versions — just the current architecture.

---

## Philosophy

Alfred is a multi-agent system where LLMs interpret context but do not own state.

**Core Principle:** Deterministic systems manage state. LLMs interpret and decide.

| Layer | Responsibility | Deterministic? |
|-------|---------------|----------------|
| CRUD Layer | Database operations, ID translation | ✅ Yes |
| Session Registry | Entity tracking, action history | ✅ Yes |
| Summarization | Conversation compression | Mostly ✅ |
| Understand | Intent detection, entity resolution | 🤖 LLM |
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

**No LLM involvement in entity lifecycle tracking.**

### View Methods (Presentation, Not Storage)

Instead of separate data structures, `SessionIdRegistry` provides views:

| Method | Purpose | Replaces |
|--------|---------|----------|
| `format_for_act_prompt()` | Entities for current step | `WorkingSet` |
| `format_for_understand_prompt()` | Full context for curation | `EntityContextModel` |
| `format_for_think_prompt()` | Entity summary for planning | `EntityRegistry.get_for_prompt()` |
| `get_entities_this_turn()` | Filter by current turn | `turn_entities` state field |
| `get_entities_by_recency()` | Sort by last reference | Background tier logic |

### Deprecated Systems (TO DELETE)

| Module | Status | Replaced By |
|--------|--------|-------------|
| `entities.py` | ❌ DELETE | `SessionIdRegistry` |
| `entity_context.py` | ❌ DELETE | `SessionIdRegistry` view methods |
| `working_set.py` | ❌ DELETE | `SessionIdRegistry.format_for_act_prompt()` |
| `id_mapper.py` | ❌ DELETE | `SessionIdRegistry` |

### State Fields to Remove

| Field | Location | Replaced By |
|-------|----------|-------------|
| `entity_registry` | `AlfredState` | `id_registry` |
| `turn_entities` | `AlfredState` | `SessionIdRegistry.get_entities_this_turn()` |
| `entity_context` | `AlfredState` | `SessionIdRegistry` |
| `working_set` | `AlfredState` | `SessionIdRegistry` |
| `id_mapper` | `AlfredState` | `SessionIdRegistry` |

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
| **Understand** | User message, entity context, recent conversation | Intent detection, entity resolution |
| **Think** | Goal, entity context, constraints, dashboard | Planning steps |
| **Act** | Step description, working set, prior step results | Executing one step |
| **Reply** | Execution summary, step results | Synthesizing response |
| **Summarize** | Full response, execution results | Updating conversation history |

### Summarization Rules

**What Summarize SHOULD do:**
- Append current turn to conversation history
- Compress older turns (beyond last 2) into narrative
- Track deterministic facts (entities created, deleted, etc.)

**What Summarize SHOULD NOT do:**
- Lose proposal details ("Proposed a plan" ❌)
- Summarize entity state (that's registry's job)
- Touch last 2 turns (they stay verbatim)

### What Needs Audit

| Current Behavior | Correct Behavior |
|------------------|------------------|
| Proposals summarized to "Proposed a plan" | Keep full proposal text |
| Entity lifecycle managed by Summarize | Managed by CRUD layer/registry |
| Multiple LLM calls for summaries | Deterministic where possible |

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

### Injection Sources

```
Act Prompt = Base Instructions
           + Step Type Instructions (read/write/analyze/generate)
           + Subdomain Schema
           + Working Set (entities available)
           + Prior Step Results
           + Contextual Examples
```

### What Needs Audit

| Component | Location | Status |
|-----------|----------|--------|
| Step type prompts | `prompts/act/*.md` | ✅ Structured |
| Subdomain schemas | `tools/schema.py` | ✅ Dynamic |
| Entity injection | `working_set.py` | ❓ Simplify |
| Example injection | `prompts/examples.py` | ❓ Audit coverage |

---

## 5. State vs Context

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
| Act | Schema, registry | Prior steps, working set | DB via CRUD | Step results |
| Reply | Execution results | - | - | Final response |
| Summarize | Execution facts | - | Conversation history | - |

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

## Audit Checklist

### Entity Management ✅ COMPLETE
- [x] Audit `entities.py` → **DELETED**
- [x] Audit `entity_context.py` → **DELETED**
- [x] Audit `working_set.py` → **DELETED**
- [x] Remove `id_mapper.py` → **DELETED**
- [x] Remove `session_state.py` → **DELETED**
- [x] Remove redundant state fields → **DONE** (`turn_entities`, `entity_registry`, `entity_context`, `working_set`, `id_mapper`, `session_id_registry` → `id_registry`)

### ID Management ✅ COMPLETE
- [x] Verify all CRUD operations use registry → **DONE** (Act, Understand, Think use `id_registry`)
- [x] Verify no UUIDs leak to prompts → **DONE** (All nodes use `format_for_*_prompt()` methods)
- [x] Verify action tracking works for all operations → **DONE** (`ref_actions`, `ref_turn_created`, `ref_turn_last_ref`)

### Summarization ✅ COMPLETE
- [x] Audit what Summarize actually does → **Simplified to conversation history only**
- [x] Remove entity tracking from Summarize → **DONE** (removed all entity logic)
- [x] Ensure proposals kept verbatim → **DONE** (prior fix)
- [x] Ensure last 2 turns kept verbatim → **DONE** (prior implementation)

### Prompt Injection ✅ COMPLETE
- [x] Simplify entity injection to use registry → **DONE** (all functions use `SessionIdRegistry`)
- [x] Remove deprecated type hints → **DONE**

### State vs Context ✅ COMPLETE
- [x] Single source of truth: `id_registry` → **DONE**
- [x] All deprecated fields removed from `AlfredState` → **DONE**

### Cross-Turn Persistence ✅ COMPLETE (CRITICAL - previously missed!)
- [x] `workflow.py`: Load `id_registry` from conversation at turn start → **DONE** (both `run_alfred` and `run_alfred_streaming`)
- [x] `summarize.py`: Save `id_registry` to conversation at turn end → **DONE**
- [x] Web app (`app.py`): Session stores updated conversation with `id_registry` → **VERIFIED** (uses `session["conversation"]`)
- [x] CLI (`main.py`): Conversation dict passed between turns → **VERIFIED** (uses `run_alfred` return value)
- [x] Test cross-turn flow: generate → confirm → save → ❓ **NEEDS MANUAL TEST**

### Files Scanned (post-consolidation audit)
| File | Status | Notes |
|------|--------|-------|
| `workflow.py` | ✅ Fixed | Added `id_registry` to initial_state |
| `summarize.py` | ✅ Fixed | Added `id_registry` to updated_conversation |
| `web/app.py` | ✅ OK | Uses conversation dict correctly |
| `main.py` | ✅ OK | Uses conversation dict correctly |
| `memory/conversation.py` | ✅ OK | `initialize_conversation()` returns empty dict, `id_registry: None` handled |
| `nodes/act.py` | ✅ OK | Uses `state.get("id_registry")` with fallback |
| `nodes/think.py` | ✅ OK | Uses `state.get("id_registry")` |
| `nodes/understand.py` | ✅ OK | Uses `state.get("id_registry")` |
| `tools/crud.py` | ✅ Fixed | Added NULL byte sanitization for LLM Unicode corruption |

### Future Optimization: Direct Artifact Injection
Currently, Act sees full generated content in prompt and re-types it (for visibility/debugging).

**Future state** (once generate→save flow is stable):
- Act outputs `{"use_artifact": "gen_recipe_1"}` instead of full JSON
- System injects content directly from `pending_artifacts`
- Benefits: No LLM corruption, faster, cheaper tokens
- Prerequisite: Confidence in cross-turn artifact persistence

### Critical Insight: Refs vs Content

**What SessionIdRegistry stores per entity:**
- ✅ Ref → UUID mapping
- ✅ Label (e.g., "chicken thighs")
- ✅ Type, last action, turn info
- ❌ Full entity content (e.g., quantity, location, all fields)

**Implication for Think's planning:**

| Step Type | What Act Needs | Refs Sufficient? |
|-----------|----------------|------------------|
| write/delete | Just the ref | ✅ Yes |
| generate | Labels + general context | ✅ Yes |
| analyze (compare/match) | **Full row data** | ❌ No — read first! |

This means Think must add a read step before any analyze step that needs to reason over data content, even if entities appear in "Entities in Context".

### Critical Insight: Dashboard ≠ Context

**Dashboard** shows what exists in the database (e.g., "1 saved recipe").
**Entities in Context** shows what has refs registered in SessionIdRegistry.

If an entity appears in Dashboard but NOT in "Entities in Context":
- Think cannot use a ref for it (e.g., `recipe_1` doesn't exist)
- Think must search by NAME, not by ref
- Act will fail if given an unregistered ref (query returns 0 results)

This happens when entities were created in a prior session, or the registry wasn't loaded properly.

---

## Next Steps

1. **Complete this audit** - fill in the ❓ sections
2. **Remove deprecated code** - `id_mapper.py`, redundant state fields
3. **Simplify entity display** - single source from registry
4. **Fix summarization** - deterministic where possible
5. **Document the final architecture** - update this doc

---

*Last updated: 2026-01-08*
