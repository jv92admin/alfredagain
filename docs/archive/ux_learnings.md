# UX Learnings & Refinements

This document tracks UX observations from testing. These are **not bugs** - the pipeline is correct. These are opportunities to improve response quality and user experience.

---

## How to Use This Document

1. **Add observations** as you test
2. **Tag severity**: `minor` (polish), `moderate` (noticeable), `major` (confusing)
3. **Include example** prompts that triggered the issue
4. **Propose fix** when solution is clear
5. **Mark resolved** when fixed

---

## Open Issues

### UX-010: Recipe ingredients copied literally to shopping list
**Severity:** moderate  
**Date:** 2024-12-25  
**Trigger:** Adding recipe ingredients to shopping list

**Observed:**
Recipe ingredient "hard-boiled eggs (4 pieces)" was added to shopping list as "hard-boiled eggs" instead of just "eggs".

**Expected:**
Shopping list should have generic ingredient names like "eggs" (quantity: 4), not preparation states like "hard-boiled eggs".

**Root Cause:**  
When generating recipes, Act stores full descriptive ingredient names in `recipe_ingredients.name`. When adding to shopping list, it copies these names verbatim.

**Proposed Fix:**  
Option A: Normalize ingredient names when adding to shopping list (strip preparation adjectives)
Option B: Add guidance in Think/Act prompts to use base ingredient names for shopping lists
Option C: Create a lookup against `ingredients` table to normalize names

**Status:** Open

---

### UX-015: Shopping list additions don't merge duplicates
**Severity:** moderate  
**Date:** 2024-12-25  
**Trigger:** Adding recipe ingredients to shopping list when some already exist

**Observed:**
When adding ingredients from a recipe to shopping list, Alfred dumps the entire ingredient list without checking for duplicates. User ends up with:
- olive oil (2 tbsp)
- olive oil (1 tbsp)  ← duplicate!
- eggs (3)
- eggs (2)  ← duplicate!

