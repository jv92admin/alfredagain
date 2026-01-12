# Progressive Data Visibility & Planning Quality Spec

## Problem Statement

As Alfred grows in capability and user data volume, a core tension emerges:

- Different reasoning layers require different depths and shapes of information
- User data (recipes, inventory, preferences, history) grows without bound
- Injecting "everything" into any single planning step is unsustainable
- But starting from a narrow slice without awareness of the broader universe leads to subpar plans

**Symptoms Today:**
- Meal plan notes don't distinguish cooking logistics from recipe diffs
- Analyze can't check inventory coverage (only sees recipe titles, not ingredients)
- Generate can't write meaningful diffs (no access to instructions)
- System guesses at user's planning strategy instead of asking

---

## Core Architecture

```
PROPOSE → THINK (intent cascade) → READ (enriched) → ANALYZE → GENERATE
    ↓           ↓                       ↓              ↓          ↓
  User      Designs the           Right-sized      Signals    Final
  aligns    thinking for          data per         & recs     output
  strategy  Act to execute        step type
```

---

## Execution Phases

### Phase 1: Proposal + Think Quality

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.1 | Proposal explicitness | 🔲 TODO | |
| 1.2 | Think designs thinking for Act | 🔲 TODO | |
| 1.3 | Subdomain preferences minimum bar | 🔲 TODO | |

#### 1.1 Proposal Explicitness

**Problem:** Proposals like "I'll plan around Sun/Wed" don't explain WHY or let user understand the influence.

**Before:**
```
"I'll prioritize using your inventory, plan around your Sun/Wed cooking 
schedule, and leave 2 slots for takeout. Sound good?"
```

**After:**
```
"Based on your preferences, here's my approach:

**Cooking Schedule:** You cook on Sunday and Wednesday evenings — I'll plan 
fresh meals for those days and structure leftovers around them.

**Strategy:** Inventory-forward — I'll prioritize recipes that use what you 
have (cod, chicken, paneer) before suggesting new shopping.

**Constraints:** You asked for 2 takeout slots — I'll place these on days 
without leftover coverage.

**What this means:** Recipes will be selected by ingredient overlap with your 
inventory. Your saved recipes will be checked first.

Sound good? You can adjust the strategy or cooking days."
```

**Requirements:**
- [ ] Think prompt: proposals must explain the WHY, not just WHAT
- [ ] Subdomain preferences must have minimum completeness (cooking schedule, strategy preference)
- [ ] Proposal must indicate what downstream behavior it influences

---

#### 1.2 Think Designs Thinking for Act

**Problem:** Think writes 30k ft step descriptions. Act has rich tools but Think doesn't leverage them.

**Principle:** Think should trust that Act has:
- Full user data access
- Semantic search
- Progressive query capability
- Subdomain preferences

Think's job is to **design the reasoning**, not describe obvious steps.

**Before:**
```
steps: [
  {"description": "Read recipes", "step_type": "read", "subdomain": "recipes"},
  {"description": "Analyze feasibility", "step_type": "analyze", "subdomain": "meal_plans"},
  {"description": "Generate meal plan", "step_type": "generate", "subdomain": "meal_plans"}
]
```

**After:**
```
steps: [
  {
    "description": "Read recipes matching inventory proteins (chicken, cod, paneer) — summary with ingredients, no instructions needed",
    "step_type": "read",
    "subdomain": "recipes"
  },
  {
    "description": "Analyze feasibility: check inventory coverage, identify must-use items (expiring by Jan 15), recommend cook schedule around Sun/Wed",
    "step_type": "analyze",
    "subdomain": "meal_plans"
  },
  {
    "description": "Generate meal plan from analysis — include cooking logistics in notes, mark leftover flows",
    "step_type": "generate",
    "subdomain": "meal_plans"
  }
]
```

**Requirements:**
- [ ] Think prompt: step descriptions carry intent, constraints, expected approach
- [ ] Examples show Think trusting Act's capabilities
- [ ] Think doesn't over-specify HOW, but is clear on WHAT reasoning is needed

---

#### 1.3 Subdomain Preferences Minimum Bar

