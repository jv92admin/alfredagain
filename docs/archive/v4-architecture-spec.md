# Alfred V4 Architecture Specification

## Document Purpose

This document defines the architectural changes required to enforce proper **state vs context boundaries** across Alfred's multi-agent pipeline. It establishes:

1. The governing thesis
2. Clear boundary definitions per component
3. Analysis of complex flows that stress current architecture
4. Infrastructure changes to enforce boundaries
5. Migration path from V3

**Status**: Draft / Discussion  
**Date**: 2026-01-05

---

## Part 1: The Governing Thesis

### 1.1 Core Distinction

| Concept | Definition | Role | Enforcement |
|---------|------------|------|-------------|
| **Context** | Information that helps the model reason | Epistemic (informing) | Probabilistic |
| **State** | What must be true regardless of what model thinks | Normative (constraining) | Deterministic |

**The fundamental insight**: Any system that relies on context to enforce constraints is probabilistically correct at best.

### 1.2 Implications for Agent Architecture

1. **LLMs are interpreters, not authorities**
   - Can interpret language, propose actions, synthesize plans
   - Cannot guarantee consistency, enforce invariants, maintain canonical identity
   - Must never be final arbiters of system truth

2. **Determinism emerges from structure, not prompting**
   - Narrow the model's perceptual field
   - Stabilize representations (IDs, schemas, enums)
   - Compile fuzzy intent into enforceable rules
   - Validate outputs before committing

3. **Architectures fail when roles bleed**
   - Each phase needs narrow epistemic scope
   - Strict output contracts
   - Zero responsibility for enforcement outside its role

### 1.3 The Goal

> **Progressive reduction of ambiguity until only deterministic actions remain.**

Every component should reduce entropy for downstream components. If a component is "remembering" something, that thing is not yet state.

---

## Part 2: Current Architecture Diagnosis

### 2.1 Component Evaluation

| Component | Epistemic Load | State/Context Discipline | Drift Risk |
|-----------|---------------|-------------------------|------------|
| **Understand** | Low ✅ | Good ✅ | Low |
| **Think** | High ⚠️ | Weak ❌ | Medium |
| **Act** | Very High ❌ | Weak ❌ | High |
| **Reply** | Medium | Medium | Medium |
| **Summarize** | Low ✅ | Good ✅ | Low |

### 2.2 Where Boundaries Leak

#### Understand → Think
- `processed_message` is still narrative prose
- Think sometimes re-interprets the rewrite instead of original intent
- Entity mentions passed as text, not structured candidates

#### Think → Act
- Step descriptions are verbal ("save all 3 recipes")
- Batch counts are context, not state
- Prior step content summarized to "(use retrieve_step for details)"
- Act must re-interpret what "generated recipes" means

#### Act → State
- Act forced to normalize rich generated content to schema
- Semantic compression happens at execution layer
- No canonical "pre-normalized payload" exists

### 2.3 Observed Failures (from 20260105_020729 session)

#### Failure 1: Recipe Content Lost
```
Step 1 (Generate): Created 3 detailed recipes with 12+ ingredients each
Step 2 (Write): Saw "(use retrieve_step for details)"
Result: Act re-invented simplified recipes, lost detailed instructions
```

**Root cause**: Generated content was context (summarized), not state (preserved).

#### Failure 2: Partial Batch Completion
```
Step 3: "Save recipe_ingredients for 3 recipes"
Act: Created 12 ingredients for recipe 1, called step_complete
Result: 2/3 recipes had no ingredients
```

**Root cause**: Batch size was verbal context, not enforceable state.

#### Failure 3: Entity Duplication and Confusion
```
Entities shown to Act:
  - gen_recipe_1 — Honey Garlic... [pending]
  - a508000d... — Honey Garlic... [pending]  ← Same entity, two IDs
```

**Root cause**: Entity identity spread across multiple sections as context, not unified as state.

---

## Part 3: Complex Flows That Stress Architecture

### 3.1 Flow Type: Linked Table Operations

**Example**: Create recipe with ingredients

**Current failure mode**:
- Think plans: "Save recipes → Save ingredients with recipe IDs"
- Generate creates rich recipes with embedded ingredients
- Write step 1 saves recipes (simplified), gets IDs
- Write step 2 must map ingredients to IDs, but doesn't have:
  - The original ingredient lists
  - Clear mapping of which ingredients → which recipe

**What must become state**:
- Recipe-to-ingredient mapping (explicit, not inferred)
- Generated content in schema-ready form before Write step

### 3.2 Flow Type: Multi-Recipe Generation with Save

**Example**: "Create 3 fish recipes and save them"

**Current failure mode**:
- Generate creates 3 detailed recipes
- Write step saves recipes (but simplified)
- Write step for ingredients only handles first recipe
- Reply claims success, user sees incomplete data

**What must become state**:
- Batch manifest with explicit item count
- Per-item completion tracking
- Generated payloads preserved until committed

### 3.3 Flow Type: Multi-Turn Context Preservation

**Example**: 
```
Turn 1: "I want fish recipes for the air fryer"
Turn 2: "Use cod, serve with rice"
Turn 3: "Make 3 variations"
Turn 4: "Save all 3"
```

**Current failure mode**:
- Context accumulates as conversation summaries
- By Turn 4, specific requirements are compressed prose
- Act must reconstruct intent from narrative history

**What must become state**:
- Accumulated constraints (compiled, not narrative)
- Session intent (structured, not summarized)
- Referenced entities (canonical IDs, not descriptions)

### 3.4 Flow Type: Ingredient Category Search

**Example**: "Show me fish recipes"

**Current failure mode**:
- "Fish" searched literally in recipe names
- Recipes with "cod" or "salmon" as ingredients not found
- Act tries to expand keywords but inconsistently

**What must become state**:
- Ingredient category mappings (fish → [cod, salmon, tilapia, ...])
- Search intent type (category vs literal)
- Expansion rules (deterministic, not LLM-interpreted)

### 3.5 Flow Type: Highly Ambiguous Single-Turn

**Example**: "What can I make?"

**Current failure mode**:
- Understand passes through with minimal processing
- Think makes assumptions (recipes? with inventory? quick?)
- Act executes a guess
- User gets something, but not necessarily what they wanted

**What should become state**:
- Ambiguity classification (under-specified intent)
- Default assumptions (explicit, not implicit)
- Clarification triggers (structured, not judgment calls)

---

## Part 4: Proposed Boundary Definitions

### 4.1 Understand: Parser + Entity Resolver + Constraint Compiler

**Scope**: Convert fuzzy language into structured signals

**Core value proposition**: Understand is the **gatekeeper** that decides which of potentially hundreds of entities are "in play" for this request. A recipe queried 5 turns ago can still be marked relevant if the user references it.

**Inputs** (Context):
- Raw user message
- Recent conversation history
- **Tiered Entity Context** (see Section 5.6):
  - Active Entities (this session, recently referenced)
  - Background Entities (from DB, relevant to session topic)

