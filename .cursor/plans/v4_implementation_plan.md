---
name: V4 Implementation Plan
overview: Create a phased TODO plan document for implementing V4 architecture changes, referencing the v4-architecture-spec.md for detailed implementation guidance.
todos:
  - id: p1-step-results
    content: "Phase 1.1: Step result preservation - preserve full artifacts in act.py"
    status: pending
  - id: p1-batch-tracking
    content: "Phase 1.2: Batch progress tracking - add BatchManifest, validate completion"
    status: pending
  - id: p1-working-set
    content: "Phase 1.3: Working Set display - unified entity table with semantic refs"
    status: pending
  - id: p1-id-mapper
    content: "Phase 1.4: ID Mapping Service - TurnIdMapper class, eliminate UUID typing"
    status: pending
    dependencies:
      - p1-working-set
  - id: p1-act-prompt
    content: "Phase 1.5: Act Prompt Restructure - Batch Manifest, Content to Save sections"
    status: pending
    dependencies:
      - p1-working-set
      - p1-id-mapper
  - id: p2-entity-context
    content: "Phase 2.1: Entity Context Model - tiered Active + Background resolution"
    status: pending
    dependencies:
      - p1-working-set
  - id: p2-understand-restructure
    content: "Phase 2.2: Understand output restructure - EntityMention, disambiguation"
    status: pending
    dependencies:
      - p2-entity-context
  - id: p2-constraints
    content: "Phase 2.3: Constraint accumulation - SessionConstraints, deterministic merge"
    status: pending
    dependencies:
      - p2-understand-restructure
  - id: p2-reply-boundary
    content: "Phase 2.4: Reply Boundary - label status, surface state, witness not authority"
    status: pending
    dependencies:
      - p1-batch-tracking
  - id: p2-summarize-output
    content: "Phase 2.5: Summarize Output - structured deltas, artifact counts, errors"
    status: pending
    dependencies:
      - p1-working-set
  - id: p3-payload-compile
    content: "Phase 3.1: Payload compilation - per-subdomain compilers"
    status: pending
    dependencies:
      - p1-step-results
      - p1-id-mapper
  - id: p3-think-data-req
    content: "Phase 3.2: Think data requirements - abstract DataRequirement model"
    status: pending
    dependencies:
      - p2-constraints
---

# V4 Implementation Plan

A phased implementation plan for Alfred V4 architecture changes. References [v4-architecture-spec.md](docs/v4-architecture-spec.md) for detailed specifications.

---

## Phase 1: Foundation (Low Risk)
**Effort**: 1-2 days | **Directly fixes**: Content loss, partial batch, entity confusion, UUID typos

### 1.1 Step Result Preservation
**Spec**: Section 5.2

**Files**: `src/alfred/graph/nodes/act.py`

**Tasks**:
- Modify `_format_step_results` to preserve full artifact content
- For Write steps following Generate, auto-inject full content (not "(use retrieve_step)")
- Add `artifacts` field to step result structure

**Success**: Generate → Write flow preserves detailed recipes with all ingredients

---

### 1.2 Batch Progress Tracking
**Spec**: Section 5.3

**Files**: `src/alfred/graph/nodes/act.py`, `src/alfred/graph/state.py`

