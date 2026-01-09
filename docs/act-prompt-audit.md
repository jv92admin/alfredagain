# Act Prompt Architecture Audit

**Date:** 2026-01-08  
**Status:** Draft  
**Purpose:** Map current Act prompt structure, identify issues, propose fixes

---

## CRITICAL BUGS (Fix First)

| Bug | Impact | Root Cause | Status |
|-----|--------|------------|--------|
| `gen_recipe_1` shown as "pending" even after `recipe_3` created | LLM confused, two refs for same entity | CRUD created new ref instead of promoting gen_* | ✅ Fixed (auto-match by label in register_created) |
| Analyze step data hidden as "(use retrieve_step)" | Next step can't see analysis conclusions | `_format_step_results` didn't handle analyze step_type | ✅ Fixed |
| `note_for_next_step` ignored for analyze steps | Analysis conclusions don't flow forward | Code only extracted notes for read/write | ✅ Fixed |
| Archives show stale "generated_recipes" after save | Confusing context | Archive keys not updated/cleared after save | ✅ Fixed (cleared after save) |
| ~~Analyze steps don't see USER PROFILE~~ | ~~Can't consider allergies/preferences in comparisons~~ | ~~`profile_section` only added for generate, not analyze~~ | ✅ Already works! (verified in 20_act.md:254-259) |
| UUID shown in `recipe_ingredients` grouping | UUIDs leaking to prompt | db_create didn't translate FK fields | ✅ Fixed (FKs now translated in output) |
| Missing newline before "Entities in Context" | Section header runs into prior content | Template concatenation missing `\n` | ✅ Fixed |

---

## COMPLETED FIXES (This Session)

### Phase 1: Dead Code Removal
- Removed `turn_entities_section` (always empty, never used)
- Removed `id_mapping_section` (ID translation now internal to SessionIdRegistry)
- Removed unused `context_block` template

### Phase 2: System Prompt Cleanup
- Removed "V4 Context Sections" meta-explanation (35 lines) from base.md
- Removed "What Already Happened" explanation (8 lines) from base.md
- Added "Simple Refs Only" as concise principle #9
- **base.md: 113 → 65 lines (42% reduction)**

### Phase 3: Bug Fixes
- `pending_artifacts` now cleared after successful db_create by subdomain
- Archive keys (generated_recipes, generated_meal_plan) cleared after save
- USER PROFILE already worked for analyze (verified, no change needed)

### Phase 4: Prompt Restructure (read/write)
- Renamed "What Already Happened (This Step)" → "Step History"
- Combined this step's progress + previous steps into unified "Step History" section
- Renamed "Working Set" → "Entities in Context" for clarity
- Split "Content to Save" → dedicated "Pending Generated Content" section (only when relevant)
- Removed duplicate archive display

### Phase 5: Example Deduplication
- Removed "Smart Shopping List Updates" from shopping schema fallback (duplicated contextual_examples)
- Fixed outdated DELETE instruction in recipes schema (now correctly says CASCADE)

### Phase 6: Entity Transition Fixes (Latest)
- **gen→saved promotion**: When saving a generated entity, CRUD now auto-matches pending `gen_*` artifact by label and promotes it (same ref, no duplicate `recipe_3`)
- **FK translation in db_create output**: Foreign key fields like `recipe_id` now translated to refs in create output
- **Formatting fix**: Added missing newline between "Patterns for This Step" and "## Entities in Context"

---

## Token Budget Analysis

| Component | Current | Target | Savings |
|-----------|---------|--------|---------|
| System Prompt | ~330 lines | ~100 lines | 230 lines |
| User Prompt (read/write) | ~650 lines | ~200 lines | 450 lines |
| **Total** | **~980 lines** | **~300 lines** | **~680 lines (70%)** |

---

## Overview

Act prompts are assembled from multiple sources:
1. **System Prompt** - Static instructions loaded from markdown files
2. **User Prompt** - Dynamic context assembled per step from multiple functions

The structure varies by step type (read/write vs analyze/generate).

### Quick Reference: Prompt Log → Code Mapping

From `prompt_logs/20260108_164355/22_act.md` (Step 5, write, shopping):