**Outputs** (State):
```typescript
interface UnderstandOutput {
  // Entity resolution (UPGRADED)
  entity_mentions: EntityMention[];
  
  // Disambiguation flag (NEW)
  needs_disambiguation: boolean;
  disambiguation_options?: {
    entity_type: EntityType;
    candidates: { id: string; label: string }[];
    prompt: string;             // "Which recipe did you mean?"
  };
  
  // Constraint snapshot for this turn (NEW - feeds into session merge)
  constraint_snapshot: TurnConstraintSnapshot;
  
  // Quick mode detection (preserved, with confidence)
  quick_mode: boolean;
  quick_mode_confidence: 'high' | 'medium';  // If medium, Think validates
  quick_intent?: string;
  quick_subdomain?: Subdomain;
  
  // Simple processed message (max 50 chars)
  processed_message: string;
}

interface EntityMention {
  raw_text: string;
  entity_type: EntityType;
  resolved_id?: string;         // Only if unambiguous
  candidates?: string[];        // If multiple matches
  confidence: 'high' | 'medium' | 'low';
  resolution: 'exact' | 'fuzzy' | 'unresolved';
}

interface TurnConstraintSnapshot {
  // New constraints mentioned this turn
  new_constraints: Constraint[];
  
  // Explicit overrides ("actually, make it spicy")
  override_constraints: Constraint[];
  
  // Reset signals
  reset_goal: boolean;           // "never mind", "start fresh"
  goal_update?: string;          // New goal description if changed
  
  // Source tracking for debugging
  source_phrases: string[];
}

interface Constraint {
  type: 'ingredient_required' | 'ingredient_excluded' | 'equipment' | 
        'cuisine' | 'difficulty' | 'time_limit' | 'servings' | 'flavor';
  field: string;
  value: any;
  confidence: number;
}
```

**What Understand does NOT do**:
- Plan steps
- Choose execution strategy
- Generate content
- Decide CRUD operations
- **Infer goal from context** (removed - Think handles this)

**Boundary enforcement**:
- Output is machine-checkable (structured, not narrative)
- Confidence scores enable downstream gating
- Constraints are compiled once per turn, merged deterministically
- Entity resolution searches Active + Background tiers

---

### 4.2 Think: Planner + Data Requirements

**Scope**: Compiled state → execution plan + data needs

**Inputs** (State):
- UnderstandOutput (structured)
- User profile (compiled constraints)
- Dashboard (current counts, not full data)
- Session goal (if multi-turn)

**Outputs** (State):
```typescript
interface ThinkOutput {
  goal: string;                 // Human-readable for logging
  
  success_criteria: string[];   // Checkable conditions
  
  // Data requirements (abstract, not SQL)
  data_requirements: DataRequirement[];
  
  // Step graph
  steps: Step[];
  
  // For multi-turn: updated session state
  session_update?: SessionPatch;
}

interface DataRequirement {
  subdomain: Subdomain;
  intent: 'read_all' | 'read_filtered' | 'read_by_ids';
  filters?: {
    field: string;
    op: FilterOp;
    value: any;
  }[];
  entity_ids?: string[];        // If reading specific entities
  fields: 'minimal' | 'default' | 'full';
  purpose: string;              // For debugging/logging
}

interface Step {
  step_id: string;
  step_type: 'read' | 'write' | 'analyze' | 'generate';
  subdomain: Subdomain;
  group: number;                // For parallelization
  
  // NEW: Explicit batch manifest
  batch?: {
    total: number;
    items: BatchItem[];
  };
  
  // NEW: Input dependencies
  inputs: {
    from_step?: string;         // step_id
    from_data_requirement?: string;
    from_understand?: string;   // field name
  }[];
  
  // Human-readable for logging (NOT for Act interpretation)
  description: string;
}

interface BatchItem {
  ref: string;                  // temp_id or entity reference
  label: string;                // Human-readable
  payload_key?: string;         // Key in prior step's output
}
```

**What Think does NOT do**:
- Guess entity identity
- Enforce constraints (already compiled)
- Normalize schema payloads
- Decide CRUD order (implicit in step_type + subdomain)

**Boundary enforcement**:
- Steps reference inputs by ID, not description
- Batch counts are explicit, not verbal
- Data requirements are abstract (subdomain + intent), not SQL

---

### 4.3 Act: Deterministic Executor

**Scope**: Execute reads/writes with validated payloads

**Inputs** (State):
- Current step (structured)
- Prior step results (by step_id)
- Compiled payloads (if generate → write flow)
- Schema (for validation)

**Outputs** (State):
```typescript
interface ActOutput {
  action: 'tool_call' | 'step_complete' | 'blocked';
  
  // For tool_call
  tool?: ToolName;
  params?: ToolParams;
  
  // For step_complete
  result?: {
    // Structured deltas, not narratives
    created_ids: { id: string; type: string; label: string }[];
    updated_ids: { id: string; type: string; fields: string[] }[];
    deleted_ids: { id: string; type: string }[];
    
    // For read steps
    retrieved_count?: number;
    retrieved_data?: any;       // Schema-validated
    
    // For generate steps
    artifacts?: {
      artifact_type: string;
      schema_version: string;
      content: any;             // Full structured content
    }[];
  };
  
  // NEW: Batch progress tracking
  batch_progress?: {
    completed: number;
    total: number;
    completed_items: string[];  // refs from batch manifest
  };
  
  note_for_next_step?: string;  // IDs and refs only
  
  // For blocked
  blocked_reason?: string;
  blocked_code?: 'missing_content' | 'missing_ids' | 'validation_error';
}
```

**What Act does NOT do**:
- Guess entity mappings
- Coerce enums without explicit mapping
- Simplify generated content (unless mapping provided)
- Decide propose vs commit

**Boundary enforcement**:
- Batch progress is tracked against manifest
- Cannot complete step until batch complete
- Generated artifacts are preserved, not normalized

#### 4.3.1 Act's Context Model (What Act Sees)

Act should see a **deduplicated, context-aware summarization** focused only on the current turn's work. Act does NOT need to reason about:
- Cross-turn history (that's Understand's job)
- Entity resolution (already done)
- Complex UUID management (system handles this)

**Act's Prompt Structure**:
```markdown
## Current Step
| Step | 2 of 4 |
| Type | write |
| Goal | Save the 3 generated recipes |

## Batch Manifest
| Gen Ref | Label | Status | Saved Ref | DB ID |
|---------|-------|--------|-----------|-------|
| gen_recipe_1 | Honey Garlic Cod | pending | — | — |
| gen_recipe_2 | Lemon Butter Cod | pending | — | — |
| gen_recipe_3 | Piri Piri Fish | pending | — | — |

## Content to Save (from Step 1)
### gen_recipe_1: Honey Garlic Cod
```json
{
  "name": "Honey Garlic Soy Glazed Cod...",
  "cuisine": "american",
  "instructions": [...],
  "ingredients": [...]
}
```
### gen_recipe_2: Lemon Butter Cod
...

## Schema (recipes)
[Relevant table schema only]

## What Already Happened (This Step)
Tool Call 1: db_create on recipes → Created 3 records
  - gen_recipe_1 → recipe_1 (a508000d-...)
  - gen_recipe_2 → recipe_2 (f527cc94-...)
  - gen_recipe_3 → recipe_3 (eb87e3bd-...)
```

