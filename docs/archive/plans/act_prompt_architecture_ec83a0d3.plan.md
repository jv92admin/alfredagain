---
name: Act Prompt Architecture
overview: "Refactor Act node with dynamic context injection. Phase 0: Scoping discussion per subdomain (you and I define personas, scope, patterns). Phase 1: Document in architecture spec. Phase 2: Implement based on spec."
todos:
  - id: scope-generic
    content: "Scoping: Generic vs Dynamic content boundary"
    status: completed
  - id: scope-recipes
    content: "Scoping: Recipes subdomain (Chef persona)"
    status: completed
  - id: scope-ops
    content: "Scoping: Inventory + Shopping + Preferences (Ops Manager)"
    status: completed
  - id: scope-planning
    content: "Scoping: Meal Plan + Tasks (Planner persona)"
    status: completed
  - id: scope-meta
    content: "Scoping: History (stubbed)"
    status: completed
  - id: impl-personas
    content: "schema.py: Add SUBDOMAIN_PERSONAS dict (Chef, Ops Manager, Planner)"
    status: completed
  - id: impl-scope-config
    content: "schema.py: Add SUBDOMAIN_SCOPE dict (implicit_children, dependencies)"
    status: completed
  - id: impl-contextual-examples
    content: "schema.py: Add get_contextual_examples(subdomain, step_desc, prev_subdomain)"
    status: completed
    dependencies:
      - impl-scope-config
  - id: impl-get-persona
    content: "schema.py: Add get_persona_for_subdomain() function"
    status: completed
    dependencies:
      - impl-personas
  - id: impl-step-note-field
    content: "state.py: Add note_for_next_step to StepCompleteAction"
    status: completed
  - id: impl-prev-note-state
    content: "state.py: Add prev_step_note to AlfredState"
    status: completed
    dependencies:
      - impl-step-note-field
  - id: impl-inject-persona
    content: "act.py: Inject persona block at top of CRUD prompts"
    status: completed
    dependencies:
      - impl-get-persona
  - id: impl-inject-scope
    content: "act.py: Inject scope section based on subdomain"
    status: completed
    dependencies:
      - impl-scope-config
  - id: impl-inject-prev-note
    content: "act.py: Inject prev_step_note if present"
    status: completed
    dependencies:
      - impl-prev-note-state
  - id: impl-contextual-inject
    content: "act.py: Replace static examples with get_contextual_examples() call"
    status: completed
    dependencies:
      - impl-contextual-examples
  - id: impl-store-note
    content: "act.py: Store note_for_next_step in state on step_complete"
    status: completed
    dependencies:
      - impl-step-note-field
  - id: cleanup-act-warnings
    content: "act.md: Remove warning-heavy blocks (⚠️ CRITICAL etc)"
    status: completed
  - id: cleanup-act-examples
    content: "act.md: Remove static examples (now dynamic)"
    status: completed
    dependencies:
      - impl-contextual-inject
  - id: cleanup-act-slim
    content: "act.md: Slim to core mechanics only (<50% current size)"
    status: completed
    dependencies:
      - cleanup-act-warnings
      - cleanup-act-examples
  - id: test-recipe-flow
    content: "Test: Recipe creation flows naturally without warning-reading"
    status: completed
    dependencies:
      - cleanup-act-slim
  - id: test-shopping-merge
    content: "Test: Shopping addition checks existing (via example, not warning)"
    status: completed
    dependencies:
      - cleanup-act-slim
  - id: write-arch-doc
    content: "Optional: Write docs/act_prompt_architecture.md from plan"
    status: completed
---

# Act Prompt Architecture Overhaul

## Approach

**Spec-first, then implement.** We discuss each subdomain together, document decisions in an architecture spec, then implement from that spec.---

## Generic vs Dynamic Content (Boundary Definition)

Before scoping subdomains, we define what's **always present** vs **varies by subdomain**.

### Generic Content (always present in act.md — static baseline)

| Section | Purpose ||---------|---------|| **Core Identity** | "You are Alfred's execution engine — execute one step at a time" || **Conversation Context** | Recent turns, active entities, user intent || **Step Context** | Step number, description, what's done so far || **Tool Call History** | What you've called this step, results || **Tool Mechanics** | How db_read/create/update/delete work (params, operators, batch) || **Exit Contract** | When to call step_complete, what data to include || **Previous Step Note** | Content from previous CRUD step (injected dynamically, but format is generic) || **User Preferences** | From preferences table (dietary, equipment, time budget) — for generate/analyze |

### Dynamic Content (injected by act.py — varies by subdomain + step context)