**Problem:** If preferences are vague, proposals can't be specific.

**Minimum for meal_plans:**
- Cooking schedule (days/times)
- Leftover tolerance
- Batch preference
- Default strategy (inventory-forward, variety-seeking, etc.)

**Minimum for recipes:**
- Skill level
- Equipment available
- Cuisine preferences
- Detail level preference (brief vs detailed instructions)

**Implementation:**
- [ ] Define minimum fields per subdomain
- [ ] Profile builder prompts for missing fields
- [ ] Think can still propose even with gaps, but notes what's assumed

---

### Phase 2: Read Enrichment

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | `include_instructions` flag | ✅ DONE | Prompt-based (no flag), Act decides based on step intent |
| 2.2 | Ingredients display: grouped by category | ✅ DONE | Auto-included via nested select, grouped in formatting |
| 2.3 | Summary vs Full presentation | ✅ DONE | `_format_recipe_record` handles both cases |

#### 2.1 Instructions Toggle

Add to `DbReadParams`:
```python
include_instructions: bool = False  # recipes table only
```

**Think decides:**
- Planning/browsing → `false`
- Cooking questions, editing → `true`

**Implementation:**
- [ ] Add flag to DbReadParams
- [ ] db_read respects flag for recipes table
- [ ] Think prompt explains when to use each

---

#### 2.2 Ingredients Display

**Decision:** Full ingredient list, no quantities, deduped by name, **grouped by category**.

**Rationale:**
- Quantities only matter for execution (cooking), not planning
- Deduped list is clean and scannable
- Grouping by category enables quick scanning (proteins across recipes, etc.)
- Same format works for shopping lists, inventory comparisons

**Format (grouped - preferred):**
```
recipe_1 (Chicken Tikka Bites):
  cuisine: indian | servings: 4 | difficulty: beginner | time: 45min
  occasion: weeknight
  proteins: chicken
  produce: onion, bell pepper, cilantro, lemon
  carbs: rice
  dairy: yogurt
  spices: garam masala, turmeric, cumin, garlic, ginger
```

**Fallback format (flat - if ingredients.category not populated):**
```
recipe_1 (Chicken Tikka Bites):
  cuisine: indian | servings: 4 | difficulty: beginner | time: 45min
  occasion: weeknight
  ingredients: chicken, onion, bell pepper, cilantro, lemon, rice, 
               yogurt, garam masala, turmeric, cumin, garlic, ginger
```

**⚠️ Dependency:** Grouped format requires ingredients DB audit (Phase 4.1) to confirm category data is populated.

**Implementation:**
- [ ] Modify recipe read to join recipe_ingredients + ingredients (for category)
- [ ] Group by ingredients.category if available, else flat list
- [ ] Format as comma-separated names within each category (deduped)
- [ ] Apply same pattern to shopping list displays

---

#### 2.3 Summary vs Full Presentation

**Summary (default for planning):**
```
- id, name, cuisine, servings, difficulty
- prep_time, cook_time
- tags
- ingredients (names only, deduped)
```

**Full (for cooking questions, editing):**
```
- All of summary
- instructions[]
- full ingredient list with quantities + units + notes
- description
```

**Implementation:**
- [ ] `_format_step_results` respects `include_instructions` flag
- [ ] Different formatting paths for summary vs full

---

### Phase 3: Search & Metadata Quality

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | Audit existing metadata | ✅ DONE | See audit results below |
| 3.2 | Recipe metadata structure | ✅ DONE | Added `occasions[]`, `health_tags[]`, `flavor_tags[]`, `equipment_tags[]` (migration 022) |
| 3.3 | Update Act prompt with honest search options | ✅ DONE | Updated personas.py + crud.md |
| 3.4 | Recipe generation → proper metadata | ✅ DONE | Updated personas.py generate persona |

#### 3.1 Audit Existing Metadata

**Questions to answer:**
- What cuisines actually exist in recipes?
- What tags are used? Are they consistent?
- What difficulty levels?
- Is ingredient_id properly linked to ingredients table?