**Key principles**:

1. **Semantic References** — Ref prefix indicates lifecycle:
   ```
   gen_recipe_1 → Generated this turn, not yet saved (transient)
   recipe_1     → Saved to DB, has real ID (persisted)
   ref_recipe_5 → Referenced from prior turn (external lookup)
   ```
   
2. **System Manages ID Mapping** — When Act creates records, system captures the mapping:
   ```python
   # System does this, not Act
   id_mapping = {
       "gen_recipe_1": {
           "saved_ref": "recipe_1",
           "db_id": "a508000d-9b55-40f0-8886-dbdd88bd2de2"
       },
       "gen_recipe_2": {
           "saved_ref": "recipe_2", 
           "db_id": "f527cc94-5af5-451d-9e4a-16fdb9582bdc"
       },
   }
   ```

3. **Content Pre-Injected** — For Write steps following Generate, the content is RIGHT THERE:
   ```
   ✅ "Content to Save" section with full JSON
   ❌ "(use retrieve_step for details)"
   ```

4. **Intra-Turn Focus** — Act only sees current turn's steps:
   ```markdown
   ## Previous Steps (This Turn)
   Step 1 (generate): Created 3 recipes [gen_recipe_1, gen_recipe_2, gen_recipe_3]
   ```
   NOT a dump of all historical entities.

5. **Batch Progress Visible** — Act always knows where it is:
   ```markdown
   ## Batch Progress
   Completed: 1 of 3 (recipe_1 ✓)
   Remaining: gen_recipe_2, gen_recipe_3
   ```

**What Act receives vs what it creates**:

| Concern | Who Provides | Act's Responsibility |
|---------|--------------|---------------------|
| Gen refs (gen_recipe_1, etc.) | Think's batch manifest | Use as given |
| Content to save | Prior step's artifacts | Execute CRUD with it |
| Saved refs (recipe_1, etc.) | System after db_create | Use for FK references |
| Real DB IDs | System after db_create | Never type, use from mapping |
| Batch completeness | Batch manifest | Track progress, cannot exit early |

**ID handling flow**:
```
Think: batch.items = [{ref: "gen_recipe_1", label: "Honey Garlic Cod"}, ...]
                ↓
Act (Step 2): db_create recipes → System returns real IDs
                ↓
System: Maps gen_recipe_1 → recipe_1 (a508000d-...), updates batch manifest
                ↓
Act (Step 3): Sees "recipe_1 = a508000d-..." in ID Mappings
              Content pre-substituted with real IDs for FK
```

**Act NEVER has to**:
- Remember which gen_ref maps to which UUID
- Copy/paste long UUIDs (typo risk eliminated)
- Reason about entities from previous turns
- Parse conversation history for context

---

### 4.4 Reply: Presentation Layer

**Scope**: Render state + artifacts for user

**Inputs** (State):
- Execution summary (structured)
- Artifacts (full content)
- Entity state (what was created/updated)

**Outputs** (Context - for user consumption only):
- Natural language response
- Formatted content (recipes, lists, etc.)
- Single next step suggestion

**What Reply does NOT do**:
- Reconcile inconsistencies
- Justify decisions
- Claim correctness beyond state
- Re-interpret intent

**Boundary enforcement**:
- Labels representational status ("generated but not saved")
- Speaks as witness, not authority
- Surfaces state, doesn't smooth over it

---

### 4.5 Summarize: Audit Ledger

**Scope**: Immutable record of what happened

**Outputs** (State - for system memory):
```typescript
interface SummarizeOutput {
  turn_summary: string;         // Factual, brief
  
  // Execution ledger
  steps_completed: number;
  steps_total: number;
  tools_called: { tool: string; table?: string; count: number }[];
  
  // State deltas
  entities_created: { id: string; type: string; label: string }[];
  entities_updated: { id: string; type: string }[];
  entities_deleted: { id: string; type: string }[];
  
  // Artifacts
  artifacts_generated: { type: string; count: number }[];
  artifacts_saved: { type: string; count: number }[];
  
  // Errors
  errors: { code: string; message: string; step_id?: string }[];
}
```

**What Summarize does NOT do**:
- Propose next steps
- Describe food nicely
- Add new content

---

## Part 5: Infrastructure Changes

### 5.1 Entity System: Working Set Model

**Current problem**: Entities scattered across multiple sections with duplicate IDs

**Proposed solution**: Single "Working Set" table with semantic ref naming

#### Reference Naming Convention

| Prefix | Meaning | Location | Example |
|--------|---------|----------|---------|
| `gen_` | Generated this turn | Step output (deterministic) | `gen_recipe_1` |
| `{type}_` | Saved to DB | Database (has UUID) | `recipe_1` |
| `ref_` | Referenced from prior turn | Database (lookup) | `ref_recipe_42` |

**Key insight**: All refs point to **real, addressable data** — the prefix indicates **where it lives**:

| Ref | Exists? | Where | How to Access |
|-----|---------|-------|---------------|
| `gen_recipe_1` | ✅ Yes | Step 1 output, artifact[0] | Deterministic index |
| `recipe_1` | ✅ Yes | Database | UUID lookup |
| `ref_recipe_42` | ✅ Yes | Database | UUID lookup |

**This is NOT about existence — it's about location:**
- `gen_recipe_1` → Lives in step output, deterministically mapped to `artifacts[0]`
- `recipe_1` → Lives in database, mapped via ID Mapping Service
- The transition `gen_* → {type}_*` is a **location change**, not a creation event

#### Working Set Display

```markdown
## Working Set

| Ref | Type | Label | Status | DB ID |
|-----|------|-------|--------|-------|
| gen_recipe_1 | recipe | Honey Garlic Cod | generated | — |
| gen_recipe_2 | recipe | Lemon Butter Cod | generated | — |
| recipe_1 | recipe | Honey Garlic Cod | saved | a508000d-... |
| ref_mealplan_3 | meal_plan | Week of Jan 6 | external | 7b2f... |
```

**Lifecycle = Location transition**:
```
gen_recipe_1 (exists in: Step 1 output, artifacts[0])
     │
     ▼  [db_create succeeds]
     │
recipe_1 (exists in: Database, UUID: a508...)
```

