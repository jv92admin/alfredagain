# Context Management — Findings & Suggestions (1-page)

**Date:** 2026-01-15 (updated)  
**Status:** ✅ Phase A-D complete  
**Scope:** How Alfred displays "active entities", what data is actually usable by Act, and how to plan reads vs analyze.

---

## What Exists Today (Ground Truth)

- **DB**: authoritative for persisted entities (recipes, inventory, meal plans, shopping, tasks, etc.).
- **`SessionIdRegistry`** (`src/alfred/core/id_registry.py`): authoritative for
  - `ref` ↔ `UUID` translation (LLM never sees UUIDs)
  - deterministic lifecycle metadata (`read`, `created`, `generated`, `linked`, etc.)
  - temporal tracking (`ref_turn_last_ref`, etc.)
  - generated artifacts (`pending_artifacts`)

---

## The Three Things That Get Confused (and must stay distinct)

### 1) Kitchen Snapshot (dashboard)
- **What it is**: High-level summary counts + examples (e.g., “Recipes: 12 saved”).
- **What it’s good for**: Holding a conversation, knowing what domains exist.
- **What it is NOT**: A guarantee that any specific entity ref exists, or that any row data is available to Act.

### 2) Entities / Recent Context (registry refs)
- **What it is**: The **active entity set** derived from `SessionIdRegistry`:
  - **Recent (automatic window)**: last 2 turns (inclusive)
  - **Retained (Understand)**: older refs explicitly kept with a reason
  - Plus **Generated** (`gen_*`) pending artifacts
- **What it contains**: refs + labels + status (and small deterministic flags).
- **What it is NOT**: full record data (rows, instructions text, etc.).

### 3) Step Results (actual data returned this turn)
- **What it is**: Tool outputs from CRUD calls made during the current Act loop.
- **What it contains**: the actual records returned by the DB call (or generated content).
- **Important**: This is the **only** place Act can safely “analyze data” from.
- **Lifecycle**: these results are **per-turn**, and do not persist as a full dataset across turns.

---

## How “Active Entities” Are Displayed (current behavior)

### How the set is computed
`SessionIdRegistry.get_active_entities(turns_window=2)` produces:
- **Recent refs**: anything referenced within the last 2 turns (inclusive)
- **Retained refs**: older refs with `ref_active_reason`

### How Think sees it
Think uses `SessionIdRegistry.format_for_think_prompt()` which renders:
- **Generated Content**: `gen_*` refs (pending artifacts)
- **Recent Context (last 2 turns)**: refs + labels + status  
  - **Recipes include a deterministic tag**: `[read:summary]` vs `[read:full]` based on whether the last DB read included `instructions`.
- **Long Term Memory (retained from earlier)**: refs + labels + retention reasons

### How Act sees it
Act uses `SessionIdRegistry.format_for_act_prompt()` which renders:
- **Needs Creating**: generated artifacts whose main record isn’t created
- **Just Saved This Turn**: promoted artifacts retained for linked writes
- **This Turn**: refs first seen this turn
- **Recent Context (last 2 turns)**: refs + labels + status (recipes also show `[read:summary/full]`)
- **Long Term Memory**

Act additionally sees **Step Results** for the current turn inside its prompt’s “Data Available / Step History”.

---

## Findings (from real logs)

### Finding A: “Refs exist” was being interpreted as “data is loaded”
Think saw `recipe_3` in Recent Context and planned an `analyze` step to “show full details”.  
But Act had no recipe record content in Step Results, so it correctly refused to hallucinate.

### Finding B: Act analyze prompts were missing Entity Context entirely (bug)
In the analyzed session, the Act prompt for `step_type=analyze` did not include the “Entities in Context” section at all, unlike generate/read/write prompts.
This prevented even ref-level grounding inside analyze steps.

---

## Prompt Assembly Consistency Note (Analyze vs Others)