**Implementation:**
- [ ] Query distinct values for cuisine, tags, difficulty
- [ ] Document what exists vs what prompts claim exists
- [ ] Identify gaps (recipes without tags, broken ingredient links)

---

#### 3.2 Recipe Metadata Structure

**Problem:** Previous approach conflated skill, time, effort, and context. Need clean separation.

---

**Existing Structured Fields (keep as-is):**

| Field | Type | What It Answers |
|-------|------|-----------------|
| `cuisine` | enum | What style of food? (indian, thai, mexican, etc.) |
| `difficulty` | enum | Who can cook this? (beginner, easy, medium, hard) |
| `prep_time_minutes` | int | How long to prep? |
| `cook_time_minutes` | int | How long to cook? |
| `servings` | int | How many portions? |

These are **facts about the recipe**, not opinions.

---

**NEW: Occasion Field (enum)**

Answers: **"When would you cook this?"**

| Value | Definition |
|-------|------------|
| `weeknight` | Quick, practical, after-work cooking. Under 45min active time. |
| `batch-prep` | Cook once, eat multiple times. Designed for leftovers. |
| `hosting` | Worth the effort, impress guests, dinner party worthy. |
| `weekend` | More involved, learning opportunity, project cooking. |
| `comfort` | Cozy, familiar, soul food. Not about speed or effort. |

**Storage:** `occasions: text[]` (array — a recipe can be both `weeknight` AND `batch-prep`)

**Enforcement:** Hard-coded enum. Generate prompt requires one of these values.

---

**NEW: Health Tags (optional array)**

| Tag | Meaning |
|-----|---------|
| `high-protein` | Protein-forward meal |
| `low-carb` | Keto-friendly, low starch |
| `vegetarian` | No meat |
| `vegan` | No animal products |
| `light` | Lower calorie, not heavy |

**Storage:** `health_tags: text[]` (optional, can be empty)

**Searchability:** `{"field": "health_tags", "op": "contains", "value": ["vegetarian"]}`

---

**Equipment Tags (array)**

| Tag | Meaning |
|-----|---------|
| `air-fryer` | Uses air fryer |
| `instant-pot` | Uses pressure cooker |
| `one-pot` | Single vessel cooking |
| `no-cook` | No heat required |
| `grill` | Uses outdoor grill |

**Storage:** Keep in existing `tags: text[]` field (already supports this)

---

**What This Gives Us:**

| Question | Field |
|----------|-------|
| What style of food? | `cuisine` |
| Who can cook this? | `difficulty` |
| How long does it take? | `prep_time + cook_time` |
| When would I cook this? | `occasions[]` |
| Dietary fit? | `health_tags[]` |
| What equipment? | `tags[]` (equipment subset) |

---

**Implementation:**
- [ ] Add `occasions` column to recipes table (text array)
- [ ] Add `health_tags` column to recipes table (text array)
- [ ] Update generate prompt to require `occasions` (at least one)
- [ ] Update generate prompt to set `health_tags` when applicable
- [ ] Backfill existing recipes (optional, LLM-assisted)

---

#### 3.3 Honest Search Options in Act Prompt

**Before (aspirational):**
```
Tags: batch-prep, meal-prep, comfort-food, quick, freezer-friendly
```

**After (honest):**
```
**Searchable Fields:**
- `cuisine`: indian, thai, mexican, italian, mediterranean, fusion, malaysian
- `difficulty`: beginner, easy, medium, hard
- `tags`: Use `contains` — actual tags vary, check results
- `name`: Use `ilike` for keyword search
- `_semantic`: Natural language ("light dinner", "comfort food")

**What Works:**
- Semantic search for vibes/concepts
- Cuisine + difficulty for structured filtering
- Name ilike for ingredient-based search

**What Doesn't Work:**
- Assuming tags exist that don't
- Filtering by categories we don't track
```

**Implementation:**
- [ ] Update Act read prompt with honest capabilities
- [ ] Remove phantom filter examples

---

#### 3.4 Recipe Generation → Proper Tagging

**Problem:** When LLM generates recipes, it should tag them properly based on:
- User's preferences (if they prefer "weeknight", tag weeknight-appropriate recipes)
- Actual recipe characteristics (cook time → quick/weekend-project)
- Standard tag vocabulary