**Expected:**
Smart merging:
- olive oil: keep one entry (staple item, don't sum tbsp)
- eggs: 5 (sum quantities for countable items)

**Root Cause:**  
Think/Act don't include explicit guidance to check existing shopping list before adding. Analyze step (when present) may not be merging intelligently.

**Proposed Fix:**  
Added schema guidance for shopping list with "Smart Shopping List Updates" pattern:
1. Read existing shopping list first
2. Combine duplicates in analyze step
3. Use `db_create` for new items, `db_update` for quantity increases

**Status:** Guidance added to schema. Needs testing.

---

### UX-001: Inventory readouts missing quantities (Partially Fixed)
**Severity:** moderate  
**Date:** 2024-12-24  
**Trigger:** `"what is in my pantry?"`

**Observed:**
> I've checked your pantry, and here's what I found:
> - Apples
> - Milk

**Expected:**
> Here's what's in your pantry:
> - **Apple**: 1 piece
> - **Milk**: 2 cartons + 2 gallons

**Root Cause:**  
Reply node's `_format_step_results()` only extracts `name` field. Full data is available in `step_results`.

**Proposed Fix:**  
Update `reply.py` `_format_step_results()` to include quantity/unit for inventory items:
```python
if "inventory" in context or table_name == "inventory":
    lines.append(f"- {item.get('name')}: {item.get('quantity')} {item.get('unit')}")
```

---

## Resolved Issues

### UX-002: Empty results presented as errors ✅ FIXED
**Severity:** major  
**Date:** 2024-12-24 | **Fixed:** 2024-12-25

**Fix Applied:**
1. Updated `act.py` to show semantic meaning for empty results:
   ```
   **Result: 0 records found.**
   → The items you searched for do NOT exist in this table.
   → This is a valid, complete answer. You now know they don't exist.
   ```
2. Updated `act.md` Role to clarify: "Query results are facts. 0 records = don't exist. Valid answer."
3. LLM now correctly calls `step_complete` on empty results.

---

### UX-003: "Pantry" interpreted literally as location filter ✅ FIXED
**Severity:** minor  
**Date:** 2024-12-24 | **Fixed:** 2024-12-24

**Fix Applied:**
Added semantic note in `SEMANTIC_NOTES` in `schema.py`:
```
When user says "pantry" or "what's in my pantry", they typically mean ALL their food inventory, 
not just items with location='pantry'. Only filter by location if user explicitly asks about 
a specific storage location (e.g., "what's in my fridge?").
```

---

### UX-004: Recipe search too literal ✅ FIXED
**Severity:** moderate  
**Date:** 2024-12-24 | **Fixed:** 2024-12-25

**Fix Applied:**
Added `or_filters` parameter to `db_read` for OR logic:
```python
{"tool": "db_read", "params": {
  "table": "recipes",
  "or_filters": [
    {"field": "name", "op": "ilike", "value": "%broccoli%"},
    {"field": "name", "op": "ilike", "value": "%cheese%"},
    {"field": "name", "op": "ilike", "value": "%rice%"}
  ]
}}
```
Now matches ANY keyword. Updated schema examples to show OR filter usage.

**Future enhancement:** Postgres full-text search RPC for ranked results.

---

### UX-005: Schema drift between code and database ✅ MITIGATED
**Severity:** major (maintenance risk)  
**Date:** 2024-12-24 | **Fixed:** 2024-12-25

**Fix Applied:**
1. Manually corrected `SUBDOMAIN_REGISTRY`, `FALLBACK_SCHEMAS`, and `SUBDOMAIN_EXAMPLES` to match actual DB
2. Added `validate_schema_drift()` function in `schema.py` that compares fallbacks to live DB
3. Added `log_schema_drift_warnings()` for startup validation

**Usage:**
```python
from alfred.tools.schema import log_schema_drift_warnings
await log_schema_drift_warnings()  # Call on app startup
```

**Future:** Consider generating fallbacks from migrations or single config file.

---

### UX-006: Infinite loop on empty/retry queries ✅ FIXED
**Severity:** major  
**Date:** 2024-12-24 | **Fixed:** 2024-12-25

**Fix Applied:**
1. `MAX_TOOL_CALLS_PER_STEP = 5` circuit breaker in `act.py`
2. Semantic result formatting: "0 records = valid answer, don't retry"
3. Updated Role in `act.md`: "Query results are facts"
4. LLM now understands empty = complete, not empty = retry

---

### UX-007: Cross-domain comparison is slow/loopy ✅ FIXED
**Severity:** moderate  
**Date:** 2024-12-24 | **Fixed:** 2024-12-25

**Fix Applied:**
1. Added `step_type` field to `PlannedStep`: `"crud"`, `"analyze"`, `"generate"`
2. Think now marks comparison steps as `"analyze"` 
3. Act handles analyze steps differently (no CRUD, just reasoning)
4. Semantic result display helps LLM understand what's done

---

### UX-008: Step/Tool Results Display is Garbled ✅ FIXED
**Severity:** moderate  
**Date:** 2024-12-24 | **Fixed:** 2024-12-25

**Fix Applied:**
1. Rewrote `_format_current_step_results()` to show actual JSON data, not summaries
2. Added semantic labels: "✓ Created 6 records", "Result: 0 records found"
3. Updated `_format_step_results()` to handle tuple format from circuit breaker
4. LLM now sees factual tool outputs, not its own potentially-wrong summaries

---

### UX-014: Conversation context bloat from recipe content ✅ FIXED
**Severity:** moderate (context explosion, potential hallucination trigger)  
**Date:** 2024-12-25 | **Fixed:** 2024-12-25

**Trigger:** Multi-turn session with recipe generation

**Observed:**
Conversation context included full recipe text (ingredients + instructions) repeated in every Act call.
- 2 recipes = ~80 lines of content per prompt
- Same content repeated 10+ times in a single conversation turn

**Root Cause:**  
Assistant messages were included verbatim in conversation context, even when they contained long generated content.

**Fix Applied (v2 - LLM-based):**
1. Added `_summarize_assistant_response()` in `summarize.py` - uses LLM for smart summarization
2. Added `assistant_summary` field to `ConversationTurn` model
3. Summarize node generates summary at storage time (after Reply)
4. Context formatting uses `assistant_summary` when available
5. Fallback to regex-based detection for legacy turns without summary

**LLM Prompt:**
```
Summarize what was accomplished in ONE brief sentence.
Focus on: what action was taken, what was created/found/updated.
Do NOT include full details like ingredient lists or instructions.
Example: "Created 2 recipes: Butter Chicken and Lemon Fish."
```

**Principle:** Conversation history conveys INTENT. Tool/step results are source of truth for DATA.

---

### UX-013: LLM hallucination loop in JSON generation ✅ MITIGATED
**Severity:** critical (complete failure)  
**Date:** 2024-12-25 | **Fixed:** 2024-12-25

**Trigger:** "Go through all recipes and update shopping list" (4 recipes with many ingredients)

**Observed:**
Act generated catastrophically malformed JSON with degenerate repetition:
```json
"filters": [
  {"field": "recipe_id", "op": "in", "value": [...]},
  "],",      // random string
  "limit", 1000, "columns", [...],  // repeated 30+ times
]
```
Pydantic threw 115 validation errors.

**Root Cause:**  
LLM got into a degenerate loop generating invalid JSON. This is a known failure mode for LLMs. Likely triggered by very long context with repeated recipe content.

**Fix Applied:**
1. Added `_validate_tool_params()` function in `act.py` to catch malformed params before Pydantic
2. Pre-validates that filters/or_filters are lists of dicts, data is correct type
3. Returns clearer error message indicating "LLM hallucination"
4. **Also:** Reduced context bloat (UX-014) which may have contributed

**Future:** Consider retry logic with simpler prompt on hallucination detection.

---

### UX-012: db_read results truncated to 10 items ✅ FIXED
**Severity:** major (data loss)  
**Date:** 2024-12-25 | **Fixed:** 2024-12-25

**Trigger:** "What about teaspoon and tablespoon stuff?" (shopping list had 15 items)

**Observed:**
Alfred said "none were listed as separate entries" for teaspoon/tablespoon items, but honey (1 tsp) and lemon juice (1 tbsp) WERE on the list as items 11-12.

**Root Cause:**  
`_format_current_step_results()` in `act.py` truncated db_read results to "First 10" when list size > 10. Items 11-15 were invisible to the LLM.

**Fix Applied:**
Increased truncation threshold from 10 to 50 records. For most CRUD operations (shopping lists, pantry items, recipes), users won't have 50+ items, so the LLM will see complete data.

---

### UX-011: db_update passed array instead of dict ✅ FIXED
**Severity:** major (tool call failure)  
**Date:** 2024-12-25 | **Fixed:** 2024-12-25

**Trigger:** "Adjust quantities for honey and lemon juice on shopping list"

**Observed:**
Act node passed `data: [{"quantity": 0.5}]` (array) when `db_update` requires `data: {"quantity": 0.5}` (dict).
Pydantic validation failed: "Input should be a valid dictionary"

**Root Cause:**  
Act prompt showed `db_create` with array format but didn't have an explicit `db_update` example. LLM confused the two formats.

**Fix Applied:**
1. Added "Data Format" section to Act prompt with explicit warning:
   - `db_create`: dict OR array
   - `db_update`: dict ONLY (applied to ALL matches)
2. Added `db_update` batch example showing the correct format

---

### UX-009: Prompt Architecture Needs Holistic Redesign ✅ FIXED
**Severity:** design debt  
**Date:** 2024-12-24 | **Fixed:** 2024-12-25

**Fix Applied:**
1. **Think prompt**: Rewritten with clear role, "What Act can do" section, planning tiers
2. **Act prompt**: Rewritten with database execution focus, semantic result display, clean structure
3. **Reply prompt**: Rewritten with Alfred's voice persona
4. **Result formatting**: Show actual JSON, not LLM summaries
5. **Prompt structure**: Task → What Happened → Schema → Decision (clear flow)
6. **Removed DO NOT patches**: Replaced with positive guidance and semantic context

**Key learnings:**
- Semantic result display ("0 records = valid") beats "DON'T retry" rules
- Clear Role explanation beats scattered constraints
- Show actual data, not summaries

---

---

## Phase 5 Scope: Multi-Turn Conversations

**Goal:** Enable conversational context across multiple user messages.

**Required:**
- [ ] ConversationContext in AlfredState
- [ ] Summarize node (end-of-exchange, gpt-4o-mini)
- [ ] Mid-loop compression for large step results
- [ ] Reference resolution ("that recipe" → EntityRef)
- [ ] Entity tracking in active_entities
- [ ] Inject conversation history into Think, Act, Reply prompts

**Nice to have:**
- [ ] Proactive suggestions (expiry alerts, meal inspiration)
- [ ] Session persistence across app restarts

---

## Phase 6 Scope: Model & Complexity Tuning

**Goal:** Optimize model selection, reasoning effort, and verbosity per task.

**Tasks:**
- [ ] Audit model usage across nodes (Router, Think, Act, Reply)
- [ ] Tune reasoning_effort: low for simple CRUD, medium for analysis
- [ ] Tune verbosity for Reply (user-facing) vs internal nodes
- [ ] Consider gpt-4o-mini for Summarize node
- [ ] Benchmark latency and cost
- [ ] Reply tone/personality tuning

---

## Testing Checklist

Use these prompts to regression-test UX improvements:

### Inventory
- [ ] `"what is in my pantry?"` → Shows quantities
- [ ] `"add 2 eggs to my fridge"` → Confirms with quantity + location
- [ ] `"what's expiring soon?"` → Shows dates

### Recipes
- [ ] `"suggest a recipe"` (no inventory) → Graceful, offers options
- [ ] `"suggest a recipe"` (with inventory) → Uses ingredients
- [ ] `"save that recipe"` → Conversation context works

### Empty States
- [ ] `"what is in my pantry?"` (empty) → "Your pantry is empty. Add items with..."
- [ ] `"show my recipes"` (none saved) → "No recipes yet. Want me to suggest one?"
- [ ] `"show my meal plan"` (none) → "No meal plan set. Want to create one?"

### Error States
- [ ] Invalid table access → Clear error, not crash
- [ ] DB connection failure → Graceful retry message

---

## Refinement Phases

### Phase A: Data Display (Low effort, high impact)
- UX-001: Include all available fields in responses
- Standardize formatting per entity type

### Phase B: Empty State Handling (Medium effort)
- UX-002: Distinguish empty results from errors
- Add helpful next-step suggestions

### Phase C: Intent Interpretation (Higher effort)
- UX-003: Better natural language understanding
- "Pantry" vs "fridge" vs "inventory" semantics

---

*Last updated: 2024-12-25*