| Prompt Lines | Section | Source Code |
|--------------|---------|-------------|
| 1-125 | System: base.md | `_get_system_prompt()` |
| 126-200 | System: crud.md | `_get_system_prompt()` |
| 200-330 | System: write.md | `_get_system_prompt()` |
| 330-340 | STATUS table | `act.py:1103-1108` |
| 340-350 | Current Step | `act.py:1112-1116` |
| 357-365 | What Already Happened | `_format_current_step_results()` |
| 368-448 | Working Set | `session_registry.format_for_act_prompt()` |
| 452-530 | Schema + Examples | `get_schema_with_fallback()` + `get_contextual_examples()` |
| 531-650 | Content to Save | `pending_artifacts_section` + `prev_step_section` + `archive_section` |
| 720-732 | Context | `format_full_context()` |

---

## Part 1: System Prompt Assembly

**Source:** `act.py::_get_system_prompt(step_type)`

### Current Structure

```
┌─────────────────────────────────────────────────────────────┐
│ 1. prompts/act/base.md        (~115 lines)                  │
│    - Role definition                                        │
│    - Core Principles (8 rules)                              │
│    - "V4 Context Sections" explanation                      │
│    - Actions table                                          │
│    - Exit Contract                                          │
│    - "What Already Happened" explanation                    │
├─────────────────────────────────────────────────────────────┤
│ 2. prompts/act/crud.md        (~70 lines) [read/write only] │
│    - Tools table (db_read, db_create, etc.)                 │
│    - Filter syntax                                          │
│    - Filter patterns                                        │
│    - Operators reference                                    │
├─────────────────────────────────────────────────────────────┤
│ 3. prompts/act/{step_type}.md (~50-100 lines)               │
│    - read.md: Query patterns, empty handling                │
│    - write.md: Batch ops, FK handling, linked tables        │
│    - generate.md: Creative guidance, output format          │
│    - analyze.md: Data comparison, no DB calls               │
└─────────────────────────────────────────────────────────────┘
```

### Issues in System Prompt

| Section | Lines | Issue | Severity | Fix |
|---------|-------|-------|----------|-----|
| "V4 Context Sections" | base.md:33-67 | Meta-explanation of sections that are self-explanatory. Wastes ~35 lines explaining Working Set, Batch Manifest, ID References, Content to Save. LLM doesn't need to be told what sections mean - just use them. | Medium | **DELETE** entire section. Sections are self-documenting. |
| "What Already Happened" explanation | base.md:106-124 | Explains what the section shows - redundant since user prompt has the actual content with clear headers. | Low | **DELETE** - section header in user prompt is sufficient. |
| crud.md always injected for read/write | act.py:358 | Filter syntax appears in both crud.md AND schema injection. Duplication. | Low | Keep in crud.md, remove from schema injection OR vice versa. |
| `context_block` variable | act.py:881-893 | Built but **NEVER USED** for read/write steps. Only analyze/generate use it (and they build their own). | Low | **DELETE** - dead code for read/write path. |

### Recommended System Prompt Structure

```
┌─────────────────────────────────────────────────────────────┐
│ 1. base.md (~60 lines - TRIMMED)                            │
│    - Role (5 lines)                                         │
│    - Core Principles (8 rules, 25 lines)                    │
│    - Actions table (15 lines)                               │
│    - Exit Contract (15 lines)                               │
├─────────────────────────────────────────────────────────────┤
│ 2. crud.md (~50 lines) [read/write only]                    │
│    - Tools table                                            │
│    - Filter operators (compact)                             │
├─────────────────────────────────────────────────────────────┤
│ 3. {step_type}.md (unchanged)                               │
└─────────────────────────────────────────────────────────────┘
```

**Savings:** ~55 lines from system prompt

---

## Part 2: User Prompt Assembly - ANALYZE Steps

**Source:** `act.py` lines 916-976

### Current Structure

