# Alfred V3 Architecture Design

**Document Type:** Architecture Design  
**Created:** December 31, 2024  
**Last Updated:** January 1, 2025  
**Status:** MVP Specification

---

## Overview

This document describes the V3 architecture for Alfred, addressing fundamental limitations discovered in V2:

1. **Entity lifecycle is broken** - No mechanism to reject, supersede, or age-out entities
2. **Context accumulates noise** - Stale data pollutes prompts as conversation grows
3. **No complexity adaptation** - Simple requests get same overhead as complex ones
4. **Prompts are one-size-fits-all** - Same Act prompt for reads, writes, analysis, generation

V3 introduces:
- **Entity Lifecycle State Machine** - 3-state model (pending/active/inactive) with clear ownership
- **Understand Layer** - Intent detection and entity state updates before planning
- **Group-Based Parallelization** - Think outputs step groups; same group = can run in parallel
- **Step-Type-Specific Prompts** - Different Act prompts for read/analyze/generate/write
- **Mode System** - Complexity adapts to request type (Quick/Cook/Plan/Create)

---

## Table of Contents

1. [Entity Lifecycle Framework](#1-entity-lifecycle-framework)
2. [Layered Architecture](#2-layered-architecture)
3. [Step Type Taxonomy](#3-step-type-taxonomy)
4. [Mode System](#4-mode-system)
5. [Clarification Loops](#5-clarification-loops)
6. [Prompt Architecture](#6-prompt-architecture)
7. [Node Contracts](#7-node-contracts)
8. [Summarization Architecture](#8-summarization-architecture)
9. [Context Management](#9-context-management)
10. [Multi-Domain Principles](#10-multi-domain-principles)
11. [Migration Path](#11-migration-path)

---

## 1. Entity Lifecycle Framework

### The Problem

In V2, entities only accumulate:
```
Step Result → Extract IDs → Append to active_entities → Forever
```

When a user says "no salads", the salad recipe remains in `active_entities`, polluting every subsequent prompt.

### Entity States (Simplified)

After analysis: `superseded`, `rejected`, and `stale` all mean "not in play anymore." 
If we don't track *what* superseded *what*, the distinction adds complexity without value.

**Simplified 3-state model:**

```
┌─────────────────────────────────────────────────────────────────┐
│                     ENTITY STATE MACHINE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│    ┌──────────┐         ┌──────────┐         ┌──────────┐       │
│    │ PENDING  │────────▶│  ACTIVE  │────────▶│ INACTIVE │       │
│    └──────────┘  user   └──────────┘  user   └──────────┘       │
│         │       confirms      │      rejects       │            │
│         │                     │      or TTL        │            │
│         │                     │      expires       │            │
│         └─────────────────────┘                    │            │
│           (no response = implicit confirm          │            │
│            in Quick/Cook mode)                     │            │
│                                                    │            │
│                                                    ▼            │
│                                            ┌─────────────┐      │
│                                            │   GARBAGE   │      │
│                                            │  COLLECTED  │      │
│                                            └─────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

| State | Meaning | In Context? | Examples |
|-------|---------|-------------|----------|
| `pending` | Generated, awaiting confirmation | Yes (marked as pending) | Proposed recipe, suggested plan |
| `active` | User confirmed or working with | Yes | Saved recipe, confirmed meal plan |
| `inactive` | No longer relevant | No | Rejected, replaced, stale (5+ turns) |

**Why this is simpler:**
- No need to track "superseded by what"
- Rejected/stale/superseded all become `inactive`
- `inactive` entities are garbage collected after 2 turns
- If user wants an "inactive" entity back, they reference it explicitly → becomes `active`

### State Transitions

| Transition | Trigger | Detection Method |
|------------|---------|------------------|
| `pending` → `active` | User confirms | "yes", "that one", "looks good", or implicit (Quick mode) |
| `pending` → `inactive` | User rejects | "no", "not that", "something else" |
| `pending` → `active` | No response + Quick mode | Implicit confirm (low stakes) |
| `active` → `inactive` | User rejects | "not the salad", "no salads" |
| `active` → `inactive` | TTL expires | Not referenced for 5+ turns |
| `active` → `inactive` | Replaced | New entity of same type in same slot |
| `inactive` → `active` | User references | "actually, that first recipe" |
| `inactive` → GC | Cleanup | Inactive for 2+ turns |

**Key simplification:** All paths to "not in play" → `inactive`. No need to distinguish why.

### Entity Registry

```python
@dataclass
class Entity:
    id: str                    # UUID (or temp ID like "temp_recipe_1" for pending)
    type: str                  # "recipe", "meal_plan", "task" (not ingredients/shopping)
    label: str                 # Human-readable: "Butter Chicken"
    state: EntityState         # pending | active | inactive
    source: str                # "db_read" | "generate" | "user_input"
    turn_created: int          # When entity entered registry
    turn_last_ref: int         # Last turn entity was mentioned
```

**Note:** Ingredients and shopping items are NOT tracked as individual entities.
They're represented as counts/categories (see "Entity Representation by Type").

### Entity Tagging at Creation (Act's Responsibility)

Act tags entities when it creates them:

```python
# In Act, after db_create or generate:
new_entity = Entity(
    id=result["id"],
    type="recipe",
    label=result["name"],
    state="pending" if step_type == "generate" else "active",
    source="generate" if step_type == "generate" else "db_create",
    turn_created=current_turn,
    turn_last_ref=current_turn
)
state["turn_entities"].append(new_entity)
```

**Key insight:** Entities arrive in Understand pre-tagged. Understand only modifies states.

### What Understand Actually Sees

```python
class UnderstandInput:
    user_message: str
    
    # Pre-tagged entities (from previous turns + current Act)
    active_entities: list[EntityRef]      # ID + label + type (no full data)
    pending_entities: list[EntityRef]     # Awaiting confirmation
    
    # Counts for list types (not enumerated)
    entity_counts: dict[str, int]         # {"inventory": 47, "shopping": 23}
    
    # Recent conversation (2-3 turns)
    recent_turns: list[TurnSummary]
    
    # Mode context
    current_mode: Mode
    pending_clarification: PendingClarification | None
```

**Understand's actual job (light):**
1. Parse user message for intent
2. Detect confirmation/rejection signals → update entity states
3. Resolve "that recipe" → specific entity ID
4. Check if clarification needed

**NOT Understand's job:**
- Extract entities from results (Act did this)
- Track full entity data (just refs)
- Enumerate long lists (use counts)

### Entity Scoping

| Scope | Lifetime | Example |
|-------|----------|---------|
| **Turn** | Single request-response | IDs created during Act steps |
| **Session** | Current conversation | Active entities, proposed content |
| **Persistent** | Across sessions | User preferences, saved recipes |

### Signal Detection (Understand's Job)

Understand detects user signals and updates entity states:

| Signal Pattern | Entity Action |
|----------------|---------------|
| "not X", "no X", "don't want X" | Mark X as `inactive` |
| "actually Y instead" | Mark old as `inactive`, Y as `active` |
| "yes", "that one", "looks good" | Mark `pending` as `active` |
| "the other one", "different" | Clarify which entity |
| (no response in Quick mode) | Implicit confirm → `pending` becomes `active` |

**Key insight:** Understand's cognitive load is LOW because:
1. Entities arrive pre-tagged (Act did the work)
2. Only 3 states to manage (pending/active/inactive)
3. Long lists are counts, not enumerated
4. Mode from UI, not inferred

### Garbage Collection

Run at end of each turn:
1. Entities in `inactive` state for 2+ turns → remove from registry
2. Entities not referenced in 5+ turns → transition to `inactive`

### Entity Representation by Type

Different entity types need different context strategies:

| Entity Type | In Context | Representation |
|-------------|------------|----------------|
| **Recipes** | Last 5 referenced | ID + name + key tags |
| **Meal Plans** | Current week only | ID + date + recipe ref |
| **Tasks** | Last 10 + incomplete | ID + description |
| **Ingredients** | Count only | "47 ingredients in inventory" |
| **Shopping Items** | Count + categories | "23 items (Produce: 8, Dairy: 5, ...)" |

**Key insight:** Don't enumerate lists that are too long to be useful. Use counts and categories.

```python
class EntityContext:
    # For enumerable entities (recipes, tasks, meal plans)
    referenced: list[EntityRef]    # Explicitly mentioned this session
    recent: list[EntityRef]        # Last N created/modified
    
    # For list entities (ingredients, shopping)
    counts: dict[str, int]         # {"inventory": 47, "shopping": 23}
    categories: dict[str, dict]    # {"shopping": {"Produce": 8, "Dairy": 5}}
```

---

## 2. Layered Architecture

### V2 Flow (Current)

```
User Message → Router → Think → Act (loop) → Reply → Summarize
```

Problems:
- Think plans everything upfront without knowing entity states
- No intent resolution before planning
- Same Act prompt for all step types
- Entities accumulate without cleanup

### V3 Flow

```
User Message
    │
    ▼
┌─────────────┐
│ UNDERSTAND  │  ← Entity state updates, signal detection
└─────────────┘
    │
    ├─── Clarify needed? ───▶ Reply (ask user) ───▶ [wait for response]
    │
    ▼
┌─────────────┐
│    THINK    │  ← Plan steps with groups
└─────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GROUP-BASED EXECUTION                         │
│                                                                  │
│  Group 0: [step, step, step]  ← Run in parallel                 │
│      │                                                           │
│      ▼                                                           │
│  Group 1: [step, step]        ← Run in parallel (needs Group 0) │
│      │                                                           │
│      ▼                                                           │
│  Group N: [step]              ← Sequential (needs Group N-1)    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────┐
│    REPLY    │  ← Format response for user
└─────────────┘
    │
    ▼
┌─────────────┐
│  SUMMARIZE  │  ← Garbage collect entities, compress context
└─────────────┘
```

### Group-Based Parallelization

Think outputs steps with a `group` field. Steps in the same group have no dependencies on each other and can run in parallel.

**Example 1:** "What can I make with what I have?"
```
Group 0: [read recipes, read inventory, read preferences]  ← parallel
Group 1: [analyze: match recipes to inventory]             ← needs Group 0
```

**Example 2:** "Add eggs, then suggest a recipe"
```
Group 0: [write: add eggs to inventory]    ← write FIRST
Group 1: [read: get updated inventory]     ← needs Group 0
Group 2: [generate: suggest recipe]        ← needs Group 1
```

**Example 3:** "Save that recipe, add missing ingredients to shopping"
```
Group 0: [write: save recipe]
Group 1: [read: recipe ingredients, read: inventory]  ← parallel
Group 2: [analyze: find missing]
Group 3: [write: add to shopping list]
```

### Layer Specifications

#### Understand Layer

| Aspect | Specification |
|--------|---------------|
| **Purpose** | Detect user signals, update entity states |
| **Executor** | LLM call |
| **Input** | User message, active entities (refs), pending entities (refs) |
| **Output** | Entity state updates, clarification flag |
| **Token Budget** | ~1.5K input, ~300 output |

**Key insight:** Understand does NOT plan. It only:
1. Detects confirmation/rejection signals
2. Updates entity states (pending→active, active→inactive)
3. Resolves "that recipe" → specific entity ID
4. Flags if clarification needed

#### Think Layer

| Aspect | Specification |
|--------|---------------|
| **Purpose** | Plan steps with group assignments |
| **Executor** | LLM call |
| **Input** | User message, entity counts, user profile (compact) |
| **Output** | Steps with group field |
| **Token Budget** | ~2K input, ~800 output |

**Key change from V2:** Outputs `group` field for parallelization.

#### Act Layer

| Aspect | Specification |
|--------|---------------|
| **Purpose** | Execute a single step |
| **Executor** | LLM call with step_type-specific prompt |
| **Input** | Step, schema (if read/write), previous group results |
| **Output** | Step result, new entities (tagged) |
| **Token Budget** | Varies by step_type |

**Key change from V2:** Prompt varies by step_type (see Section 6).

---

## 3. Step Type Taxonomy

### V2 Step Types (Current)

| Type | Executor | Problems |
|------|----------|----------|
| `crud` | LLM → DB | Same prompt for reads and complex writes |
| `analyze` | LLM only | Overloaded - does judgment AND computation |
| `generate` | LLM only | Fine |

### V3 Step Types

Simplified to 4 types with step_type-specific Act prompts:

| Type | Purpose | Schema Injected? | Prev Results? | Example |
|------|---------|------------------|---------------|---------|
| `read` | Query database | Yes | No | "Get recipes where cuisine=indian" |
| `analyze` | Reason over data | No | Yes (full) | "Which recipes match user preferences?" |
| `generate` | Create new content | No | Yes (summary) | "Generate a weeknight pasta recipe" |
| `write` | Create/update/delete | Yes | Yes (IDs only) | "Save recipe to database" |

### Step Type Decision Tree

```
What is the step doing?
│
├── Reading from database?
│   └── `read` (inject schema, filter syntax)
│
├── Writing to database?
│   └── `write` (inject schema, FK handling, entity tagging)
│
├── Creating new content?
│   └── `generate` (inject user profile, creative guidance)
│
└── Reasoning over existing data?
    └── `analyze` (inject previous results prominently)
```

### Why This Works

The key insight: **LLMs aren't bad at computation when given focused context.**

V2 failed because:
- Analyze steps saw stale entities polluting context
- Same prompt for all operations meant irrelevant examples
- No filtering of previous results by relevance

V3 fixes this by:
- Filtering entities by state (no inactive entities in prompts)
- Step_type-specific prompts (only relevant sections)
- Group-based execution (previous GROUP results, not all results)

---

## 4. Mode System

### Why Modes?

Not every request needs the same overhead:
- "Add eggs to shopping" → 1 step, no planning needed
- "Plan my meals for the week" → 5+ steps, proposals, confirmations

Modes let the system adapt complexity to the request.

### Mode Definitions

| Mode | Trigger | Think Depth | Typical Steps | Confirmation |
|------|---------|-------------|---------------|--------------|
| **Quick** | Simple CRUD keywords | Skip or minimal | 1-2 | None |
| **Cook** | Active cooking signals | Light | 2-4 | Light |
| **Plan** | Planning signals | Full iterative | 4-8+ | Proposal + confirm |
| **Explore** | Discovery signals | Medium | 2-5 | Optional |

### Mode Selection: UI-First, LLM-Assisted

**Primary:** User selects mode in UI (explicit, reliable)
**Secondary:** LLM can suggest mode switch if behavior doesn't match

| Mode | UI Selection | When to Use |
|------|--------------|-------------|
| **Quick** | Default / "Quick" button | Most interactions, low-stakes CRUD |
| **Cook** | "Cooking" button | Active cooking session (= Quick + recipe focus) |
| **Plan** | "Plan" button | Multi-step workflows, meal planning |
| **Create** | "Create" button | Recipe generation, content creation |

### Mode Detection Logic

```
1. Check UI mode selection (explicit) → USE THAT
2. If no selection, check user profile default → USE THAT
3. Only if ambiguous: LLM classifies intent (NOT keyword matching)
4. LLM can SUGGEST mode switch, user confirms
```

**Key insight:** Don't make LLM guess mode. Let UI carry that burden.

```python
class ModeContext(BaseModel):
    selected_mode: Mode | None     # From UI
    profile_default: Mode          # From user preferences
    llm_suggestion: Mode | None    # Only if different from above
    suggestion_reason: str | None  # "This looks like a planning task"
```

### Mode Effects on Pipeline

| Mode | Understand | Think | Execute | Confirm |
|------|------------|-------|---------|---------|
| Quick | Minimal | Skip | 1-2 steps | None |
| Cook | Light | Light | 2-4 steps | Light |
| Plan | Full | Full | 4-8 steps | Proposal |
| Create | Full | Full | 2-4 steps | Optional |

### Mode Switching

LLM can **suggest** mode switch (not auto-switch):

```
User: "Add milk to my shopping list"
Mode: Plan (current from UI)

System: Executes in Plan mode (user's choice respected)
        OR
        Quietly executes quickly (Plan mode allows simple ops)
        
Note: Don't fight the user's mode selection.
```

**Safe auto-behaviors:**
- Plan mode can still do simple ops quickly (don't over-engineer)
- Create mode implies Plan behavior for complex generation
- Cook mode = Quick + recipe context focus

### Profile-Aided Cognitive Load

The user profile reduces both clarification AND reasoning load:

```python
class SubdomainProfile(BaseModel):
    # Meal Planning
    cooking_frequency: str       # "weekends_only", "3x_week", "daily"
    batch_cooking: bool          # Do they meal prep?
    planning_horizon: str        # "week", "few_days", "day_of"
    
    # Recipes
    recipe_storage: str          # "full", "links_only", "mixed"
    recipe_generation: str       # "detailed", "quick", "ingredients_only"
    
    # Tasks
    task_granularity: str        # "detailed", "reminders", "minimal"
    
    # Shopping
    list_organization: str       # "by_aisle", "by_category", "unorganized"
```

**How profile reduces calls:**

| Without Profile | With Profile |
|-----------------|--------------|
| "Do you meal prep?" | Already know from onboarding |
| "How detailed should tasks be?" | Profile says "reminders" |
| "Full recipe or quick version?" | Profile says "detailed" |
| Clarify cooking schedule | Profile has cooking_frequency |

**Key insight:** Good onboarding = fewer runtime LLM calls = faster responses

---

## 5. Clarification Loops

### Two Types of Clarification

| Source | Clarifies About | Example | Trigger |
|--------|-----------------|---------|---------|
| **Understand** | What are you asking? | "Which recipe?" | Ambiguous reference |
| **Think** | How should I approach? | "Plan 5 dinners?" | Complex plan proposal |

Both funnel through a **unified clarification break** before returning to the user.

### When to Clarify

| Signal | Action |
|--------|--------|
| Profile is empty | Ask about preferences (but leverage onboarding!) |
| Ambiguous entity reference | "That one" with multiple candidates |
| Conflicting constraints | "Vegan butter chicken" |
| Critical info gap | Dates for meal plan without range |
| Complex plan (Plan mode) | Propose plan for confirmation |

### When NOT to Clarify

| Signal | Action | Why |
|--------|--------|-----|
| Profile has data | Use profile data, state assumption | Leverage onboarding |
| Request is specific | Execute directly | Trust the user |
| Can infer safely | State assumption, proceed | Low stakes |
| Quick/Cook mode | Execute, inform after | Speed matters |

### Profile Reduces Clarification

Subdomain-specific onboarding questions reduce runtime clarification:

| Subdomain | Onboarding Question | Reduces Clarification About |
|-----------|--------------------|-----------------------------|
| Meal Planning | "How many days do you cook?" | Batch size questions |
| Meal Planning | "Weekend or weekday cooking?" | Schedule assumptions |
| Recipes | "Save full recipes or just links?" | Storage format |
| Tasks | "Detailed tasks or quick reminders?" | Task granularity |
| Shopping | "Organize by aisle or category?" | List formatting |

**Key insight:** Ask once in onboarding, use forever. Don't re-ask at runtime.

### Clarification Flow

```
┌───────────────────────────────────────────────────────────────┐
│                     CLARIFICATION BREAK                        │
│                                                                │
│   Understand says: "Ambiguous entity"                         │
│        OR                                                      │
│   Think says: "Complex plan, propose first"                   │
│                                                                │
│              ▼                                                 │
│   ┌─────────────────────┐                                     │
│   │  Format question(s) │                                     │
│   │  Return to user     │                                     │
│   └─────────────────────┘                                     │
│              │                                                 │
│              ▼                                                 │
│   ┌─────────────────────┐                                     │
│   │   User responds     │                                     │
│   └─────────────────────┘                                     │
│              │                                                 │
│              ▼                                                 │
│   ┌─────────────────────┐                                     │
│   │ Understand parses   │  ← Always through Understand        │
│   │ response + context  │                                     │
│   └─────────────────────┘                                     │
│              │                                                 │
│              ▼                                                 │
│   Resume from where clarification was triggered               │
│   (Understand → Think, or Think → Execute)                    │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

### Clarification vs Proposal Decision

```
                    ┌──────────────────────┐
                    │  Do I have enough    │
                    │  context to act?     │
                    └──────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
        ┌─────────┐                     ┌───────────┐
        │   NO    │                     │    YES    │
        └─────────┘                     └───────────┘
              │                               │
              ▼                               ▼
    ┌──────────────────┐           ┌──────────────────┐
    │  Is the missing  │           │   Is mode Plan   │
    │  info critical?  │           │   or Create?     │
    └──────────────────┘           └──────────────────┘
              │                               │
      ┌───────┴───────┐               ┌───────┴───────┐
      ▼               ▼               ▼               ▼
  ┌───────┐       ┌───────┐       ┌───────┐       ┌───────┐
  │  YES  │       │  NO   │       │  YES  │       │  NO   │
  └───────┘       └───────┘       └───────┘       └───────┘
      │               │               │               │
      ▼               ▼               ▼               ▼
  CLARIFY         EXECUTE         PROPOSE        EXECUTE
  (ask user)   (state assumption) (confirm plan) (just do it)
```

### Threading Context

Clarification context persists across the user response:

```python
class PendingClarification(BaseModel):
    source: Literal["understand", "think"]  # Who triggered it
    questions: list[str]
    original_intent: str
    partial_plan: list[Step] | None  # If Think triggered
    partial_entities: list[Entity]   # What we know so far
    turn_asked: int
```

When user responds:
1. Understand layer sees `pending_clarification`
2. Interprets response in context of questions and source
3. If source was Understand → resume to Think
4. If source was Think → resume to Execute with confirmed plan

---

## 6. Prompt Architecture

### The Problem

V2 uses one-size-fits-all prompts:
- Same Act prompt for simple reads and complex generation
- Same schema injection whether needed or not
- Same context injection regardless of step type

### Step-Type-Specific Prompt Injection

Each step_type gets a tailored prompt built by `injection.py`:

```python
# src/alfred/prompts/injection.py

def build_act_prompt(
    step: ThinkStep,
    mode: Mode,
    entities: list[Entity],
    prev_group_results: list[dict]
) -> str:
    """Assemble Act prompt based on step_type."""
    
    sections = []
    
    # Core context (always)
    sections.append(build_step_context(step))
    
    # Step-type-specific sections
    if step.step_type == "read":
        sections.append(build_read_sections(step))
    elif step.step_type == "analyze":
        sections.append(build_analyze_sections(prev_group_results))
    elif step.step_type == "generate":
        sections.append(build_generate_sections(step, mode))
    elif step.step_type == "write":
        sections.append(build_write_sections(step, entities))
    
    return "\n\n".join(sections)
```

### What Each Step Type Gets

#### READ Steps

| Section | Content | Why |
|---------|---------|-----|
| Schema | Table schema for queried subdomain | Know what to query |
| Filter Syntax | Supabase filter examples | Correct syntax |
| Entity IDs | Referenced entity IDs | Join on known IDs |

**NOT injected:**
- Previous results (not needed for reads)
- Generation guidelines (not generating)
- Full entity data (just IDs)

```python
def build_read_sections(step: ThinkStep) -> str:
    return f"""
## Database Schema
{get_schema_for_subdomain(step.subdomain)}

## Query Syntax
{get_filter_examples()}

## Referenced Entities
{format_entity_ids(step.referenced_entities)}
"""
```

#### ANALYZE Steps

| Section | Content | Why |
|---------|---------|-----|
| Previous Results | Full results from prior group | Data to analyze |
| User Preferences | Relevant constraints | Filter criteria |
| Output Format | Expected analysis structure | Consistent output |

**NOT injected:**
- Schema (not querying DB)
- Generation guidelines (not generating)
- Write examples (not writing)

```python
def build_analyze_sections(prev_group_results: list[dict]) -> str:
    return f"""
## Data to Analyze
{format_results_prominently(prev_group_results)}

## CRITICAL
Only analyze the data above. If no data, report "No data to analyze."
Do NOT invent data. Do NOT use entities as data sources.

## Output Format
{{
    "analysis": "...",
    "matches": [...],
    "reasoning": "..."
}}
"""
```

#### GENERATE Steps

| Section | Content | Why |
|---------|---------|-----|
| User Profile | Preferences, restrictions | Personalization |
| Prior Context | Summary of previous results | Grounding |
| Creative Guidance | Mode-specific verbosity | Style |
| Entity Tagging | How to ID new content | Tracking |

**NOT injected:**
- Schema (not querying)
- Full previous results (just summary)

```python
def build_generate_sections(step: ThinkStep, mode: Mode) -> str:
    verbosity = get_verbosity_for_mode(mode)
    return f"""
## User Preferences
{format_user_preferences(step.subdomain)}

## Prior Context
{summarize_prior_results(step.prior_group_summary)}

## Generation Guidelines
- Verbosity: {verbosity}
- Style: {get_style_guidance(mode)}

## Entity Tagging
New content MUST include: temp_id, type, label
Format: {{"temp_id": "temp_recipe_1", "type": "recipe", "label": "Quick Pasta"}}
"""
```

#### WRITE Steps

| Section | Content | Why |
|---------|---------|-----|
| Schema | Table schema with required fields | Correct inserts |
| FK Handling | Foreign key requirements | Valid relationships |
| Entity IDs | IDs from prior steps | Link entities |
| Entity Tagging | How to tag new records | Tracking |

**NOT injected:**
- Full previous results (just IDs)
- Generation guidelines (not generating)

```python
def build_write_sections(step: ThinkStep, entities: list[Entity]) -> str:
    return f"""
## Database Schema
{get_schema_for_subdomain(step.subdomain)}

## Entity IDs from Prior Steps
{format_entity_ids_for_write(entities)}

## Entity Tagging on Write
When creating records, tag them:
- state: "pending" (awaiting user confirmation)
- temp_id: use if no DB ID yet
- source: "generate" or "user_input"
"""
```

### Mode-Aware Prompt Variations

| Mode | Profile Detail | Examples | Verbosity |
|------|---------------|----------|-----------|
| Quick | Minimal | None | Terse |
| Cook | Compact | Light | Focused |
| Plan | Full | Full | Detailed |
| Create | Full (creative) | None | Rich |

```python
def get_verbosity_for_mode(mode: Mode) -> str:
    return {
        Mode.QUICK: "terse",
        Mode.COOK: "focused",
        Mode.PLAN: "detailed",
        Mode.CREATE: "rich"
    }[mode]
```

### Prompt File Organization

```
prompts/
├── understand.md          # Intent detection, entity resolution
├── think.md               # Step planning with groups
├── act/
│   ├── base.md            # Common Act instructions
│   ├── read.md            # Read-specific sections
│   ├── analyze.md         # Analyze-specific sections  
│   ├── generate.md        # Generate-specific sections
│   └── write.md           # Write-specific sections
├── reply.md               # Response formatting
└── summarize.md           # Context compression
```

---

## 7. Node Contracts

This section defines the exact input/output contracts for each node.

### Understand Node

**Input:**
```python
class UnderstandInput:
    user_message: str
    active_entities: list[EntityRef]   # Just id, type, label
    pending_entities: list[EntityRef]  # Awaiting confirmation
    recent_turns: list[TurnSummary]    # Last 2 turns
    pending_clarification: PendingClarification | None
```

**Output:**
```python
class UnderstandOutput(BaseModel):
    # Entity state updates
    entity_updates: list[dict]     # [{"id": "x", "new_state": "active"}]
    referenced_entities: list[str] # Entity IDs user is referring to
    
    # Clarification
    needs_clarification: bool
    clarification_questions: list[str] | None
    clarification_reason: str | None  # "ambiguous_reference", "missing_info"
    
    # Pass-through
    processed_message: str  # User message with resolved references
```

**Contract:**
- Understand ONLY updates entity states and detects clarification needs
- Does NOT plan steps
- Does NOT execute anything
- If `needs_clarification=True`, workflow routes to Reply (not Think)

### Think Node

**Input:**
```python
class ThinkInput:
    user_message: str
    referenced_entities: list[str]  # From Understand
    entity_counts: dict[str, int]   # {"recipes": 45, "meal_plans": 3}
    user_profile: UserProfileCompact
    mode: Mode
```

**Output:**
```python
class ThinkStep(BaseModel):
    description: str
    step_type: Literal["read", "analyze", "generate", "write"]
    subdomain: str
    group: int  # 0, 1, 2... Same group = parallel
    referenced_entities: list[str] | None  # Entities this step uses

class ThinkOutput(BaseModel):
    goal: str
    steps: list[ThinkStep]
    needs_proposal: bool  # True if should show user before executing
    proposal_message: str | None
```

**Contract:**
- Steps in same `group` can run in parallel
- Groups execute in order: 0 → 1 → 2
- If `needs_proposal=True`, workflow routes to Reply (not Act)
- User confirmation continues to Act

### Act Node

**Input:**
```python
class ActInput:
    step: ThinkStep
    mode: Mode
    entities: list[Entity]           # Active + pending entities
    prev_group_results: list[dict]   # Results from prior group
    schema: str | None               # If step_type is read or write
```

**Output:**
```python
class ActOutput(BaseModel):
    result: dict                     # Step-specific result
    new_entities: list[Entity]       # Entities created (tagged)
    errors: list[str] | None

class Entity(BaseModel):
    id: str                # UUID or temp_id
    type: str              # "recipe", "meal_plan", etc.
    label: str             # Human-readable
    state: EntityState     # pending, active, inactive
    source: str            # "db_read", "generate", "user_input"
    turn_created: int
```

**Contract:**
- Act tags ALL new entities at creation
- state="pending" for generated content
- state="active" for user-provided or confirmed content
- Returns `new_entities` list for tracking

### Reply Node

**Input:**
```python
class ReplyInput:
    mode: Mode
    action: Literal["respond", "clarify", "propose"]
    
    # For "respond"
    execution_results: list[dict] | None
    entities_created: list[Entity] | None
    
    # For "clarify"
    clarification_questions: list[str] | None
    
    # For "propose"
    proposal_message: str | None
    proposed_steps: list[ThinkStep] | None
```

**Output:**
```python
class ReplyOutput(BaseModel):
    message: str
    pending_clarification: PendingClarification | None
    pending_proposal: PendingProposal | None
```

**Contract:**
- Formats response based on mode (Quick=terse, Plan=detailed)
- Sets `pending_clarification` if asking user for info
- Sets `pending_proposal` if proposing plan for confirmation

### Summarize Node

**Input:**
```python
class SummarizeInput:
    turn_entities: list[Entity]      # Entities from this turn
    execution_results: list[dict]    # Results from all steps
    conversation_so_far: list[Turn]  # For periodic compression
    current_turn: int
```

**Output:**
```python
class SummarizeOutput(BaseModel):
    updated_entities: list[Entity]   # After state transitions
    garbage_collected: list[str]     # Entity IDs removed
    conversation_summary: str | None # If compression happened
```

**Contract:**
- Merge `turn_entities` into entity registry
- Garbage collect: inactive > 2 turns, unreferenced > 5 turns
- Compress conversation every 3 turns

### Entity Handoff Flow

```
                  ┌─────────────┐
                  │  UNDERSTAND │
                  └──────┬──────┘
                         │ entity_updates, referenced_entities
                         ▼
                  ┌─────────────┐
                  │    THINK    │
                  └──────┬──────┘
                         │ steps with referenced_entities per step
                         ▼
           ┌─────────────────────────────┐
           │          ACT (per step)     │
           │  Input: prev_group_results  │
           │  Output: new_entities       │
           └──────────────┬──────────────┘
                          │ all new_entities from turn
                          ▼
                  ┌─────────────┐
                  │  SUMMARIZE  │
                  └──────┬──────┘
                         │ merge to registry, garbage collect
                         ▼
                  ┌─────────────┐
                  │   NEXT      │
                  │   TURN      │
                  └─────────────┘
```

---

## 8. Summarization Architecture

### LLM vs Deterministic

| What | Method | Why |
|------|--------|-----|
| Entity ID extraction | Code | Pattern matching, reliable |
| Record counts | Code | Deterministic |
| Step result summary | Code + Template | Structure is known |
| Conversation compression | LLM | Requires semantic judgment |
| Session context | LLM (periodic) | Narrative compression |
| Intent summary | LLM | Semantic understanding |
| Entity state detection | LLM | Natural language understanding |

### Hot / Warm / Cold Context

```
┌─────────────────────────────────────────────────────────────┐
│                     CONTEXT TEMPERATURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  HOT (always injected)                                       │
│  ├── Current turn entities (active state only)               │
│  ├── User profile summary (compact)                          │
│  ├── Last 2 conversation turns                               │
│  └── Current step context                                    │
│                                                              │
│  WARM (injected on demand)                                   │
│  ├── Session summary (compressed)                            │
│  ├── Last 5 turn entities                                    │
│  ├── Pending clarification context                           │
│  └── Recent step results (last 3)                            │
│                                                              │
│  COLD (requires explicit retrieval)                          │
│  ├── Full conversation history                               │
│  ├── Old step results                                        │
│  ├── Archived generated content                              │
│  └── Historical cooking logs                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Summarization Timing

| Event | What Gets Summarized | Method |
|-------|---------------------|--------|
| Step complete | Step result | Code (extract IDs, counts) |
| Turn complete | Turn entities → merge to session | Code |
| Turn complete | Conversation | LLM (if > 3 turns since last) |
| Entity state change | Entity registry | Code |
| Session end | Full session | LLM |

### Conversation Summarization

```python
class ConversationSummary(BaseModel):
    engagement_summary: str      # What we're helping with
    key_decisions: list[str]     # User confirmed/rejected
    active_constraints: list[str] # Current limitations
    next_likely_intent: str      # Predicted next request
```

Summarization prompt focuses on:
1. What user is trying to accomplish (goal)
2. What decisions have been made (constraints)
3. What entities are relevant (active, not rejected)
4. What's likely to come next (prediction for cache warming)

---

## 9. Context Management

### What Each Layer Sees

| Layer | Sees | Doesn't See |
|-------|------|-------------|
| **Understand** | User message, active entities (IDs + labels), recent 2 turns | Full history, step results, schema |
| **Think** | User message, entity counts by type, user profile (compact) | Full entity data, conversation history |
| **Act** | Step, relevant schema, previous group results, entities | Other subdomain schemas, old results |
| **Reply** | Execution summary, user context, active entities | Internal step details |
| **Summarize** | Full turn data, entity registry, conversation so far | (Everything - it's the compressor) |

### Token Budgeting

| Layer | Input Budget | Output Budget | Rationale |
|-------|--------------|---------------|-----------|
| Understand | 1.5K | 300 | Quick entity state detection |
| Think | 2K | 800 | Planning with groups |
| Act | 3K | 1K | Needs schema + results |
| Reply | 2K | 1K | Final formatting |
| Summarize | 3K | 500 | Compression task |

### Context Injection by Mode

| Context Component | Quick | Cook | Plan | Explore |
|-------------------|-------|------|------|---------|
| User profile | Minimal | Compact | Full | Compact |
| Active entities | Last 3 | Last 5 | All | Last 5 |
| Conversation | Current | Last 2 | Last 3 | Last 2 |
| Step results | N/A | Last 2 | Last 3 | Last 2 |
| Examples | None | Light | Full | Light |

---

## 10. Multi-Domain Principles

### Core Framework (Domain-Agnostic)

These components transfer to any domain:

| Component | Purpose | Domain-Agnostic? |
|-----------|---------|------------------|
| Entity Lifecycle | State machine for all entities | Yes |
| Understand Layer | Entity state management | Yes |
| Think Layer | Step planning with groups | Yes |
| Act Layer | Step execution | Yes |
| Mode System | Complexity adaptation | Yes (modes are domain-specific) |
| Context Management | Token budgeting | Yes |
| Prompt Injection | Step-type-specific prompts | Yes |

### Domain-Specific Components

| Component | Kitchen Domain | Future Domain X |
|-----------|----------------|-----------------|
| Schema | recipes, inventory, meal_plans | documents, contacts, projects |
| Entity Types | recipe, ingredient, meal_plan | document, contact, task |
| Subdomains | inventory, recipes, shopping | files, communications, calendar |
| Modes | Quick, Cook, Plan, Create | Quick, Focus, Plan, Create |
| Personas | Chef, Ops Manager, Planner | Writer, Coordinator, Analyst |
| Query Strategies | Cuisine→recipes | Project→team members |

### Pluggable Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CORE FRAMEWORK                           │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐    │
│  │ Entity        │  │ Layer         │  │ Context       │    │
│  │ Lifecycle     │  │ Orchestration │  │ Management    │    │
│  └───────────────┘  └───────────────┘  └───────────────┘    │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              DOMAIN ADAPTER INTERFACE                  │  │
│  │  - get_schema(subdomain) -> TableSchema               │  │
│  │  - get_entity_types() -> list[EntityType]             │  │
│  │  - get_modes() -> list[Mode]                          │  │
│  │  - get_personas() -> dict[subdomain, Persona]         │  │
│  │  - get_compute_functions() -> dict[name, Callable]    │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
    ┌───────────────┐               ┌───────────────┐
    │ KITCHEN       │               │ DOMAIN X      │
    │ ADAPTER       │               │ ADAPTER       │
    │               │               │               │
    │ - PantrySchema│               │ - XSchema     │
    │ - RecipeEntity│               │ - XEntity     │
    │ - CookMode    │               │ - XMode       │
    │ - ChefPersona │               │ - XPersona    │
    └───────────────┘               └───────────────┘
```

---

## 11. Migration Path

### Phase 1: Entity Lifecycle + State

**Goal:** Implement 3-state entity model with Act tagging

**Changes:**
1. Add `EntityState` enum (pending, active, inactive) and `Entity` dataclass
2. Create `EntityRegistry` class with state transitions
3. Update Act to tag new entities at creation with state + temp_id
4. Update Summarize for garbage collection
5. Update context injection to filter by entity state

**Success Criteria:**
- Generated content gets state="pending"
- User confirmation → state="active"
- Inactive entities don't appear in prompts
- Entities garbage collected after N turns

### Phase 2: Understand Layer

**Goal:** Add entity state management before Think

**Changes:**
1. Create `src/alfred/graph/nodes/understand.py`
2. Create `prompts/understand.md` with entity resolution focus
3. Implement entity state update detection (confirmation/rejection signals)
4. Wire into graph before Think
5. Implement clarification break if needed

**Success Criteria:**
- "Save that" → marks pending entity as active
- "No salads" → marks salad entities as inactive
- Ambiguous references → clarification break

### Phase 3: Think with Groups

**Goal:** Add group-based parallelization to Think output

**Changes:**
1. Update `ThinkStep` model with `group: int` field
2. Update `prompts/think.md` with group planning guidance
3. Implement group execution in workflow (parallel steps per group)
4. Update workflow to execute groups sequentially, steps in parallel

**Success Criteria:**
- Think outputs steps with group numbers
- Same group = can run in parallel
- Groups execute in order: 0 → 1 → 2

### Phase 4: Step-Type-Specific Act Prompts

**Goal:** Different prompts for read/analyze/generate/write

**Changes:**
1. Create `src/alfred/prompts/injection.py` for prompt assembly
2. Create `prompts/act/` directory with step-type-specific sections
3. Update Act node to use `build_act_prompt()` based on step_type
4. Inject only relevant schema/results per step type
5. Test each step type in isolation

**Success Criteria:**
- Read steps get schema, not previous results
- Analyze steps get previous results prominently
- Generate steps get user profile and creative guidance
- Write steps get schema and entity IDs

### Phase 5: Mode System

**Goal:** UI-driven complexity adaptation

**Changes:**
1. Add `Mode` enum (Quick, Cook, Plan, Create)
2. Add mode to CLI/API parameters
3. Update Think to adjust step depth by mode
4. Update prompt injection to vary by mode (verbosity, examples)
5. Update Reply for mode-appropriate formatting

**Success Criteria:**
- Quick mode: 1-2 steps, terse response
- Plan mode: full planning, detailed response
- Mode selection in UI, not LLM-inferred

---

## Appendix: Diagrams

### A. Complete V3 Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           USER MESSAGE                                    │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  UNDERSTAND (1 LLM call - outputs structured data)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Intent    │  │   Entity    │  │   Entity    │  │    Mode     │     │
│  │  Detection  │  │ Resolution  │  │   States    │  │  (from UI)  │     │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               │               ▼
            ┌───────────┐          │       ┌───────────────┐
            │ Ambiguous?│          │       │  Clear intent │
            │ → CLARIFY │          │       │    → THINK    │
            └───────────┘          │       └───────────────┘
                    │              │               │
                    ▼              │               ▼
            ┌───────────┐          │       ┌───────────────┐
            │   USER    │          │       │ Complex plan? │
            │  RESPONDS │          │       │  → PROPOSE    │
            └───────────┘          │       └───────────────┘
                    │              │               │
                    │              │               ▼
                    │              │       ┌───────────────┐
                    │              │       │     USER      │
                    │              │       │   CONFIRMS    │
                    │              │       └───────────────┘
                    │              │               │
                    └──────────────┴───────────────┘
                                   │
                    ◀──────────────┴───────────────▶
                    │  (all responses go through   │
                    │   Understand to parse)       │
                                   │
                                   ▼
                        ┌───────────────────┐
                        │  EXECUTE          │
                        │  (mode-dependent) │
                        │                   │
                        │  Quick: 1 step    │
                        │  Plan: loop+check │
                        └───────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  REPLY                                                                    │
│  Format execution results for user                                        │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SUMMARIZE (mostly code, LLM only for compression)                        │
│  Update entities, compress context, prepare for next turn                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**LLM Call Count by Mode:**

| Mode | Calls | Breakdown |
|------|-------|-----------|
| Quick | 2-3 | Understand (maybe skip) + Act + Reply |
| Cook | 3-4 | Understand + Act(1-2) + Reply |
| Plan | 4-7 | Understand + Think + Act(2-4) + Reply |
| Create | 4-6 | Understand + Think + Generate(1-2) + Reply |

**Optimization:** In Quick/Cook mode with UI mode selection, Understand can be skipped or minimized.

### B. Entity State Transitions (Simplified)

```
                         ┌─────────────┐
                         │  ACT STEP   │
                         │  creates    │
                         └─────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
        ┌─────────────┐                 ┌─────────────┐
        │   PENDING   │                 │   ACTIVE    │
        │ (generated) │                 │ (from DB)   │
        └─────────────┘                 └─────────────┘
               │                               │
       ┌───────┴───────┐                       │
       ▼               ▼                       │
  ┌─────────┐    ┌──────────┐                  │
  │ confirm │    │  reject  │                  │
  └─────────┘    └──────────┘                  │
       │               │                       │
       ▼               │                       │
┌─────────────┐        │                       │
│   ACTIVE    │◀───────┼───────────────────────┘
└─────────────┘        │               │
       │               │               │
       │ reject/       │               │ TTL (5 turns)
       │ replace       ▼               ▼
       │         ┌─────────────────────────┐
       └────────▶│       INACTIVE          │
                 └─────────────────────────┘
                               │
                               │ 2+ turns
                               ▼
                 ┌─────────────────────────┐
                 │    GARBAGE COLLECTED    │
                 └─────────────────────────┘
```

**3 states, clear transitions, no over-engineering.**

### C. Mode Decision Tree

```
                    ┌─────────────────────┐
                    │ Analyze user message │
                    └─────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ Simple CRUD?    │             │ Complex request?│
    │ (add/remove/    │             │ (plan/suggest/  │
    │  show/check)    │             │  help/organize) │
    └─────────────────┘             └─────────────────┘
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   QUICK MODE    │             │ Active cooking? │
    │                 │             │ (I'm making...) │
    └─────────────────┘             └─────────────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                    ┌─────────────────┐             ┌─────────────────┐
                    │   COOK MODE     │             │ Discovery/ideas?│
                    │                 │             │ (suggest/what   │
                    └─────────────────┘             │  can I/ideas)   │
                                                    └─────────────────┘
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                    ┌─────────────────┐             ┌─────────────────┐
                                    │  EXPLORE MODE   │             │   PLAN MODE     │
                                    │                 │             │                 │
                                    └─────────────────┘             └─────────────────┘
```