**Implementation:**
- [ ] Generate prompt requires standard tags
- [ ] Validation that generated recipes have required fields
- [ ] Tags derived from characteristics (e.g., <30min total → "quick")

---

### Phase 4: Ingredients DB Enrichment

| # | Task | Status | Notes |
|---|------|--------|-------|
| 4.1 | Audit ingredients table | ✅ DONE | 1000 ingredients, 88% with aliases, categories usable |
| 4.2 | Category-based filtering | 🔲 TODO | |
| 4.3 | Ingredient similarity search | 🔲 TODO | Future scope |

#### 4.1 Audit Ingredients Table

**Questions:**
- How many ingredients have category populated?
- What categories exist?
- Are recipe_ingredients properly linked via ingredient_id?

**Goal:** Understand what we can leverage.

---

#### 4.2 Category-Based Filtering

**If ingredients.category is populated:**
```sql
-- "Show me chicken recipes"
SELECT DISTINCT r.* 
FROM recipes r
JOIN recipe_ingredients ri ON ri.recipe_id = r.id
JOIN ingredients i ON i.id = ri.ingredient_id
WHERE i.category = 'protein' AND i.name ILIKE '%chicken%';
```

**Enables:**
- "What can I make with my proteins?" → match inventory proteins to recipe proteins
- "Vegetarian options" → recipes where protein ingredients are tofu/paneer/eggs only
- "Pantry-friendly" → recipes with mostly shelf-stable ingredients

**Implementation:**
- [ ] Assess ingredient_id linkage coverage
- [ ] Add category-based query option to db_read
- [ ] Expose in Act prompt

---

#### 4.3 Ingredient Similarity (Future)

Search within similar categories:
- "Something like chicken" → poultry category → turkey, duck
- "Replace cod" → fish category → tilapia, salmon

**Scope:** Future phase, depends on 4.1/4.2 foundation.

---

### Phase 5: Analyze → Generate Pipeline

| # | Task | Status | Notes |
|---|------|--------|-------|
| 5.1 | Analyze output contract | 🔲 TODO | |
| 5.2 | Lazy enrichment before Generate | 🔲 TODO | |
| 5.3 | Context tiers (full vs names) | 🔲 TODO | |

#### 5.1 Analyze Output Contract

**Analyze MUST output:**
```json
{
  "narrative": "Brief reasoning about trade-offs",
  "selected_recipes": ["recipe_1", "recipe_3", "recipe_5"],
  "schedule_recommendation": {
    "2026-01-12": {"dinner": "recipe_1", "note": "fresh cook"},
    "2026-01-13": {"lunch": "recipe_1", "note": "leftovers"}
  },
  "constraints": {
    "must_use": ["inv_48 (wings) by Jan 15"],
    "hard": ["no shellfish"],
    "soft": ["prefer Indian cuisine"]
  },
  "gaps": ["Tuesday dinner - no good option, suggest takeout"]
}
```

**Analyze does NOT:**
- Create final meal plan items
- Write notes/diffs
- Require rigid schema (narrative is fine)

**Implementation:**
- [ ] Update analyze prompt with output contract
- [ ] Examples of good vs bad analyze outputs

---

#### 5.2 Lazy Enrichment Before Generate

**After Analyze completes:**
1. Parse Analyze output for `selected_recipes`
2. Fetch full recipe details (with instructions) for those IDs only
3. Inject into Generate context

**Implementation:**
```python
# In act.py, before building Generate prompt
if step_type == "generate" and prior_step_was_analyze:
    selected_ids = extract_recipe_refs(prior_step_result)
    full_recipes = await fetch_full_recipes(selected_ids)
    inject_full_recipe_context(prompt, full_recipes)
```

- [ ] Parse Analyze output for recipe refs
- [ ] Lazy fetch full recipes
- [ ] Inject into Generate context

---

#### 5.3 Context Tiers

**In Generate's context:**

| Source | What's Shown |
|--------|--------------|
| Analyze-selected recipes | Full (instructions, ingredients with qty) |
| Other recipes in history | Names only ("recipe_7: Malaysian Noodles") |
| Inventory | Full (from prior read) |
| Analyze output | Full signals |