**Tasks**:
- Add `BatchManifest` model with `total`, `items[]`, and per-item status
- Add `batch_progress` to `ActOutput`
- Validate: cannot call `step_complete` while `pending.length > 0`
- Surface failed items (don't block others)

**Success**: "Save all 3 recipes" always saves 3 or reports which failed

---

### 1.3 Working Set Display
**Spec**: Section 5.1

**Files**: `src/alfred/core/working_set.py` (new), `src/alfred/prompts/injection.py`

**Tasks**:
- Create `WorkingSet` class with unified entity table
- Implement semantic ref naming: `gen_*` (generated), `recipe_*` (saved), `ref_*` (external)
- Replace scattered entity sections in Act prompts with single table
- Track lifecycle: `gen_recipe_1` → `recipe_1` on save

**Success**: Act sees one entity table, no duplicates

---

### 1.4 ID Mapping Service
**Spec**: Section 5.5

**Files**: `src/alfred/core/id_mapper.py` (new), `src/alfred/graph/nodes/act.py`, `src/alfred/tools/crud.py`

**Tasks**:
- Create `TurnIdMapper` class with location registry
- Register `gen_*` refs after Generate step
- Capture real IDs from CRUD layer after `db_create`
- Auto-inject mapping table into Act prompts
- Pre-substitute FKs in payloads for linked table writes

**Success**: Act never types UUIDs; `recipe_ingredients` correctly reference parent recipe IDs

---

### 1.5 Act Prompt Restructure
**Spec**: Section 4.3.1

**Files**: `src/alfred/prompts/injection.py`, `prompts/act/base.md`

**Tasks**:
- Restructure Act prompt with explicit sections: Current Step, Batch Manifest, Content to Save
- Add "What Already Happened (This Step)" section for intra-step tool call history
- Remove scattered entity sections, use Working Set table only
- Focus on intra-turn context only (not cross-turn history dumps)
- Add Batch Progress section showing completed/remaining items

**Success**: Act prompt is focused, deduplicated, with clear section boundaries

---

## Phase 2: Entity, Constraint, and Output Systems (Medium Risk)
**Effort**: 3-5 days | **Directly fixes**: Multi-turn context drift, entity resolution, output accuracy

### 2.1 Entity Context Model
**Spec**: Section 5.6

**Files**: `src/alfred/memory/conversation.py`, `src/alfred/graph/nodes/understand.py`

**Tasks**:
- Implement tiered context: Active (this session) + Background (DB, relevant)
- Add `last_referenced_turn` and `relevance_reason` tracking
- Update Understand prompt to show tiered entity table
- Implement resolution logic: Active first, then Background, then disambiguate

**Success**: Recipe from 5 turns ago can be resolved if user references it

---

### 2.2 Understand Output Restructure
**Spec**: Section 4.1

**Files**: `src/alfred/graph/nodes/understand.py`, `src/alfred/graph/state.py`, `prompts/understand.md`

**Tasks**:
- Add `EntityMention` model with `confidence` and `resolution` type
- Add `needs_disambiguation` flag with `disambiguation_options`
- Add `TurnConstraintSnapshot` output (new/override constraints, reset signals)
- Keep `quick_mode` with confidence gating

**Success**: Understand outputs structured entity mentions, not prose descriptions

---

### 2.3 Constraint Accumulation
**Spec**: Section 5.7

**Files**: `src/alfred/core/session_state.py` (new), `src/alfred/graph/nodes/understand.py`

**Tasks**:
- Create `SessionConstraints` with `permanent_constraints` and `active_goal`
- Implement deterministic `merge_constraints()` function (no LLM)
- Implement reset triggers: "never mind", subdomain change, 3+ turns no reference
- Feed compiled constraints to Think (not prose)

**Success**: "Use cod" in Turn 2 persists to Turn 4 without re-extraction

---

### 2.4 Reply Boundary
**Spec**: Section 4.4

**Files**: `src/alfred/graph/nodes/reply.py`, `prompts/reply.md`

**Tasks**:
- Update Reply to label representational status ("generated but not saved", "3 of 3 saved")
- Surface batch failures explicitly (don't smooth over partial completion)
- Speak as witness, not authority (report what happened, not what should have happened)
- Add single next-step suggestion (not multiple options)

**Success**: Reply accurately reflects execution state, including partial failures

---

### 2.5 Summarize Output Restructure
**Spec**: Section 4.5

**Files**: `src/alfred/graph/nodes/summarize.py`, `src/alfred/graph/state.py`

**Tasks**:
- Restructure to `SummarizeOutput` with explicit fields:
  - `entities_created`, `entities_updated`, `entities_deleted` (structured, not prose)
  - `artifacts_generated`, `artifacts_saved` (counts by type)
  - `errors[]` with code, message, step_id
- Remove content generation from Summarize (no "describe food nicely")
- Factual `turn_summary` only

**Success**: Summarize produces machine-readable audit ledger, not narrative

---

## Phase 3: Think Abstraction (Higher Risk)
**Effort**: ~1 week | **Completes**: Full state/context boundary enforcement

### 3.1 Payload Compilation
**Spec**: Section 5.4

**Files**: `src/alfred/tools/payload_compiler.py` (new), per-subdomain compilers

**Tasks**:
- Create `compile_payload()` function per subdomain
- Run between Generate and Write steps
- Output `CompiledPayload` with `target_table`, `records[]`, `linked_records[]`
- Surface "simplified from" warnings in Reply

**Success**: Write step receives schema-ready payloads, no normalization needed

---

### 3.2 Think Data Requirements
**Spec**: Section 4.2

**Files**: `src/alfred/graph/nodes/think.py`, `src/alfred/graph/state.py`, `prompts/think.md`

**Tasks**:
- Add `DataRequirement` model (subdomain, intent, filters, fields)
- Add `Step.inputs[]` for explicit dependencies
- Remove SQL-level details from Think output
- Add `batch` field to Step with explicit item list

**Success**: Think outputs abstract requirements; system translates to queries

---

## Verification Criteria

| Phase | Test Scenario | Expected Outcome |
|-------|---------------|------------------|
| 1.1-1.4 | "Create 3 fish recipes and save them" | All 3 saved with full ingredients |
| 1.4 | Write step for recipe_ingredients | Uses correct parent recipe UUIDs |
| 1.5 | Inspect Act prompt during multi-step | Single Working Set table, no duplicates |
| 2.1 | Turn 4: "save those recipes" (from Turn 1) | Resolves correct entities |
| 2.3 | "Use cod" + 2 turns later + "make it spicy" | Both constraints applied |
| 2.4 | Partial batch failure (2 of 3 saved) | Reply reports exactly what saved/failed |
| 2.5 | After any turn, inspect summarize output | Structured JSON, no prose descriptions |
| 3 | Complex recipe with 12 ingredients | Full content preserved through pipeline |

---

## Spec Coverage

| Spec Section | Plan Task | Status |
|--------------|-----------|--------|
| 4.1 Understand | 2.2 | ✅ |
| 4.2 Think | 3.2 | ✅ |
| 4.3 Act + 4.3.1 | 1.5 | ✅ |
| 4.4 Reply | 2.4 | ✅ |
| 4.5 Summarize | 2.5 | ✅ |
| 5.1 Working Set | 1.3 | ✅ |
| 5.2 Step Results | 1.1 | ✅ |
| 5.3 Batch Contracts | 1.2 | ✅ |
| 5.4 Payload Compile | 3.1 | ✅ |
| 5.5 ID Mapping | 1.4 | ✅ |
| 5.6 Entity Context | 2.1 | ✅ |
| 5.7 Constraints | 2.3 | ✅ |
| 5.8 Artifact Lifecycle | 1.1 + 2.1 | ✅ (implicit) |

**Note**: Section 5.8 (Artifact Lifecycle) clarifies that artifacts are an intra-turn concern. This is covered by the combination of Step Result Preservation (1.1) and Entity Context Model (2.1) — no separate implementation needed.

---

## Reference

- Full specification: [docs/v4-architecture-spec.md](docs/v4-architecture-spec.md)
- V3 design context: [docs/archive/architecture_v3_design.md](docs/archive/architecture_v3_design.md)
- Current architecture: [docs/architecture_overview.md](docs/architecture_overview.md)