```
┌─────────────────────────────────────────────────────────────┐
│ 1. subdomain_header                                         │
│    Source: get_full_subdomain_content(subdomain, "analyze") │
│    Content: SUBDOMAIN_INTRO + SUBDOMAIN_PERSONAS["analyze"] │
│    Example: "Domain: Inventory" + "Pantry Manager (Compare)"│
├─────────────────────────────────────────────────────────────┤
│ 2. STATUS table                                             │
│    | Step | N of M |                                        │
│    | Goal | {step description} |                            │
│    | Type | analyze (no db calls) |                         │
│    | Today | YYYY-MM-DD |                                   │
├─────────────────────────────────────────────────────────────┤
│ 3. profile_section (optional)                               │
│    Source: get_cached_profile() + format_profile_for_prompt │
│    Content: User constraints, equipment, preferences        │
├─────────────────────────────────────────────────────────────┤
│ 4. ## 1. Task                                               │
│    User said: "{user_message}"                              │
│    Your job this step: **{step description}**               │
├─────────────────────────────────────────────────────────────┤
│ 5. analyze_guidance                                         │
│    Source: get_contextual_examples(..., step_type="analyze")│
│    Content: Domain-specific analysis patterns               │
├─────────────────────────────────────────────────────────────┤
│ 6. ## 2. Data Available                                     │
│    {turn_entities_section}  ← ALWAYS EMPTY (bug)            │
│    {prev_step_section}                                      │
│    {archive_section}                                        │
├─────────────────────────────────────────────────────────────┤
│ 7. ## 3. Context                                            │
│    {conversation_section}                                   │
├─────────────────────────────────────────────────────────────┤
│ 8. ## DECISION                                              │
│    step_complete with result_summary and data               │
└─────────────────────────────────────────────────────────────┘
```

### Issues in ANALYZE Prompt

| Section | Issue | Severity | Fix |
|---------|-------|----------|-----|
| `turn_entities_section` | **ALWAYS EMPTY** - set to "" on line 875, never populated. Dead code reference. | High | ✅ **REMOVED** |
| No Working Set | Analyze steps don't see the SessionIdRegistry entities. May need entity refs for analysis. | Medium | Consider adding if needed. |
| `note_for_next_step` not shown | Analyze steps should see notes from prior steps. | High | ✅ **FIXED** |
| `prev_step_section` shows "(use retrieve_step)" for prior analyze | Prior analyze data was hidden. | High | ✅ **FIXED** |
| ~~No USER PROFILE~~ | ~~Analyze steps compare data but don't see user allergies/preferences!~~ | ~~Critical~~ | ✅ **Already works!** (profile_section IS in analyze template) |

### Recommended ANALYZE Structure

```
## STATUS (keep as-is)
## Your Job: {step description}
## USER PROFILE ← MANDATORY for analyze!
  - Allergies, dietary restrictions (for substitution logic)
  - Preferences (for prioritization)
## Data to Analyze
  - Prior step results (with full data)
  - Prior step note (if any)
  - Entities in context (from registry)
## Context (conversation)
## DECISION
```

**Why USER PROFILE is critical for analyze:**
- Comparing inventory to recipe → need to know allergies for substitutions
- Comparing shopping list to inventory → need to know preferences for deduplication
- Any "what's missing" logic → need constraints to filter results

---

## Part 3: User Prompt Assembly - GENERATE Steps

**Source:** `act.py` lines 978-1034

### Current Structure (from 09_act.md - Step 3 Generate)

```
┌─────────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT                                               │
│ 1. base.md (~125 lines) - includes V4 meta-explanation      │
│ 2. generate.md (~90 lines) - NO crud.md for generate!       │
├─────────────────────────────────────────────────────────────┤
│ USER PROMPT                                                 │
├─────────────────────────────────────────────────────────────┤
│ 1. subdomain_header (~90 lines!)                            │
│    = SUBDOMAIN_INTRO[recipes] + PERSONAS[recipes][generate] │
│    "Creative Chef with Restaurant & Cookbook Expertise"     │
│    Flavor synergies, techniques, chef's tips, skill levels  │
├─────────────────────────────────────────────────────────────┤
│ 2. STATUS table (4 rows)                                    │
├─────────────────────────────────────────────────────────────┤
│ 3. USER PROFILE (5 lines) ← GOOD: prominent placement!      │
│    Constraints, Equipment, Likes, Schedule, Vibes           │
├─────────────────────────────────────────────────────────────┤
│ 4. ## 1. Task                                               │
├─────────────────────────────────────────────────────────────┤
│ 5. ## Generation Guidance (~20 lines)                       │
│    Source: get_contextual_examples(..., step_type="generate")│
│    Recipe structure, ingredient naming rules                │
├─────────────────────────────────────────────────────────────┤
│ 6. ## 2. Data Available                                     │
│    Previous Step Results (inventory list - 50 items!)       │
│    NO turn_entities_section (not in generate template)      │
│    NO archive_section (not relevant for generate)           │
├─────────────────────────────────────────────────────────────┤
│ 7. ## 3. Context (conversation)                             │
├─────────────────────────────────────────────────────────────┤
│ 8. ## DECISION                                              │
└─────────────────────────────────────────────────────────────┘
```