### What we observed
In `act_node()`, prompt assembly differed by `step_type` in a way that impacted entity/state awareness:
- **`read` / `write` prompts** included an “Entities in Context” section (from `SessionIdRegistry.format_for_act_prompt()`).
- **`generate` prompts** included an “Entities in Context” section (explicitly injected).
- **`analyze` prompts** were previously built **without** the “Entities in Context” section (only “Data Available” + conversation), which made analyze steps feel “blind” to active refs even when the registry knew them.

### Design feedback / principle
It’s correct that some prompt sections depend on the step type (e.g., schema for CRUD steps, generation guidance for generate steps).  
However, **entity/state management context should not vary by step type**:
- Every Act step benefits from seeing the current active refs + their statuses (recent vs retained vs generated, etc.).
- The entity registry is the deterministic “handles layer” that keeps the system consistent across steps.

### What we changed
We now inject “Entities in Context” into the analyze prompt as well, so entity refs and status are always present regardless of step type.

---

## Suggestions (prioritized)

### 1) Persist step_results across turns (key fix)

**The root cause:** `step_results` is cleared when Think runs (`step_results: {}`), losing prior turn data.

**The fix:** Store step_results in `conversation["turn_step_results"]` (last 2 turns):

| Where | Change |
|-------|--------|
| **Summarize** (end of turn) | Save `step_results` → `conversation["turn_step_results"][turn_num]`, keep last 2 |
| **Think** (start of turn) | Reset `step_results: {}` for THIS turn only (unchanged) |
| **Act prompt builder** | Pull from stored turn results + current step results |

**Result:**
- Act sees full data for all active entities (last 2 turns + current)
- Same table format as "This Turn" entities — no redesign needed
- Think still sees refs only (cognitive load stays low)

### 2) Consolidate entity display for Act

Use ONE consolidated table for all active entity data:

```
## Active Entities (Full Data)

| ref | label | type | data_summary |
|-----|-------|------|--------------|
| recipe_1 | Spicy Cod Masala | recipe | 45min, indian, 4 servings |
| recipe_2 | Indian-Inspired Cod Curry | recipe | 60min, indian, 4 servings |
| inv_1 | frozen cauliflower | inv | 500g, freezer |
```

- **Recent Context (2 turns):** Full data in table
- **Long Term Memory:** Refs + labels only (no data row)
- **Deduped:** Ref appears once even if mentioned in multiple narratives

### 3) Refactor common Act prompt sections

Entity context + conversation history should be COMMON scaffolding for all step types.
Step-type-specific sections (schema, generation guidance) are injected separately.

```python
# Common base (all step types)
common_sections = build_common_act_context(state, session_registry)

# Step-type specific
if step_type == "read":
    specific = build_read_sections(...)
elif step_type == "analyze":
    specific = build_analyze_sections(...)
# etc.

user_prompt = f"{common_sections}\n\n{specific}"
```

---

## Implementation Checklist

- [x] **Summarize:** Save `step_results` to `conversation["turn_step_results"][turn_num]` ✅
- [x] **Summarize:** Prune to last 2 turns ✅
- [x] **Act:** New function `_build_enhanced_entity_context()` pulls from turn_step_results + current ✅
- [x] **Act:** Consolidated "Active Entities (Full Data)" section ✅
- [x] **Act:** Refactor prompt assembly via `build_act_user_prompt()` ✅
- [x] **Act:** Full instructions shown (not just count) ✅
- [x] **Turn counter:** Fixed double-increment bug ✅
- [x] **Act Quick:** Tightened criteria in Understand prompt ✅
- [x] **Think:** Unchanged (refs only) ✅

---

## Deduplication Principle

**Entity data appears ONCE in the consolidated table, NOT duplicated in narrative.**

| Layer | What it contains | Example |
|-------|------------------|---------|
| **Full Data Table** | One row per active entity, most recent data | `recipe_3: Malaysian Sambal... [45min, thai, 4 servings]` |
| **Narrative Layer** | What *happened* to entities (actions, edits) | "Turn 4: read recipe_3. Turn 5: edited recipe_3 instructions." |