**Implementation:**
- [ ] `_format_step_results` tiers based on "selected in prior step"
- [ ] Historical refs compressed to names

---

### Phase 6: Fallbacks & Polish

| # | Task | Status | Notes |
|---|------|--------|-------|
| 6.1 | Progressive query capability | 🔲 TODO | |
| 6.2 | Hard caps for large results | 🔲 TODO | |
| 6.3 | Act sequential read in one step | 🔲 TODO | |

#### 6.1 Progressive Query Capability

**Already possible.** Act can:
1. Broad search → too many
2. Add filter → right size
3. Complete

**Need:** Prompt examples showing this is valid.

---

#### 6.2 Hard Caps

When results > N (e.g., 30 recipes):
- Act should narrow with filters
- Or use semantic search to focus
- Don't dump 100 items into Analyze

**Implementation:**
- [ ] Prompt guidance for large result sets
- [ ] Maybe: soft warning when results > threshold

---

#### 6.3 Sequential Read in One Step

**Pattern:**
1. Summary read → identify specific items
2. Full read on those items
3. Complete

**Already possible** — just need prompt nudge that this is valid.

---

## Execution Priority

### Now (Quick Wins)
- [ ] 2.1 `include_instructions` flag
- [ ] 3.1 Audit existing metadata (cuisines, tags, difficulties in use)
- [ ] 4.1 Audit ingredients table (category coverage, linkage)
- [ ] 3.3 Honest search options in Act prompt

### Next (Core Enrichment)
- [ ] 3.2 Add `occasions` and `health_tags` columns (schema migration)
- [ ] 2.2 Ingredients display format (grouped by category)
- [ ] 2.3 Summary vs Full presentation
- [ ] 3.4 Update generate prompt with new metadata requirements

### Then (Pipeline + Think Quality)
- [ ] 1.1 Proposal explicitness
- [ ] 1.2 Think designs thinking for Act
- [ ] 5.1 Analyze output contract
- [ ] 5.2 Lazy enrichment before Generate

### Later (Polish)
- [ ] 4.2 Category-based filtering in queries
- [ ] 5.3 Context tiers
- [ ] 6.x Fallbacks and progressive query
- [ ] Backfill existing recipes with new metadata

---

## Resolved Decisions

1. **Ingredients display:** ✅ Full list, no qty, deduped, **grouped by category** (proteins, produce, carbs, etc.). Falls back to flat list if ingredients.category not populated. 4.1 audit complete - categories are usable.

2. **Recipe tag schema:** ✅ 4 columns replacing generic `tags`:
   - `occasions[]`: weeknight, batch-prep, hosting, weekend, comfort
   - `health_tags[]`: vegetarian, vegan, high-protein, low-carb, light, gluten-free, dairy-free
   - `flavor_tags[]`: spicy, mild, savory, sweet, tangy, umami
   - `equipment_tags[]`: air-fryer, instant-pot, one-pot, sheet-pan, grill, stovetop-only

3. **Metadata separation:** ✅ Clean split between facts (cuisine, difficulty, time) and context (occasions, health_tags, flavor_tags, equipment_tags).

4. **Ingredient matching:** ✅ Word-by-word matching with similarity scoring. 100% linkage achieved across all tables.

5. **Ingredient naming discipline:** ✅ Recipe ingredients use canonical names in `name` field, qualifiers in `notes`. Inventory/shopping keep user's text in `name`, auto-link via `ingredient_id`.

---

## Audit Results (2026-01-11)

### Recipe Metadata Audit

**Total recipes: 9**

| Field | Coverage | Notes |
|-------|----------|-------|
| `cuisine` | 9/9 (100%) | indian (3), fusion (2), thai (2), malaysian (1), indian-thai fusion (1) |
| `difficulty` | 9/9 (100%) | beginner (8), medium (1) — skewed toward beginner |
| `tags` | 8/9 (89%) | 29 unique tags for 9 recipes — **inconsistent vocabulary** |
| `prep_time` | 9/9 (100%) | ✅ |
| `cook_time` | 9/9 (100%) | ✅ |
| `occasions` | 0/9 (0%) | ❌ **New field needed** |
| `health_tags` | 0/9 (0%) | ❌ **New field needed** |