**Key changes**:
1. **Unified view**: One table, not scattered sections
2. **Semantic refs**: Prefix indicates lifecycle state
3. **Clear lifecycle**: `gen_*` → `{type}_*` on save
4. **Explicit mapping**: gen_id to saved_id when created
5. **No duplicates**: Each entity appears once

**Implementation**:
- New `WorkingSet` class in `src/alfred/core/working_set.py`
- Replaces current entity tracking in `conversation.py`
- Rendered as table in Act prompts

### 5.2 Step Results: Content Preservation

**Current problem**: Generate output summarized before Write step

**Proposed solution**: Structured result storage with full content

```typescript
interface StepResult {
  step_id: string;
  step_type: StepType;
  
  // For read steps
  records?: any[];
  
  // For generate steps - FULL CONTENT PRESERVED
  artifacts?: {
    type: string;
    content: any;
    schema: string;
  }[];
  
  // Compact summary for display
  summary: string;
  
  // IDs for downstream reference
  ids: string[];
}
```

**Key changes**:
1. **Full artifacts preserved**: Not summarized until committed
2. **Indexed by step_id**: Downstream steps reference by ID
3. **Schema-typed**: Artifacts have explicit schema version
4. **Lazy loading**: Full content retrieved only when needed

**Implementation**:
- Modify `_format_step_results` in `act.py`
- Add `StepResultStore` for artifact persistence
- Auto-inject relevant content for Write steps following Generate

### 5.3 Batch Contracts: Enforceable Manifests

**Current problem**: "Save all 3" is verbal, not enforceable

**Proposed solution**: Explicit batch manifest in step schema

```typescript
interface BatchManifest {
  total: number;                // Enforceable count
  items: {
    ref: string;                // Identifier (temp_id or label)
    status: 'pending' | 'in_progress' | 'complete' | 'failed';
    result_id?: string;         // DB ID when created
  }[];
}
```

**Key changes**:
1. **Think declares batch**: Explicit count and item list
2. **Act tracks progress**: Updates status per item
3. **System validates**: Cannot complete step until all items done
4. **Failure handling**: Individual failures tracked, don't block others

**Implementation**:
- Add `batch` field to `Step` schema
- Modify Act's `step_complete` validation
- Add batch progress to ActOutput

### 5.4 Payload Compilation: Pre-Normalized for Write

**Current problem**: Act normalizes generated content (lossy)

**Proposed solution**: Compile payloads before Write step

```typescript
interface CompiledPayload {
  target_table: string;
  records: {
    ref: string;                // Maps to batch item
    data: Record<string, any>;  // Schema-validated
    linked_records?: {          // For FK tables
      table: string;
      records: Record<string, any>[];
    }[];
  }[];
}
```

**Key changes**:
1. **Generate outputs artifacts** (rich, not schema-constrained)
2. **System compiles payloads** (deterministic mapping)
3. **Write receives compiled payloads** (no interpretation needed)
4. **Discrepancies surfaced** (what was lost in compilation)

**Implementation**:
- Add `compile_payload` function per subdomain
- Run between Generate and Write steps
- Surface "simplified from" warnings in Reply

### 5.5 ID Mapping Service: Location Registry

**Current problem**: Act copies/pastes UUIDs, leading to typos. Act must track which `gen_*` ref maps to which database ID across tool calls.

**Key insight**: `gen_recipe_1` is **not ephemeral** — it's a deterministic reference to Step output:
```
gen_recipe_1 → step_results[1].artifacts[0]  // Always addressable
```

**Proposed solution**: System-managed location registry that tracks where each entity lives.

```typescript
interface TurnIdMapping {
  turn_id: string;
  
  // Location registry for this turn
  mappings: {
    gen_ref: string;          // gen_recipe_1 → lives in step output
    saved_ref: string;        // recipe_1 → lives in database (assigned on save)
    entity_type: EntityType;
    label: string;
    
    // Location tracking
    source_step?: number;     // Which step created it (for gen_* refs)
    artifact_index?: number;  // Index in that step's artifacts
    db_id?: string;           // Populated after db_create
    status: 'pending' | 'created' | 'failed';
    created_at_step?: number;
  }[];
}
```