**Key rules:**
1. Entities enter full data table through **reads** (or creates/generates)
2. When entities are **referenced** (but not re-read), they trigger narrative updates only
3. If entity was read turn N-1 and edited turn N → show deduped data (latest version), narrative shows edit history
4. No duplicated rows — ref appears once in data table even if mentioned across multiple turns

**Why this matters:**
- Saves tokens (no repeated full records)
- Clear separation: data vs history
- Act knows what data is available vs what happened

---

## TODO: Documentation & Implementation

### 1) Structure docs ✅ DONE

| Doc | Purpose | Location |
|-----|---------|----------|
| **Think Prompt Structure** | Section-by-section breakdown, sources, turn windows | [`docs/prompts/think-prompt-structure.md`](prompts/think-prompt-structure.md) |
| **Act Prompt Structure** | Common sections, step-type sections, entity context, output contract | [`docs/prompts/act-prompt-structure.md`](prompts/act-prompt-structure.md) |

**Key findings documented:**
- Think sees refs + labels only (cognitive load savings)
- Act sees refs + labels but NOT full data for prior turns (gap — Phase A/B will fix)
- ~~Three separate templates in `act.py` cause maintenance issues~~ → ✅ FIXED: Centralized in `injection.py`
- ~~Entity context sometimes missing from analyze steps~~ → ✅ FIXED: Now in `_build_common_sections()`

### 2) Implementation (next steps)

**Phase A: Persist step_results across turns** ✅ DONE (2026-01-15)
- [x] `summarize.py`: Save `step_results` → `conversation["turn_step_results"][turn_num]`
- [x] `summarize.py`: Prune to last 2 turns via `_serialize_step_results()`

**Phase B: Wire full entity data to Act** ✅ DONE (2026-01-15)
- [x] `act.py`: Added `_build_enhanced_entity_context()` that merges:
  - Current turn's `step_results`
  - Prior turns' `turn_step_results` (from conversation)
- [x] Deduplication: latest version wins (newer turn overwrites older)
- [x] Audit: Understand can't promote long-term → active with data (only sets flag, not data)

**Phase C: Refactor Act prompt assembly** ✅ DONE (2026-01-15)
- [x] `injection.py`: Added `build_act_user_prompt()` as main entry point
- [x] `injection.py`: Added `_build_common_sections()` for shared sections
- [x] `injection.py`: Added `_build_step_type_sections()` for step-specific sections
- [x] `act.py`: Now calls `build_act_user_prompt()` (eliminated ~280 lines of duplicate templates)

**Phase D: Documentation** ✅ DONE (2026-01-15)
- [x] Add docstrings to `injection.py` referencing `docs/prompts/act-prompt-structure.md`
- [ ] Add docstrings to `think.py` referencing `docs/prompts/think-prompt-structure.md`
- [ ] Add docstrings to `entity.py`, `builders.py` explaining data flow

### 3) Files to audit for prompt assembly

| File | What to check | Status |
|------|---------------|--------|
| `src/alfred/prompts/injection.py` | `build_act_user_prompt()`, common/step-type sections | ✅ Refactored |
| `src/alfred/graph/nodes/act.py` | Context gathering, calls `build_act_user_prompt()` | ✅ Simplified |
| `src/alfred/graph/nodes/think.py` | What context Think receives | Audit pending |
| `src/alfred/context/builders.py` | How context is assembled per node | Audit pending |
| `src/alfred/context/entity.py` | EntitySnapshot structure, format modes | Phase B |
| `src/alfred/core/id_registry.py` | `format_for_act_prompt()`, `format_for_think_prompt()` | Audit pending |

---

## One-line takeaway
**Act sees full data for active entities (last 2 turns). Think sees refs only. Step results persist in conversation. Dedupe data, not narrative.**