**Tag inconsistency examples:**
- "air-fryer" vs "air fryer" (duplicate with different formatting)
- "beginner-friendly" vs "beginner" (overlaps with difficulty field)
- "indian" (overlaps with cuisine field)
- "make-ahead sauce" vs "make-ahead-friendly" (inconsistent naming)

**Conclusion:** Need to standardize tag vocabulary and add `occasions` field.

---

### Ingredient Linkage Audit

**Initial Audit (2026-01-11):**
| Table | Total | Linked | Rate |
|-------|-------|--------|------|
| `recipe_ingredients` | 120 | 101 | **84%** |
| `inventory` | 97 | 83 | **86%** |
| `shopping_list` | 12 | 10 | **83%** |

**After Word-by-Word Matching Improvement (2026-01-12):**
| Table | Total | Linked | Rate |
|-------|-------|--------|------|
| `recipe_ingredients` | 120 | 120 | **100%** |
| `inventory` | 97 | 97 | **100%** |
| `shopping_list` | 12 | 12 | **100%** |

✅ **All ingredients now linked** via improved `ingredient_lookup.py`

**Previous issues (now resolved):**

| Unlinked Name | Should Match | Issue |
|---------------|--------------|-------|
| "frozen cod filet" | cod | Qualifier "frozen" + "filet" |
| "minced garlic" | garlic | Qualifier "minced" |
| "cumin powder" | cumin | Qualifier "powder" |
| "frozen broccoli" | broccoli | Qualifier "frozen" |
| "cheddar habanero cheese" | cheese / cheddar | Compound name |
| "gochugaru powder" | gochugaru | Qualifier "powder" |
| "thick-sliced brioche or challah bread" | bread | Complex description |

**Pattern:** Fuzzy matching fails on qualifiers (frozen, minced, powder) and compound names.

**Recommendation:** 
1. Current system works for ~85% of cases
2. Could improve by stripping common qualifiers before matching
3. Or add more aliases to ingredients table
4. Low priority — 85% is workable for now

---

### Ingredients Table Audit

**Total ingredients: 1000** — Comprehensive catalog!

**Alias coverage:** 878/1000 (88%) have aliases

**Categories (47 unique):**

| Category Type | Examples | Count |
|---------------|----------|-------|
| **Food types** | vegetables (111), fish (81), fruits (71), cheese (68), spices (56), dairy (53) | ~700 |
| **Cuisine-specific** | cuisine_indian, cuisine_korean, cuisine_japanese, etc. | ~35 |
| **Overlapping** | spices vs spice, nut vs nuts | Needs cleanup |

**Category issues:**
- Some redundancy: `spices` (56) vs `spice` (19), `nut` (13) vs `nuts` (12)
- Cuisine categories are mixed in with food types
- Good enough for grouped display

**Conclusion:** Categories exist and are usable. Minor cleanup would help but not blocking.

---

## Decisions (Aligned 2026-01-11)

### Decision 1: Ingredient Matching Strategy → Option C (Both)

**A. Generation Discipline:**
- Recipe ingredients: `name` = canonical food item, `notes` = preparation state
- Example: `name: "garlic"`, `notes: "minced"` (not `name: "minced garlic"`)
- Inventory/shopping: Keep user's text in `name` (they want to see brand names)

**B. Word-by-Word Matching Fallback:**
- Split ingredient name into words
- Match each word independently against ingredients DB
- Pick best match above threshold
- Handles: "frozen cod filet" → matches "cod", "minced garlic" → matches "garlic"

**Where brand names go:**
- `name`: User's text ("Trader Joe's organic eggs")
- `ingredient_id`: Auto-linked to canonical ("eggs")
- Current schema already supports this — just need smarter matching

---

### Decision 2: New Schema Columns (Replace Generic Tags)

**Remove generic `tags[]` column entirely.** Replace with 4 specific columns:

| Column | Valid Values | Required |
|--------|-------------|----------|
| `occasions[]` | weeknight, batch-prep, hosting, weekend, comfort | Yes (at least one) |
| `health_tags[]` | vegetarian, vegan, high-protein, low-carb, light, gluten-free, dairy-free, keto | No |
| `flavor_tags[]` | spicy, mild, savory, sweet, tangy, rich, light, umami | No |
| `equipment_tags[]` | air-fryer, instant-pot, one-pot, one-pan, grill, no-cook, slow-cooker, oven, stovetop | No |

**Remove from tags (use dedicated fields instead):**
- Cuisine names → `cuisine` field
- Difficulty indicators → `difficulty` field
- Ingredient names → search by ingredient instead

---

### Decision 3: Tag Cleanup → Do Now

Clean up existing 9 recipes NOW before bad patterns propagate. Script: `scripts/cleanup_recipe_metadata.py`

---

### Decision 4: Backfill Strategy

1. Create schema migration for `occasions` and `health_tags`
2. Update existing 9 recipes manually (small dataset, test data anyway)
3. Update generation prompts to require new fields

---

## Execution Order

1. ✅ **Schema migration** - Added `occasions`, `health_tags`, `flavor_tags`, `equipment_tags` columns (migration 022)
2. ✅ **Tag cleanup script** - Cleaned up existing 9 recipes (`cleanup_recipe_metadata.py`)  
3. ✅ **Prompt updates** - Updated personas.py (read/write/generate/analyze) + write.md + crud.md with new tag columns and ingredient naming
4. ✅ **Ingredient matching** - Word-by-word matching in `ingredient_lookup.py` + re-linked all tables (100% linkage now)
5. 🔲 **Presentation** - `include_instructions` flag, grouped ingredients display

---

## Remaining Work

### High Priority (Completes Core Functionality)
- [x] **2.1** Instructions toggle — prompt-based, Act uses `columns` to include/exclude
- [x] **2.2** Ingredients auto-included via nested select, grouped by category in formatting
- [x] **2.3** `_format_recipe_record` shows metadata, grouped ingredients, instructions if present

### Medium Priority (Think/Analyze Pipeline)
- [ ] **1.1** Proposal explicitness (Think prompt updates)
- [ ] **1.2** Think designs thinking for Act (richer step descriptions)
- [x] **5.1** Analyze output contract — all analyze personas now have explicit Output sections
- [ ] **5.2** Lazy enrichment before Generate (may not be needed with current design)

### Lower Priority (Polish)
- [x] **4.2** Semantic search simplified (name+description embeddings, clear structured vs semantic guidance to Act)
- [ ] **5.3** Context tiers (full vs names for historical refs)
- [ ] **6.x** Progressive query guidance, hard caps

---

## Session 2026-01-11 Accomplishments

### Semantic Search Improvements
- Simplified recipe embeddings to name + description only (removed bloated tags/ingredients)
- Regenerated all recipe embeddings with lean text
- Adjusted distance threshold from 0.6 → 0.7 for better recall
- Clear guidance: `_semantic` for vibes, structured filters for concrete attributes

### Analyze Pipeline Fixes
- **Clarifications no longer truncated** — removed 2000 char limit on analyze outputs
- **Output contracts** added to all analyze personas (inventory, shopping, tasks)
- **meal_plans.analyze** improved: "Be Reasonable, Then Clarify" principle
  - Constraints are soft, not binary
  - Draft what's possible, surface gaps honestly
  - Explain WHY recipes excluded, suggest shopping as option

### Smart Inventory Search
- **New `similar` operator** — `op: "similar"` returns top 5 ingredient matches
- **`=` operator enhanced** — uses ingredient lookup for best single match
- Backend uses same ingredient matching logic (exact → fuzzy → semantic)
- LLM controls depth: `=` for exact, `similar` for variants
- Works for both `inventory` and `shopping_list` tables

### Think Prompt Clarity
- Read step descriptions simplified — "Read all inventory" not "Read inventory for X"
- Avoids confusion that led Act to incorrectly AND filter multiple ingredients

---

*Last updated: 2026-01-12*