### What's GOOD About Generate Prompts

| Aspect | Why It Works |
|--------|--------------|
| No Working Set | Generate creates NEW entities - doesn't need existing refs |
| No "Content to Save" | Nothing to save yet - that's for write step |
| No schema injection | No DB ops in generate |
| USER PROFILE prominent | Essential for personalization, shown early |
| Data flows clearly | Inventory → Generate is obvious |
| No archive confusion | Archives not needed for generation |

**Key insight:** Generate prompts are **much cleaner** than read/write. The mess is concentrated in read/write steps.

### Issues in GENERATE Prompt

| Section | Issue | Severity | Fix |
|---------|-------|----------|-----|
| System: "V4 Context Sections" | Still in base.md (lines 45-78) - unnecessary | Low | Delete from base.md |
| System: "What Already Happened" | Still in base.md (lines 118-125) - redundant | Low | Delete from base.md |
| `temp_id` in example | Recipe structure example shows `temp_id` (line 286) but we use `gen_recipe_1` now | Low | Update generate.md example |
| Subdomain header is 90 lines | "Creative Chef" persona is comprehensive but long | Medium | Consider trimming or making conditional |
| Ingredient naming duplicated | Appears in generate.md AND contextual guidance | Low | Pick one location |
| No explicit "HARD CONSTRAINTS" header | Allergies in profile but not visually separated | Medium | Add explicit section |

### Recommended GENERATE Structure

```
## STATUS
## Your Job: {step description}
## HARD CONSTRAINTS (allergies, dietary - NEVER violate)
  - Shellfish: EXCLUDE
  - Diet: no breakfast
## Inspiration
  - Cuisines: indian, mexican, thai, mediterranean
  - Vibes: chicken, cod, paneer, chickpeas, eggs
  - Equipment: air fryer, stove top, pots, instant pot
  - Skill: beginner
## Available Ingredients (from prior step)
  {prev_step_section} - formatted as ingredient list
## Context (conversation)
## DECISION
```

**Generate is the MODEL** - read/write should aspire to this clarity.

### Generate vs Read/Write Comparison

| Aspect | Generate (09_act.md) | Read/Write (22_act.md) | Winner |
|--------|---------------------|------------------------|--------|
| Total lines | ~440 | ~900 | Generate |
| User prompt lines | ~220 | ~400 | Generate |
| Sections | 8 clear sections | 13+ fragmented sections | Generate |
| Entity display | None needed | Working Set + prev_step + archives (triple!) | Generate |
| Schema | None needed | Schema + examples + contextual_examples (triple!) | Generate |
| Data flow | Inventory → Generate (clear) | prev_step buried under "Content to Save" | Generate |
| Dead code | Minimal | 3 unused variables | Generate |
| Profile visibility | Prominent, early | Not shown in read/write OR analyze! | Generate |

**Conclusion:** Read/write prompts have ~2x the tokens with worse organization.

### Why Generate Avoids the Mess

Generate steps have a fundamentally simpler data model:

```
INPUT:  Prior step results (inventory, user profile)
        ↓
OUTPUT: New content (recipes, meal plans)
        ↓
NEXT:   Write step saves it
```