**How it works**:

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Generate                                               │
│  ═══════════════                                                │
│  Act outputs:                                                   │
│    artifacts: [                                                 │
│      { ref: "gen_recipe_1", type: "recipe", label: "Honey.." },│
│      { ref: "gen_recipe_2", type: "recipe", label: "Lemon.." },│
│    ]                                                            │
│                                                                 │
│  System creates location registry:                              │
│    { gen_ref: "gen_recipe_1", source_step: 1, artifact_index: 0,│
│      status: "pending", db_id: null }                           │
│    { gen_ref: "gen_recipe_2", source_step: 1, artifact_index: 1,│
│      status: "pending", db_id: null }                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Write (recipes table)                                  │
│  ══════════════════════════════                                 │
│  Act sees in prompt:                                            │
│    ## Batch Manifest                                            │
│    | Ref | Label | Status | DB ID |                            │
│    | gen_recipe_1 | Honey Garlic Cod | pending | — |           │
│    | gen_recipe_2 | Lemon Butter Cod | pending | — |           │
│                                                                 │
│  Act calls: db_create(table="recipes", data=[...])             │
│                                                                 │
│  CRUD layer returns:                                            │
│    created_ids: ["a508000d-...", "f527cc94-..."]               │
│                                                                 │
│  System updates mapping + assigns saved_ref:                    │
│    { gen_ref: "gen_recipe_1", saved_ref: "recipe_1",           │
│      db_id: "a508000d-...", status: "created" }                │
│    { gen_ref: "gen_recipe_2", saved_ref: "recipe_2",           │
│      db_id: "f527cc94-...", status: "created" }                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Write (recipe_ingredients table)                       │
│  ════════════════════════════════════════                       │
│  Act sees in prompt:                                            │
│    ## ID Mappings (from prior steps)                            │
│    | Gen Ref | Saved Ref | DB ID |                             │
│    | gen_recipe_1 | recipe_1 | a508000d-9b55-40f0-... |        │
│    | gen_recipe_2 | recipe_2 | f527cc94-5af5-451d-... |        │
│                                                                 │
│    ## Content to Save                                           │
│    ### recipe_1 ingredients (FK already substituted)           │
│    [{ recipe_id: "a508000d-...", name: "cod", qty: 2 }, ...]   │
│                                                                 │
│  Act calls: db_create(table="recipe_ingredients",              │
│    data=[{ recipe_id: "a508000d-...", name: "cod", ... }])     │
│                                                                 │
│  ⚠️ Act uses the REAL ID pre-substituted in content            │
└─────────────────────────────────────────────────────────────────┘
```

**The ID Mapping Service**:

```python
class TurnIdMapper:
    """Location registry: tracks where each entity lives (step output vs database)."""
    
    def __init__(self, turn_id: str):
        self.turn_id = turn_id
        self.mappings: dict[str, IdMapping] = {}
    
    def register_from_step(self, gen_ref: str, entity_type: str, label: str, 
                           source_step: int, artifact_index: int):
        """Register entity location after Generate step.
        
        gen_recipe_1 exists at: step_results[source_step].artifacts[artifact_index]
        """
        self.mappings[gen_ref] = IdMapping(
            gen_ref=gen_ref,
            saved_ref=None,  # Assigned on save
            entity_type=entity_type,
            label=label,
            source_step=source_step,
            artifact_index=artifact_index,
            status='in_step_output'
        )
    
    def record_saved(self, gen_ref: str, db_id: str, step_index: int):
        """Called after db_create returns real ID — entity moved to database."""
        if gen_ref in self.mappings:
            m = self.mappings[gen_ref]
            m.db_id = db_id
            m.status = 'in_database'  # Location changed: step output → database
            m.created_at_step = step_index
            # Assign saved_ref: gen_recipe_1 → recipe_1
            m.saved_ref = self._to_saved_ref(gen_ref)
    
    def _to_saved_ref(self, gen_ref: str) -> str:
        """Convert gen_recipe_1 → recipe_1"""
        if gen_ref.startswith("gen_"):
            return gen_ref[4:]  # Remove "gen_" prefix
        return gen_ref
    
    def record_saved_batch(self, gen_refs: list[str], db_ids: list[str], step_index: int):
        """Called after batch db_create - matches by order."""
        for gen_ref, db_id in zip(gen_refs, db_ids):
            self.record_saved(gen_ref, db_id, step_index)
    
    def get_content(self, gen_ref: str, step_results: list) -> dict | None:
        """Retrieve actual content from step output using location info."""
        m = self.mappings.get(gen_ref)
        if m and m.source_step is not None and m.artifact_index is not None:
            return step_results[m.source_step].artifacts[m.artifact_index]
        return None
    
    def get_real_id(self, ref: str) -> str | None:
        """Lookup real ID for a gen_ref or saved_ref."""
        # Try direct lookup (gen_ref)
        if ref in self.mappings:
            return self.mappings[ref].db_id
        # Try saved_ref lookup
        for m in self.mappings.values():
            if m.saved_ref == ref:
                return m.db_id
        return None
    
    def format_for_prompt(self) -> str:
        """Format location registry for Act's prompt."""
        lines = [
            "## Entity Location Registry",
            "| Ref | Type | Label | Location | DB ID |",
            "|-----|------|-------|----------|-------|"
        ]
        for gen_ref, m in self.mappings.items():
            if m.status == 'in_step_output':
                location = f"Step {m.source_step}, artifact[{m.artifact_index}]"
            else:
                location = f"Database ({m.saved_ref})"
            db_id = m.db_id or "—"
            lines.append(f"| {gen_ref} | {m.entity_type} | {m.label} | {location} | {db_id} |")
        return "\n".join(lines)
    
    def inject_real_ids(self, payload: dict, gen_ref: str) -> dict:
        """Replace gen refs with real IDs in a payload."""
        db_id = self.get_real_id(gen_ref)
        if db_id:
            # For FK fields, substitute the real ID
            if 'recipe_id' in payload and payload['recipe_id'] in (gen_ref, self.mappings.get(gen_ref, {}).saved_ref):
                payload['recipe_id'] = db_id
        return payload
```

**Integration points**:

| When | What Happens | Who Does It |
|------|--------------|-------------|
| After Generate step | Register `gen_*` refs as pending | Act node (post-processing) |
| After db_create returns | Map `gen_*` → real ID, assign `saved_*` ref | CRUD layer callback |
| Before next step's prompt | Inject mapping table | `build_act_prompt()` |
| In Write step | Substitute FKs using real IDs | Payload compiler |

**What Act sees vs what Act does**:

| Concern | Act Sees | Act Does |
|---------|----------|----------|
| Generated refs | `gen_recipe_1`, `gen_recipe_2` in batch manifest | Reference by name |
| Saved refs | `recipe_1`, `recipe_2` after save | Use for future references |
| Real IDs | Mapping table with UUIDs | Never types them |
| FK values | Pre-substituted in "Content to Save" | Just execute db_create |

**Key guarantee**: Act never types a UUID. The mapping service handles all ID substitution.

**Implementation**:
- New `TurnIdMapper` class in `src/alfred/core/id_mapper.py`
- Integrate with Act node's step processing
- CRUD layer returns created IDs in order
- `build_act_prompt` injects mapping table

### 5.6 Entity Context Model: Tiered Resolution

**Current problem**: Understand only sees "Recent Items" (~20 entities from recent operations). A recipe discussed 5 turns ago is invisible.

**Proposed solution**: Tiered entity context with selective relevance

```typescript
interface EntityContext {
  // Tier 1: Active this session (high priority for resolution)
  active_entities: {
    id: string;
    type: EntityType;
    label: string;
    last_referenced_turn: number;
    last_referenced_phrase?: string;  // "save it", "that recipe"
  }[];
  
  // Tier 2: Background (from DB, relevant to session topic)
  background_entities: {
    id: string;
    type: EntityType;
    label: string;
    relevance_reason: string;         // "contains: cod", "recent: 2 days ago"
  }[];
}
```

**Prompt format for Understand**:
```markdown
## Entity Context

### Active Entities (this session)
| ID | Type | Label | Last Referenced |
|----|------|-------|-----------------|
| a508... | recipe | Honey Garlic Cod | Turn 4: "save it" |
| f527... | recipe | Lemon Butter Cod | Turn 4 |

### Background Entities (relevant to session)
| ID | Type | Label | Relevance |
|----|------|-------|-----------|
| d3ae... | recipe | Mediterranean Cod | contains: cod |
| 487f... | recipe | Thai Chicken Curry | recent: 2 days ago |
```

**Resolution logic**:
```python
def resolve_entity_reference(raw_text: str, context: EntityContext) -> EntityMention:
    # 1. Check active entities first (high confidence)
    active_matches = fuzzy_match(raw_text, context.active_entities)
    if len(active_matches) == 1:
        return EntityMention(
            resolved_id=active_matches[0].id,
            confidence='high',
            resolution='exact'
        )
    
    # 2. Check background if no active match
    if not active_matches:
        background_matches = fuzzy_match(raw_text, context.background_entities)
        if len(background_matches) == 1:
            return EntityMention(
                resolved_id=background_matches[0].id,
                confidence='medium',
                resolution='fuzzy'
            )
    
    # 3. Multiple matches = needs disambiguation
    if len(active_matches) > 1 or len(background_matches) > 1:
        return EntityMention(
            candidates=[m.id for m in active_matches + background_matches],
            confidence='low',
            resolution='unresolved'
        )
    
    # 4. No matches
    return EntityMention(confidence='low', resolution='unresolved')