| Section | What Varies | Injected When ||---------|-------------|---------------|| **Persona** | Chef vs Ops Manager vs neutral | Based on subdomain || **Scope** | "Shopping is influenced by recipes, meal_plan..." | Based on subdomain || **Schema** | Table definitions | Based on subdomain || **Contextual Examples** | 1-2 patterns relevant to THIS step | Based on step verb + prev subdomain || **Semantic Notes** | "Pantry = all inventory" | Based on subdomain || **Step Note Instructions** | "When completing, leave a note with IDs..." | CRUD subdomains only |

### Step Notes: Read vs Write

| Aspect | Where It Lives | Why ||--------|----------------|-----|| **Reading** previous step's note | Generic context (always injected) | Every step should see what previous step communicated || **Writing** a note for next step | Subdomain-specific instruction (CRUD only) | Only CRUD steps need to pass forward IDs/context |---

## Phase 0: Scoping Discussion (You + Me)

Go through each subdomain iteratively and define:| Subdomain | Questions to Answer ||-----------|---------------------|| **recipes** | Chef persona details? Naming conventions? Linked table guidance tone? || **inventory** | Ops Manager focus? Cataloging rules? Location handling? || **shopping** | Merge logic? Cross-domain patterns (from recipes, meal_plan)? || **meal_plan** | Planning style? Date handling? Recipe linking? || **tasks** | Reminder style? Category conventions? || **preferences** | Just data? Any special handling? || **history** | Just logging? Any special handling? |For each, we'll define:

1. **Persona/Identity** — How should Act "think" in this domain?
2. **Scope** — What influences this domain? What flows INTO it?
3. **Key Patterns** — What are the 2-3 most common operations?
4. **Gotchas** — What mistakes does Act make today that we want to prevent?

Output: Filled-in spec in `docs/act_prompt_architecture.md`---

## Phase 1: Architecture Documentation

Create `docs/act_prompt_architecture.md` with:

1. **Decision Points** — Where dynamic injection happens
2. **Persona Definitions** — Exact text for Chef, Ops Manager
3. **Subdomain Scope Tables** — influenced_by, typical_flows per subdomain
4. **Contextual Example Logic** — When to inject which pattern
5. **Step Note Format** — What CRUD steps should communicate forward
6. **Reasoning** — Why each choice was made (so future edits don't conflict)

This becomes the **source of truth** for prompt construction.---

## Phase 2: Implementation

Only after Phase 0-1 are complete:| Task | File ||------|------|| Add `SUBDOMAIN_PERSONAS`, `SUBDOMAIN_SCOPE` | `schema.py` || Add `get_contextual_examples()` | `schema.py` || Add `note_for_next_step` to state | `state.py` || Inject dynamic sections in Act | `act.py` || Slim down static prompt | `act.md` |---

## Plumbing Details & Legacy Cleanup

### Files to Modify

**`src/alfred/tools/schema.py`:**

- ADD: `SUBDOMAIN_PERSONAS` dict with Chef, Ops Manager, Planner text
- ADD: `SUBDOMAIN_SCOPE` dict with implicit_children, implicit_dependencies
- ADD: `get_contextual_examples(subdomain, step_description, prev_subdomain)` function
- MODIFY: `get_subdomain_context()` to use new structures
- REVIEW: `SUBDOMAIN_EXAMPLES` — replace static examples with contextual selection
- REVIEW: `SEMANTIC_NOTES` — keep but ensure no conflicts with new scope

**`src/alfred/graph/state.py`:**

- ADD: `note_for_next_step: str | None` to `StepCompleteAction`
- ADD: `prev_step_note: str | None` to `AlfredState`

**`src/alfred/graph/nodes/act.py`:**

- MODIFY: `act_node()` to inject persona at top of prompt
- MODIFY: `act_node()` to inject scope section
- MODIFY: `act_node()` to inject prev_step_note if present
- MODIFY: `act_node()` to call `get_contextual_examples()` instead of full static examples
- ADD: Store `note_for_next_step` in state when step completes
- REVIEW: `_format_step_results()` — ensure it's not duplicating context

**`prompts/act.md`:**

- KEEP: Core identity, tool mechanics, exit contract
- REMOVE: Static examples (moved to dynamic injection)
- REMOVE: Warning-heavy "⚠️ CRITICAL" blocks (replace with intuitive guidance)
- REMOVE: Redundant sections that will be dynamically injected
- SLIM DOWN: Focus on generic mechanics only

### Legacy Patterns to Remove/Replace

| Legacy Pattern | Issue | Replacement ||----------------|-------|-------------|| `⚠️ CRITICAL DIFFERENCE` blocks | Warning-heavy, not intuitive | Contextual examples when relevant || Static `SUBDOMAIN_EXAMPLES` for all steps | Same examples regardless of step type | `get_contextual_examples()` based on verb || Linked table warnings in schema | Reads like rules, not guidance | Chef persona handles intuitively || "DON'T" / "NEVER" phrasing | Negative framing | Positive guidance via persona || Full example blocks in act.md | Bloats static prompt | Move to dynamic injection |

### Verification Checklist

Before implementation is complete:

- [ ] Persona text defined for Chef, Ops Manager, Planner
- [ ] Scope config complete for all subdomains
- [ ] Contextual example function handles: step verb, prev subdomain, cross-domain patterns
- [ ] Step notes wired through state
- [ ] act.md slimmed to <50% of current size
- [ ] Legacy warning blocks removed
- [ ] Test: Recipe creation flows naturally (no warning-reading required)
- [ ] Test: Shopping addition checks existing first (via example, not warning)

---

## Implementation Details (from scoping)

### Contextual Example Selection

| Context Signal | Example Pattern ||----------------|-----------------|| Step verb = "add", subdomain = shopping | "Smart Shopping" pattern (read first, merge duplicates) || Step verb = "delete", subdomain = recipes | Linked table delete pattern || Previous step was recipes read | "Recipe → Shopping" cross-domain pattern || Previous step was meal_plan read | "Meal Plan → Shopping" pattern |

### CRUD Step Notes

```python
class StepCompleteAction(BaseModel):
    result_summary: str
    data: Any
    note_for_next_step: str | None  # "Recipe ID abc123 created, needs ingredients"
```

Rules:

- Only CRUD steps write notes (generate/analyze don't need to)
- Keep notes short (1-2 sentences) — IDs, counts, key observations

### Subdomain Scope Structure

```python
SUBDOMAIN_SCOPE = {
    "shopping": {
        "influenced_by": ["recipes", "meal_plan", "inventory"],
        "typical_flows": ["recipe ingredients → shopping", "meal plan → shopping", "manual add"]
    },
    "meal_plan": {
        "influenced_by": ["recipes"],
        "typical_flows": ["assign recipe to date", "batch cooking session"]
    },
    ...
}
```



### Prompt Structure (After)

```javascript
┌─────────────────────────────────────────────────────────────┐
│ DYNAMIC: Subdomain-Specific                                 │
├─────────────────────────────────────────────────────────────┤
│ ## Persona                                                  │
│ [Chef or Ops Manager — based on subdomain]                  │
│                                                             │
│ ## Scope                                                    │
│ [What influences this subdomain, typical flows]             │
├─────────────────────────────────────────────────────────────┤
│ GENERIC: Always Present (from act.md)                       │
├─────────────────────────────────────────────────────────────┤
│ ## Core Mechanics                                           │
│ [Identity, tools, exit contract — static baseline]          │
│                                                             │
│ ## Previous Step Note                                       │
│ [Content from last CRUD step — injected if present]         │
│                                                             │
│ ## Conversation Context                                     │
│ [Recent turns, active entities]                             │
│                                                             │
│ ## Step Context                                             │
│ [Step N of M, description, tool results so far]             │
├─────────────────────────────────────────────────────────────┤
│ DYNAMIC: Subdomain-Specific                                 │
├─────────────────────────────────────────────────────────────┤
│ ## Schema                                                   │
│ [Table definitions for this subdomain]                      │
│                                                             │
│ ## Patterns for This Step                                   │
│ [1-2 contextual examples — based on step verb + context]    │
│                                                             │
│ ## Step Note Instructions (CRUD only)                       │
│ [How to write a note for the next step]                     │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** Dynamic content wraps around the generic core. Persona/scope at top for orientation, schema/examples at bottom for execution guidance.---

## Proposed Discussion Flow

1. **Recipes** — Chef persona, linked tables, naming ✅
2. **Inventory + Shopping + Preferences** — Ops Manager, normalization ✅
3. **Meal Plan + Tasks** — Planner persona, coordination ✅
4. **History** — Stubbed, deprioritized ✅

**All subdomain scoping complete!**---

## Scoping Results

### Recipes Subdomain ✅

**Persona:**

- Frame: "High-end personal chef" — user preferences paramount, expertise serves the client
- Generate steps: Creative chef — flavor intuition, balanced recipes, personalization
- CRUD steps: Organizational chef — clean naming, proper tagging, linked tables correct

**Naming Conventions:**

- Avoid run-on sentences
- Clean, searchable: "Spicy Garlic Pasta & Pesto Chicken"
- Use `&` to combine dishes when appropriate

**Tags Strategy (`recipes.tags`):**

- Occasion: `weekday`, `fancy`, `date-night`
- Lifecycle: `leftovers`, `try-again-soon`, `friends-liked`
- Equipment: `air-fryer`, `instant-pot`
- Tags can be updated through conversation

**Linked Tables:**

- Keep `recipe_ingredients` as separate table (query flexibility, shopping aggregation)
- Think mentions ingredients explicitly in step descriptions
- Step notes pass recipe IDs forward to next step
- LLM can combine ingredient quantities in updates

**Implicit vs Explicit Chains:**

- Implicit: `recipe → recipe_ingredients` — always create together, one unit
- Explicit: `recipe → shopping` — only when user requests

**Subdomain Scope Config:**

```python
"recipes": {
    "implicit_children": ["recipe_ingredients"],
}
```

---

### Inventory + Shopping + Preferences Subdomain (Ops Manager) ✅

**Persona: Ops Manager**

- Frame: Organized, efficient cataloger
- Focus: Normalize, dedupe, tag, track
- Shared across: inventory, shopping, preferences

**Core Principles:**

1. **Quantity normalization** — Check before updating, consolidate duplicates
2. **Consistent naming** — "diced chillies" → "chillies", "boiled eggs" → "eggs"
3. **Reasonable substitutions** — Infer base ingredients from preparation states
4. **Tagging/metadata** — Best-guess location (fridge/frozen/fresh/shelf), category
5. **Track purchase data & expiry** — Approximate when possible

**Preferences Handling:**

- Be accurate. Always communicate preference changes explicitly to user.
- Implications on UX are significant — explicit confirmation required.

**Ingredient Normalization (Async):**

- Seed `ingredients` table with large dataset (Open Food Facts, etc.)
- Background process matches names to master list, populates `ingredient_id`
- No LLM involvement — transparent cleanup at CRUD layer
- Already have seed scripts from Phase 8 (`scripts/seed_ingredients.py`)

**Subdomain Scope Config:**

```python
"inventory": {
    "normalization": "async",  # Background process
},
"shopping": {
    "normalization": "async",
},
"preferences": {},  # Explicit communication required
```

---

### Meal Plan + Tasks Subdomain (Planner) ✅

**Persona: Planner**

- Frame: Coordinator, scheduler
- Focus: Sequencing, dependencies, effective planning
- Shared across: meal_plan, tasks

**Core Principles:**

1. **Meal plan is primary** — Tasks often flow from meal planning
2. **Tasks support progression** — Prep, thaw, buy, etc.
3. **Shared logic context** — Meal plans and tasks work in harmony
4. **`meal_plan_id` > `recipe_id`** — Tasks prefer meal_plan reference (recipe derivable)
5. **Graceful recipe handling** — Suggest creating recipe if not found, but not mandated

**Implicit Dependencies:**

- Real meals (breakfast/lunch/dinner/snack) → should have recipe
- Exception: `prep` and `other` meal types don't require recipes
- If recipe missing: graceful prompt "That recipe doesn't exist. Create it for better shopping/planning?"

**Task Inflow:**

- Most common: from meal plan (prep tasks, reminders)
- Can also be freeform (not linked to anything)
- Categories: prep, shopping, cleanup, other

**Subdomain Scope Config:**

```python
"meal_plan": {
    "implicit_dependencies": ["recipes"],
    "exception_meal_types": ["prep", "other"],
    "related": ["tasks"],  # They work together
},
"tasks": {
    "primary_inflow": ["meal_plan"],
    "prefer_reference": "meal_plan_id over recipe_id",
},
```

---

### History Subdomain (Stubbed) ✅

**Status:** Deprioritized — stub for now**Reasoning:**

- Cooking log is simple CRUD, no special persona needed
- Recipe tags can track "tried this", "liked it" for now
- Could be UI-driven/deterministic later (not LLM-dependent)
- No special prompt guidance required

**Subdomain Scope Config:**

```python
"history": {},  # Stubbed, basic CRUD only
```

---

### Persona vs Schema Injection (Architecture Clarification)

Two layers of dynamic injection:| Layer | What It Does | Scope ||-------|--------------|-------|| **Persona (System)** | Sets mindset, big picture identity | Shared across related subdomains || **Schema (Tool)** | Tables for THIS step only | Focused on current subdomain |**Example: Ops Manager Group**Persona (shared across inventory, shopping, preferences):> "You're an operations manager. Normalize names, dedupe, tag consistently, track accurately."Schema (only what's needed for the step):

- Step about inventory → inject `inventory` schema only
- Step about shopping → inject `shopping_list` schema only

This keeps:

- **Big picture** = consistent via persona
- **Focus** = maintained via scoped schema

---

## Why This Matters

Without explicit scoping:

- I might define "Chef" as overly creative when you want precision
- I might add merge logic to shopping that conflicts with your UX expectations
- Examples might overlap or contradict each other
- Future edits break things because reasoning isn't documented