No need for:
- Working Set (creates new refs, doesn't use existing)
- Schema (no DB ops)
- "Content to Save" (nothing to save yet)
- Archives (no cross-turn retrieval)
- ID mappings (system assigns gen_* refs automatically)

Read/write has circular dependencies that cause the mess:
- Need entities from prior steps (prev_step_section)
- Need entities from Working Set (duplicates prior steps!)
- Need pending artifacts (from generate step)
- Need archives (cross-turn content)
- Need schema (for CRUD ops)
- Need examples (duplicates schema!)

**Solution:** De-duplicate read/write, don't flatten. Schema is essential.

**Specific fixes for read/write:**
1. **Remove duplicate entity displays** - Pick ONE: Working Set OR prev_step_section entity refs, not both
2. **Remove duplicate examples** - Pick ONE: schema examples OR contextual_examples, not both
3. **Separate concerns** - "Content to Save" should ONLY have pending artifacts, not prior step history
4. **Add USER PROFILE to analyze** - Critical for comparison logic (allergies, preferences)
5. **Keep schema** - Essential for CRUD, can't remove

---

## Part 4: User Prompt Assembly — READ/WRITE Steps (RESTRUCTURED)

**New clean structure:**

1. **STATUS** - Step #, goal, type, progress, date
2. **Current Step** - User message + job description  
3. **Step History** - This step's tool results + previous step data (unified)
4. **Schema** - CRUD reference for this subdomain
5. **Entities in Context** - Working Set (renamed for clarity)
6. **Pending Generated Content** - Only shown for write steps with pending artifacts
7. **Context** - Conversation history
8. **DECISION** - Action options

**Key improvements:**
- Removed "What Already Happened" confusion → renamed to "Step History"
- Unified this step progress + previous step data into one section
- Removed duplicate entity displays
- Pending artifacts now in dedicated section (only when relevant)
- Archive section removed (cleared on save anyway)

---

### Original Issues (PRE-RESTRUCTURE)

**Source:** `act.py` lines 1036-1160

### Current Structure (THE MESS)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. dynamic_header                                           │
│    Source: get_full_subdomain_content(subdomain, step_type) │
│    Content: SUBDOMAIN_INTRO + SUBDOMAIN_PERSONAS[step_type] │
├─────────────────────────────────────────────────────────────┤
│ 2. ## STATUS table                                          │
│    | Step | N of M |                                        │
│    | Goal | {step description} |                            │
│    | Type | read/write |                                    │
│    | Progress | N tool calls → Last: db_X returned Y |      │
│    | Today | YYYY-MM-DD |                                   │
├─────────────────────────────────────────────────────────────┤
│ 3. prev_note_section (conditional)                          │
│    ## Previous Step Note                                    │
│    {note from prior step}                                   │
├─────────────────────────────────────────────────────────────┤
│ 4. ## 1. Current Step                                       │
│    User said: "{user_message}"                              │
│    Your job this step: **{step description}**               │
├─────────────────────────────────────────────────────────────┤
│ 5. batch_manifest_section (conditional)                     │
│    Shows batch progress if multi-item operation             │
├─────────────────────────────────────────────────────────────┤
│ 6. ## 2. What Already Happened (This Step)                  │ ← CONFUSING NAME
│    {this_step_section}                                      │
│    Shows tool calls made THIS STEP only                     │
├─────────────────────────────────────────────────────────────┤
│ 7. ## 3. Working Set                                        │ ← TOO EARLY, DUPLICATES
│    {working_set_section}                                    │
│    Source: session_registry.format_for_act_prompt()         │
│    Shows ALL entities (pending, this turn, prior turns)     │
├─────────────────────────────────────────────────────────────┤
│ 8. {id_mapping_section}                                     │ ← ALWAYS EMPTY (dead)
├─────────────────────────────────────────────────────────────┤
│ 9. ## 4. Schema ({subdomain})                               │
│    {subdomain_schema}                                       │
│    Source: get_schema_with_fallback()                       │
│    Includes: tables, columns, filter syntax, enums          │
├─────────────────────────────────────────────────────────────┤
│10. {contextual_examples}                                    │ ← DUPLICATES SCHEMA EXAMPLES
│    Source: get_contextual_examples()                        │
│    Adds patterns like "Smart Add Pattern", "Recipe Search"  │
├─────────────────────────────────────────────────────────────┤
│11. ## 5. Content to Save                                    │ ← WRONG LABEL, MIXED CONTENT
│    {pending_artifacts_section}  ← gen_* not yet saved       │
│    {prev_step_section}          ← HISTORICAL RESULTS (why here??)
│    {archive_section}            ← cross-turn storage        │
├─────────────────────────────────────────────────────────────┤
│12. ## 6. Context                                            │
│    {conversation_section}                                   │
├─────────────────────────────────────────────────────────────┤
│13. ## DECISION                                              │
│    Action options with JSON examples                        │
└─────────────────────────────────────────────────────────────┘
```

### Issues in READ/WRITE Prompt

| # | Section | Issue | Severity | Fix |
|---|---------|-------|----------|-----|
| 1 | `id_mapping_section` | **ALWAYS EMPTY** - Dead code, set to "" on line 1101 | Low | **DELETE** variable and reference |
| 2 | Working Set placement | Shows entities BEFORE schema. Schema should come first (tools reference). | Medium | Move Working Set after Schema |
| 3 | Working Set content | Duplicates entity info from `prev_step_section`. If Step 1 created `recipe_1`, it appears in BOTH Working Set AND "Content to Save" prev_step results. | High | **MERGE** - Working Set should reference step results, not duplicate |
| 4 | "What Already Happened" name | Confusing - sounds like prior steps, but only shows THIS step's tool calls | Medium | Rename to "This Step's Tool Calls" or "Progress" |
| 5 | "Content to Save" label | Misleading for step 5 (add to shopping list). Contains: pending artifacts + historical step results + archives. Only pending artifacts are "content to save". | High | **SPLIT** into: "Pending Artifacts" (gen_* content) + "Prior Step Results" (separate section) |
| 6 | `prev_step_section` in wrong place | Historical step results buried under "Content to Save" | High | Move to dedicated "What Happened in Prior Steps" section |
| 7 | `prev_step_section` shows "(use retrieve_step)" | For analyze steps, data was hidden. We fixed this but retrieve_step still referenced. | Medium | Remove retrieve_step references entirely |
| 8 | `archive_section` shows stale refs | After recipe is saved, still shows "generated_recipes" key. Should show saved recipe or clear. | High | Update archive after save, or remove archives concept |
| 9 | `contextual_examples` duplicates schema | Schema injection already has examples. contextual_examples adds more. Redundant. | Medium | Either: (a) remove examples from schema, keep contextual_examples, OR (b) vice versa |
| 10 | `pending_artifacts_section` shows saved recipe | gen_recipe_1 shown even after recipe_1 was created. Registry didn't clear it. | Critical | **BUG** - registry.register_created() should clear pending_artifacts[gen_ref] |
| 11 | No unified "What Happened" flow | This step results and prior step results are in completely separate places | High | Combine into single "Execution History" or "What Happened" section |

### Entity Tracking Bug Details (Issue #10)

**Symptom:** Step 5 prompt shows:
- Working Set: `recipe_1 | recipe | ... | created`
- Content to Save: `gen_recipe_1: Indian-Inspired Cod Curry...` (full JSON)

**Problem:** Both exist! The gen_recipe_1 should have been cleared when recipe_1 was created.

**Root Cause:** In `id_registry.py::register_created()`:
```python
# Clear the pending artifact content - it's now saved in DB
if gen_ref in self.pending_artifacts:
    del self.pending_artifacts[gen_ref]
```

This code exists but may not be called if `gen_ref` doesn't match. Need to trace the flow.

---

## Part 5: Injection Sources Reference

### personas.py — Domain Knowledge

| Dict | Purpose | Example Content |
|------|---------|-----------------|
| `SUBDOMAIN_INTRO` | General domain description | `"**Domain: Shopping**\nShopping list items. Check against inventory before adding."` |
| `SUBDOMAIN_PERSONAS` | Step-type-specific behavioral guidance | `[shopping][write]`: "Normalize names, check duplicates, consolidate quantities" |

**How it's assembled:**
```python
get_full_subdomain_content(subdomain, step_type)
  → SUBDOMAIN_INTRO[subdomain] + SUBDOMAIN_PERSONAS[subdomain][step_type]
```

### examples.py — Contextual Patterns

| Function | Triggers On | Example Output |
|----------|-------------|----------------|
| `get_contextual_examples()` | Verbs in step description | "add" → Smart Add Pattern (check existing first) |
| `_get_analyze_guidance()` | step_type="analyze" | Domain-specific comparison instructions |
| `_get_generate_guidance()` | step_type="generate" | Creative guidance for recipes/meals |

**Issue:** Examples often duplicate what's in schema injection AND write.md. Triple coverage.

### schema.py — Actual DB Schema

| Function | Returns | Size |
|----------|---------|------|
| `get_schema_with_fallback()` | Tables, columns, types, enums, filter syntax, examples | ~80-100 lines per subdomain |

**Issue:** Includes filter syntax (also in crud.md) and examples (also in contextual_examples).

### id_registry.py — Entity Display

| Method | Called By | Format |
|--------|-----------|--------|
| `format_for_act_prompt(step_idx)` | Act node | `\| ref \| type \| label \| status \|` with step context |
| `format_for_think_prompt()` | Think node | Grouped by type with counts |
| `format_for_understand_prompt()` | Understand node | Full registry for curation decisions |

**Current issue:** `format_for_act_prompt()` shows entities redundantly with `prev_step_section`.

---

## Part 6: Proposed Clean Structure for READ/WRITE

```
┌─────────────────────────────────────────────────────────────┐
│ ## STATUS                                                   │
│ | Step | N of M |                                           │
│ | Goal | {step description} |                               │
│ | Type | read/write |                                       │
│ | Progress | N tool calls |                                 │
│ | Today | YYYY-MM-DD |                                      │
├─────────────────────────────────────────────────────────────┤
│ ## Your Job                                                 │
│ **{step description}**                                      │
│ (Note from prior step: {prev_note} if any)                  │
├─────────────────────────────────────────────────────────────┤
│ ## Tools & Schema                                           │
│ {subdomain_schema} (tables, columns, filters)               │
│ {contextual_examples} (relevant patterns only)              │
├─────────────────────────────────────────────────────────────┤
│ ## What Happened                                            │
│ ### Prior Steps                                             │
│ {prev_step_section} (with step numbers and key data)        │
│ ### This Step                                               │
│ {this_step_section} (tool calls made so far)                │
├─────────────────────────────────────────────────────────────┤
│ ## Available Entities                                       │  
│ {working_set_section} (refs with status tied to steps)      │
│ e.g., "recipe_1 | recipe | Cod Curry | created (step 1)"    │
├─────────────────────────────────────────────────────────────┤
│ ## Pending Artifacts (only for write steps with gen_* refs) │
│ {pending_artifacts_section} (full JSON to save)             │
├─────────────────────────────────────────────────────────────┤
│ ## Context                                                  │
│ {conversation_section}                                      │
├─────────────────────────────────────────────────────────────┤
│ ## DECISION                                                 │
│ Action options                                              │
└─────────────────────────────────────────────────────────────┘
```

### Key Changes

1. **Remove dead code:** `id_mapping_section`, `turn_entities_section`
2. **Rename sections:** "What Already Happened" → "This Step" under "What Happened"
3. **Unify history:** Prior steps + This step under one "What Happened" section
4. **Relocate Working Set:** After Schema (tools first, then data)
5. **Split "Content to Save":** Pending Artifacts only (for gen_* content), move prev_step_section to "What Happened"
6. **Remove archives:** Or update after save (not worth the complexity)
7. **Tie entities to steps:** Working Set shows which step created/read each entity

---

## Part 7: Action Items

### Phase 1: Dead Code Removal (Low Risk)
- [ ] Remove `turn_entities_section` variable and references
- [ ] Remove `id_mapping_section` variable and references
- [ ] Remove unused `context_block` for read/write (only used by analyze/generate)

### Phase 2: System Prompt Cleanup (Low Risk)
- [ ] Delete "V4 Context Sections" from base.md (lines 33-67)
- [ ] Delete "What Already Happened" explanation from base.md (lines 106-124)

### Phase 3: Bug Fixes (Medium Risk)
- [ ] Fix `pending_artifacts` not clearing after save (trace register_created flow)
- [ ] Fix archive references after save (or remove archives)
- [ ] Ensure `note_for_next_step` flows for all step types (done)
- [ ] Ensure analyze step data shown to next step (done)

### Phase 4: Prompt Restructure (Higher Risk)
- [ ] Rename "What Already Happened (This Step)" → "This Step's Progress"
- [ ] Create unified "What Happened" section (prior + this)
- [ ] Move Working Set after Schema
- [ ] Split "Content to Save" into "Pending Artifacts" only
- [ ] Update analyze/generate prompts to use Working Set if needed

### Phase 5: Deduplication (Medium Risk)
- [ ] Audit schema injection vs contextual_examples for duplicate examples
- [ ] Consider removing one source of examples

---

## Appendix A: File References

| File | Purpose |
|------|---------|
| `src/alfred/graph/nodes/act.py` | Main prompt assembly |
| `src/alfred/prompts/injection.py` | build_act_prompt (partially used) |
| `src/alfred/prompts/personas.py` | SUBDOMAIN_INTRO, SUBDOMAIN_PERSONAS |
| `src/alfred/prompts/examples.py` | get_contextual_examples |
| `src/alfred/tools/schema.py` | get_schema_with_fallback |
| `src/alfred/core/id_registry.py` | SessionIdRegistry format methods |
| `prompts/act/base.md` | System prompt base |
| `prompts/act/crud.md` | CRUD tools reference |
| `prompts/act/read.md` | Read step instructions |
| `prompts/act/write.md` | Write step instructions |
| `prompts/act/generate.md` | Generate step instructions |

---

## Appendix B: Key Functions in act.py

| Function | Lines | Purpose | Called For |
|----------|-------|---------|------------|
| `_get_system_prompt(step_type)` | 343-370 | Assembles system prompt from md files | All steps |
| `_format_step_results()` | 373-520 | Formats prior step results for context | All steps |
| `_format_current_step_results()` | 593-650 | Formats THIS step's tool calls | All steps |
| `act_node()` | 710-1500 | Main Act orchestration | All steps |
| `act_quick_node()` | 1580-1720 | Simplified single-op execution | Quick mode only |

### Variables Built in act_node (read/write path)

| Variable | Line | Source | Issue |
|----------|------|--------|-------|
| `prev_step_section` | 814-818 | `_format_step_results()` | Shown in wrong place ("Content to Save") |
| `this_step_section` | 820 | `_format_current_step_results()` | OK |
| `conversation_section` | 823-825 | `format_full_context()` | OK |
| `archive_section` | 828-836 | Manual string build | Stale after saves |
| `pending_artifacts_section` | 845-860 | `session_registry.get_all_pending_artifacts()` | Shows even after save |
| `working_set_section` | 873 | `session_registry.format_for_act_prompt()` | Duplicates prev_step_section |
| `id_mapping_section` | 874 | Hardcoded `""` | **DEAD CODE** |
| `turn_entities_section` | 875 | Hardcoded `""` | **DEAD CODE** |
| `context_block` | 881-893 | Manual string build | **DEAD CODE** (not used for read/write) |
| `subdomain_schema` | 1038 | `get_schema_with_fallback()` | OK |
| `subdomain_content` | 1041 | `get_full_subdomain_content()` | OK |
| `contextual_examples` | 1049-1054 | `get_contextual_examples()` | Duplicates schema examples |

---

## Appendix C: Duplication Analysis

Content that appears in **multiple places**:

| Content | Location 1 | Location 2 | Location 3 |
|---------|------------|------------|------------|
| Filter syntax | crud.md | schema injection | - |
| CRUD examples | write.md | schema injection | contextual_examples |
| Entity refs | Working Set | prev_step_section | (sometimes) pending_artifacts |
| "Check existing before adding" | write.md | shopping persona | contextual_examples |

**Recommendation:** Pick ONE authoritative source per content type.
| `prompts/act/analyze.md` | Analyze step instructions |