```

**Key benefits**:
1. Recipe from 5 turns ago can be resolved if still in Active tier
2. Background provides DB context without overwhelming prompt
3. Disambiguation is explicit, not implicit in prose

### 5.7 Constraint Accumulation: B+C Hybrid Model

**Current problem**: Constraints re-derived from conversation prose each turn. Drift, forgetting, inconsistent interpretation.

**Proposed solution**: Session state (B) with per-turn snapshots (C) and deterministic merge

```
┌─────────────────────────────────────────────────────┐
│  SESSION STATE (Canonical Store)                    │
│  ════════════════════════════════                   │
│  permanent_constraints:                             │
│    allergies: [shellfish]                          │
│    dietary: []                                      │
│    equipment: [air_fryer, instant_pot]             │
│                                                     │
│  active_goal:                                       │
│    description: "3 fish recipes for air fryer"     │
│    started_turn: 1                                  │
│    constraints:                                     │
│      - ingredient_required: cod                    │
│      - ingredient_required: rice                   │
│      - flavor: not_spicy                           │
└─────────────────────────────────────────────────────┘
                       ▲
                       │ merge_constraints()
                       │
┌─────────────────────────────────────────────────────┐
│  PER-TURN SNAPSHOT (from Understand)                │
│  ════════════════════════════════════               │
│  new_constraints: [flavor: not_spicy]              │
│  override_constraints: []                           │
│  reset_goal: false                                 │
│  goal_update: null                                 │
└─────────────────────────────────────────────────────┘
```

**The merge function (deterministic, no LLM)**:
```python
def merge_constraints(
    session: SessionConstraints,
    snapshot: TurnConstraintSnapshot
) -> SessionConstraints:
    """Deterministic merge - no LLM interpretation."""
    
    # Reset if flagged
    if snapshot.reset_goal:
        session.active_goal = None
        return session
    
    # Initialize goal if needed
    if session.active_goal is None:
        session.active_goal = ActiveGoal(
            description=snapshot.goal_update or "User request",
            started_turn=current_turn,
            constraints=[]
        )
    
    # Apply overrides (explicit contradictions replace existing)
    for override in snapshot.override_constraints:
        session.active_goal.constraints = [
            c for c in session.active_goal.constraints 
            if not (c.type == override.type and c.field == override.field)
        ]
        session.active_goal.constraints.append(override)
    
    # Add new constraints (accumulate)
    for new in snapshot.new_constraints:
        if not any(c.type == new.type and c.field == new.field 
                   for c in session.active_goal.constraints):
            session.active_goal.constraints.append(new)
    
    # Update goal description if provided
    if snapshot.goal_update:
        session.active_goal.description = snapshot.goal_update
    
    return session
```

**Reset triggers**:
- User says "never mind", "start over", "forget that"
- Explicit new goal statement with different subdomain
- 3+ turns without referencing prior entities (heuristic, configurable)

**What Think receives**:
```typescript
interface ThinkInput {
  // From Understand
  entity_mentions: EntityMention[];
  processed_message: string;
  
  // From Session State (compiled, not prose)
  permanent_constraints: PermanentConstraints;
  active_goal?: {
    description: string;
    constraints: Constraint[];
  };
}
```

### 5.8 Artifact Lifecycle: Intra-Turn vs Cross-Turn

**Clarification**: Artifact persistence is **only an intra-turn concern**. Once committed to DB, entities are managed by the Entity Context Model (5.6).

```
┌─────────────────────────────────────────────────────────────────┐
│  INTRA-TURN / INTER-STEP (Artifact Phase)                       │
│  ═══════════════════════════════════════                        │
│                                                                 │
│  Generate Step → artifacts[] in step_results                   │
│       │         (full content preserved)                       │
│       ▼                                                         │
│  Write Step → artifacts auto-injected                          │
│       │       (no "(use retrieve_step)" summarization)         │
│       ▼                                                         │
│  DB Commit → real IDs assigned                                 │
│       │                                                         │
│  ════════════════════════════════════════════════════════════  │
│  BOUNDARY: Artifact becomes Entity                             │
│  ════════════════════════════════════════════════════════════  │
│       │                                                         │
│       ▼                                                         │
│  Summarize → records entity in conversation memory             │
│       │                                                         │
│       ▼                                                         │
│  CROSS-TURN: Entity Context Model manages it                   │
│              (Active tier → Background tier → Archive)         │
└─────────────────────────────────────────────────────────────────┘
```

**Key insight**: We don't need a separate artifact store. We need:
1. **Better injection**: `_format_step_results` preserves full content for Write steps
2. **Clear boundary**: Artifact → Entity transition happens at DB commit
3. **Entity Context**: Manages cross-turn visibility

---

## Part 6: Migration Path

### Phase 1: Foundation (Low Risk)

1. **Step result preservation** (Section 5.2)
   - Modify `_format_step_results` to preserve full artifacts
   - Auto-inject for Write steps following Generate
   - Test with generate → write flows
   - **Directly fixes**: Recipe content lost failure

2. **Batch progress tracking** (Section 5.3)
   - Add `batch_progress` to ActOutput
   - Validate cannot complete with pending items
   - Surface failed items in Reply
   - **Directly fixes**: Partial batch completion failure

3. **Working Set display** (Section 5.1)
   - Create unified entity table format
   - Replace scattered entity sections in prompts
   - **Directly fixes**: Entity duplication confusion

4. **ID Mapping Service** (Section 5.5)
   - Implement `TurnIdMapper` class
   - Integrate with CRUD layer to capture created IDs
   - Auto-inject mapping table into Act prompts
   - Pre-substitute FKs in payloads
   - **Directly fixes**: UUID typo failures

### Phase 2: Entity & Constraint System (Medium Risk)

5. **Entity Context Model** (Section 5.6)
   - Implement tiered entity context (Active + Background)
   - Update Understand to receive full context
   - Add entity resolution logic with confidence
   - Test with multi-turn flows

6. **Understand output restructure** (Section 4.1)
   - Migrate to structured EntityMention output
   - Add disambiguation flag
   - Add TurnConstraintSnapshot output
   - Preserve backward compatibility during transition

7. **Constraint accumulation** (Section 5.7)
   - Implement SessionConstraints storage
   - Add deterministic merge function
   - Implement reset triggers
   - Test with multi-turn constraint flows

### Phase 3: Think Abstraction (Higher Risk)

8. **Payload compilation** (Section 5.4)
   - Implement per-subdomain compilers
   - Add between generate and write
   - Surface compilation warnings
   - Test with complex recipes

9. **Think data requirements**
   - Migrate to abstract data requirements model
   - Remove SQL-level details from Think
   - Add step input dependencies
   - Test with multi-step flows

### Phase Summary

| Phase | Risk | Effort | Fixes |
|-------|------|--------|-------|
| 1 | Low | 1-2 days | Content loss, partial batch, entity confusion |
| 2 | Medium | 3-5 days | Multi-turn context, entity resolution |
| 3 | Higher | 1 week | Full abstraction, payload compilation |

---

## Part 7: Decisions (Resolved)

### 7.1 Understand Scope ✅ DECIDED

**Question**: How much entity resolution should Understand do?

**Decision**: **Option A+ with Tiered Entity Context**

- Structured output with confidence scores
- Tiered entity context (Active + Background)
- Disambiguation flag when multiple candidates
- Quick mode preserved with confidence gating

**Key win**: Removed goal inference from Understand. Selective entity management is Understand's core value — a recipe from 5 turns ago can still be marked relevant.

**Quick mode status**: Keep for now. If mistakes observed, gate by confidence or remove entirely.

**See**: Section 5.6 (Entity Context Model)

### 7.2 Constraint Accumulation ✅ DECIDED

**Question**: How do constraints accumulate across turns?

**Decision**: **B+C Hybrid — Session State + Per-Turn Snapshots + Deterministic Merge**

- **Session state (B)**: Canonical store of accumulated constraints
- **Per-turn snapshot (C)**: Understand outputs what's new this turn
- **Merge function**: Deterministic, no LLM re-interpretation

**Reset triggers**:
- User says "never mind", "start over", "forget that"
- Explicit new goal with different subdomain
- 3+ turns without referencing prior entities (configurable heuristic)

**See**: Section 5.7 (Constraint Accumulation)

### 7.3 Artifact Persistence ✅ DECIDED

**Question**: Where do generated artifacts live before commitment?

**Decision**: **Option A+ — Intra-Turn Only with Smart Injection**

- Artifacts stored in `step_results` (existing mechanism)
- Full content preserved, not summarized
- Auto-injected for Write steps following Generate
- No new storage system needed

**Key insight**: This is only an **intra-turn concern**. Once committed to DB, entities are managed by the Entity Context Model, not artifact storage.

**See**: Section 5.8 (Artifact Lifecycle)

### 7.4 Error Recovery ✅ DECIDED

**Question**: What happens when Act fails mid-batch?

**Decision**: **Option B — Partial Completion with Progress Tracking**

```typescript
interface BatchProgress {
  total: number;
  completed: { ref: string; result_id: string }[];
  failed: { ref: string; error: string; retriable: boolean }[];
  pending: string[];
}
```

**Rules**:
- Act cannot `step_complete` while `pending.length > 0`
- Act CAN `step_complete` with failed items
- Failed items surfaced in Reply
- No retry logic in Phase 1

**Subdomain policies** (future consideration):
- `recipes`: Allow partial
- `meal_plans`: May require all-or-nothing
- Configurable per subdomain

---

## Appendix A: Prompt Log References

The following session logs informed this specification:

| Log | Flow Type | Failure Observed |
|-----|-----------|------------------|
| 253-258_act.md | Generate → Write recipes + ingredients | Content lost, partial batch |
| 266-280_act.md | Chettinad chicken creation | UUID typo, missing ingredients |
| 254_act.md | Write step | Simplified recipes instead of generated |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Context** | Information that informs reasoning (epistemic) |
| **State** | Information that constrains behavior (normative) |
| **Working Set** | Current turn's entities with lifecycle tracking |
| **Artifact** | Generated content before normalization/save |
| **Compiled Payload** | Schema-ready data derived from artifact |
| **Batch Manifest** | Explicit list of items in a multi-item operation |
| **Entity Resolution** | Mapping user text to canonical IDs |
| **Constraint Compilation** | Converting natural language rules to structured filters |

---

## Appendix C: Critical Gap — ID Translation Layer

**Discovered:** 2026-01-06 during testing

### The Problem

The current implementation exposes UUIDs to LLMs in several ways:
1. Read results show truncated IDs (`id:..c69607bb`)
2. LLMs attempt to reconstruct UUIDs (padding with zeros)
3. Operations fail silently with invalid UUIDs

**Observed failure:**
```
Act saw: id:..c69607bb
Act tried: db_delete with id = "c69607bb-0000-0000-0000-000000000000"
Result: Delete failed (no matching records)
```

### The V4 Intent (Misunderstood)

Section 5.5 states: "Act NEVER types UUIDs. The mapping service handles all ID substitution."

This was interpreted as only applying to generate→write flows. **The actual intent:**
- LLMs should NEVER see UUIDs
- A system layer translates ALL CRUD input/output
- LLMs only see simple refs: `recipe_1`, `inventory_5`

### The Solution

**TurnIdRegistry** — a translation layer between LLMs and CRUD:

```
LLM sees: recipe_1, recipe_2
    ↕ (TurnIdRegistry translates)
DB uses: a508000d-..., f527cc94-...
```

**Full specification:** `docs/id-translation-layer-spec.md`

### Status

| Task | Status |
|------|--------|
| Specification written | ✅ Complete |
| TurnIdRegistry implementation | ✅ Complete |
| CRUD layer integration | ✅ Complete |
| Prompt cleanup (remove UUIDs) | ✅ Complete |
| Hygiene audit | ✅ Complete |

### Files Changed

**New:**
- `src/alfred/core/id_registry.py` - TurnIdRegistry class

**Modified:**
- `src/alfred/tools/crud.py` - Added `registry` param to `execute_crud`, translation layer
- `src/alfred/graph/nodes/act.py` - Integrated registry with CRUD calls
- `src/alfred/graph/state.py` - Added `id_registry` field
- `src/alfred/prompts/injection.py` - Removed ID truncation
- `src/alfred/core/entity_context.py` - Removed ID truncation
- `src/alfred/core/working_set.py` - Removed ID truncation
- `src/alfred/core/id_mapper.py` - Updated for ref-based display
- `src/alfred/graph/nodes/understand.py` - Removed ID truncation
- `prompts/act/base.md` - Updated to ref-based IDs
- `prompts/act/crud.md` - Updated examples to use refs
- `prompts/act/write.md` - Updated FK handling and examples

---

## Appendix D: Implementation Status

### Phase 1: Foundation (Low Risk) ✅ IMPLEMENTED

| Item | Spec Section | Files Changed | Status | Needs Testing |
|------|--------------|---------------|--------|---------------|
| Step result preservation | 5.2 | `act.py`, `state.py` | ✅ Done | Generate → Write flow |
| Batch progress tracking | 5.3 | `state.py` (BatchManifest) | ✅ Done | Multi-item batch operations |
| Working Set display | 5.1 | `working_set.py` (new) | ✅ Done | Entity table rendering |
| ID Mapping Service | 5.5 | `id_mapper.py` (new) | ✅ Done | FK substitution in write steps |
| Act Prompt Restructure | 4.3.1 | `act.py`, `injection.py`, `prompts/act/base.md` | ✅ Done | Prompt structure validation |

### Phase 2: Entity & Constraint System (Medium Risk) ✅ IMPLEMENTED

| Item | Spec Section | Files Changed | Status | Needs Testing |
|------|--------------|---------------|--------|---------------|
| Entity Context Model | 5.6 | `entity_context.py` (new) | ✅ Done | Tiered resolution |
| Understand output restructure | 4.1 | `state.py` (EntityMention, TurnConstraintSnapshot) | ✅ Done | Structured entity mentions |
| Constraint accumulation | 5.7 | `session_state.py` (new) | ✅ Done | Multi-turn constraint merge |
| Reply Boundary | 4.4 | `reply.py`, `prompts/reply.md` | ✅ Done | Status labels in reply |
| Summarize Output | 4.5 | `summarize.py`, `state.py` (SummarizeOutput) | ✅ Done | Structured audit ledger |

### Phase 3: Think Abstraction (Higher Risk) ⚠️ PARTIALLY DEPRECATED

| Item | Spec Section | Files Changed | Status | Notes |
|------|--------------|---------------|--------|-------|
| Payload compilation | 5.4 | `payload_compiler.py` (new) | ✅ Done | Recipe payload compilation |
| Think data requirements | N/A | N/A | ❌ **Deprecated** | See V4.1 below |

### V4.1 Simplification (2026-01-08) — Deprecated Unused Fields

**Rationale:** With `SessionIdRegistry` tracking entities across turns, the V4 "abstract data needs" system became redundant. These fields were generated by Think but never read by any downstream code.

**Deprecated from `ThinkOutput`:**
- `data_requirements` — Never used; entity tracking handled by SessionIdRegistry
- `success_criteria` — Never validated downstream

**Deprecated from `ThinkStep`:**
- `referenced_entities` — Entity tracking handled by SessionIdRegistry  
- `input_from_steps` — Group-based parallelism handles dependencies
- `data_requirement` — Never used

**Deleted:**
- `DataRequirement` model — No longer needed

**Files Changed:**
- `state.py` — Removed unused fields and model
- `prompts/think.md` — Replaced with lean v2 (484 → 187 lines)
- `workflow.py` — Removed `needs_proposal` check (use `decision` only)

**Token savings:** ~200 tokens per Think call

### V4 Refinements (2026-01-06) ✅ IMPLEMENTED

| Item | Description | Files Changed | Status | Needs Testing |
|------|-------------|---------------|--------|---------------|
| Entity Curation by Understand | Understand curates entity context based on intent, not time | `entity_context.py`, `state.py`, `understand.py`, `prompts/understand.md` | ✅ Done | "forget that", topic changes |
| Simplified Summarize | Summarize is Conversation Historian, not curator | `summarize.py`, `prompts/summarize.md` | ✅ Done | Turn compression |
| EntityCurationDecision | New model for Understand's curation output | `state.py` | ✅ Done | Curation decisions |
| _compress_turns_to_narrative | LLM-based narrative compression (no IDs) | `summarize.py` | ✅ Done | 4+ turn conversations |

---

### Test Scenarios

#### Scenario 1: Generate → Write Flow (Phase 1)
```
User: "Create 3 cod recipes and save them"
Expected:
- Generate step creates 3 full recipes with artifacts
- Write step sees full content (not "(use retrieve_step)")
- BatchManifest tracks 3 items
- ID mapping shows gen_recipe_1 → recipe_1 → UUID
```

#### Scenario 2: Entity Curation (V4 Refinement)
```
User: "Create 2 fish recipes"
User: "Actually, forget those and make chicken instead"
Expected:
- Understand outputs entity_curation.clear_all=true OR drop_entities=[...]
- entity_context cleared before Think plans chicken recipes
```

#### Scenario 3: Multi-turn Constraint Accumulation (Phase 2)
```
User: "I want fish recipes"
User: "Use cod"
User: "Keep it simple"
Expected:
- SessionConstraints accumulates: protein=cod, style=simple
- Think sees compiled constraints, not prose history
```

#### Scenario 4: Conversation Compression (V4 Refinement)
```
User: [4+ turns of conversation]
Expected:
- recent_turns limited to FULL_DETAIL_TURNS (3)
- Older turns compressed to history_summary (narrative, no IDs)
- Summarize uses _compress_turns_to_narrative
```

#### Scenario 5: Partial Batch Failure
```
User: "Save these 3 recipes"
[Simulate one failing]
Expected:
- BatchManifest shows: 2 completed, 1 failed
- Reply surfaces failure explicitly
- step_complete allowed with failures tracked
```

---

### Files Added/Modified Summary

**New Files (V4):**
- `src/alfred/core/working_set.py` — WorkingSet entity tracking
- `src/alfred/core/id_mapper.py` — TurnIdMapper for ID resolution
- `src/alfred/core/entity_context.py` — EntityContextModel tiered resolution
- `src/alfred/core/session_state.py` — SessionConstraints accumulation
- `src/alfred/core/payload_compiler.py` — PayloadCompiler for write steps

**Modified Files:**
- `src/alfred/graph/state.py` — Added BatchManifest, EntityMention, TurnConstraintSnapshot, EntityCurationDecision, SummarizeOutput; V4.1: Removed DataRequirement
- `src/alfred/graph/nodes/act.py` — Integrated WorkingSet, TurnIdMapper, BatchManifest
- `src/alfred/graph/nodes/understand.py` — Entity curation application
- `src/alfred/graph/nodes/summarize.py` — Simplified to Conversation Historian
- `src/alfred/graph/nodes/reply.py` — Status labels, witness perspective
- `src/alfred/prompts/injection.py` — V4 context sections
- `prompts/understand.md` — Entity curation output
- `prompts/summarize.md` — Conversation Historian role
- `prompts/act/base.md` — Restructured prompt sections
- `prompts/reply.md` — Witness perspective
- `prompts/think.md` — V4.1: Lean prompt (484 → 187 lines)

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-05 | Cursor + User | Initial draft |
| 2026-01-05 | Cursor + User | Resolved open questions, added Entity Context Model (5.6), Constraint Accumulation (5.7), Artifact Lifecycle (5.8) |
| 2026-01-05 | Cursor + User | Added Act's Context Model (4.3.1) - defines simplified refs, pre-injected content, ID mapping flow |
| 2026-01-05 | Cursor + User | Added ID Mapping Service (5.5) - TurnIdMapper class, gen→saved ref resolution, eliminates UUID typing |
| 2026-01-05 | Cursor + User | Semantic ref naming as **location indicators**: `gen_*` (step output), `{type}_*` (database), `ref_*` (external) |
| 2026-01-05 | Cursor + User | Renamed to "Location Registry" — entities always exist, prefix indicates where |
| 2026-01-06 | Cursor + User | Added Appendix C: Implementation Status with test scenarios |
| 2026-01-06 | Cursor + User | V4 Refinement: Understand curates entity context, Summarize is Conversation Historian |
| 2026-01-08 | Cursor + User | V4.1 Simplification: Deprecated unused fields (DataRequirement, success_criteria, etc.), lean Think prompt |

