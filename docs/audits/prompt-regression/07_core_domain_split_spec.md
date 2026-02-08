# Core / Domain Prompt Split Specification

**Context:** The Phase 3f genericization replaced domain content with useless placeholders. This spec defines the exact boundary: what the core orchestration shell owns vs what each domain (kitchen, FPL, fitness) must inject.

**Principle:** Core owns the *shape*. Domain owns the *substance*. Core tells each node its role in the pipeline and enforces the output contract structure. Domain provides every example, entity reference, workflow pattern, subdomain description, and user-facing personality.

**Definition of done:** The runtime prompt sent to the LLM for each node must match the pre-refactor prompt as closely as possible. The pre-refactor logs at `prompt_logs_downloaded/20260203_014946/` are the canonical reference. The only difference should be *where* the content comes from (core template vs domain injection), not *what* the LLM sees.

**Pydantic contracts:** Response models (`UnderstandOutput`, `ThinkOutput`, `ActDecision`, `ReplyOutput`, `AssistantResponseSummary`) live in core and are enforced via `response_model` in `llm_call()`. This is correct — core needs these shapes to route data between nodes. The domain fills the *content* inside those shapes.

---

## Handling Genericized Examples

Three options for what to do with the current genericized placeholders in core templates:

| Option | Description | When to Use |
|--------|-------------|-------------|
| **A: Delete from core** | Remove genericized examples entirely, rely on domain injection to restore pre-refactor content | Understand — examples are 100% domain content |
| **B: Keep as template documentation** | Keep as commented/annotated examples showing the *shape* domain content should follow | Think — structural examples around step types, context layers, etc. are useful documentation even if the specific nouns are domain-flavored |
| **C: Replace with `{placeholder}` tags** | Mechanical find-replace where domain fills named injection points | Not recommended — too many injection points, harder to maintain |

**Recommendation:** Option A for Understand (pure domain content, no structural value in generic placeholders). Option B for Think (structural patterns around step types, entity lifecycle, parallel grouping are genuinely useful as documentation for domain implementors, even with genericized nouns).

---

## Per-Node Split

### Understand

**Current template:** `src/alfred/prompts/templates/understand.md` (308 lines)
**Kitchen injection:** None currently — all content is in the template
**Pre-refactor reference:** `prompt_logs_downloaded/20260203_014946/06_understand.md`

#### Core owns (orchestration shell)
- Role definition: "You are Alfred's memory manager"
- Three cognitive tasks (structural): reference resolution, context curation, quick mode detection
- "What you don't do" list (structural)
- Output contract field definitions (Pydantic `UnderstandOutput`)
- Resolution types table (structural — defines what "clear", "ambiguous", "none" mean)
- "What NOT to Do" rules (structural — constraints on behavior)

#### Domain injects (everything else — restored from pre-refactor)
- **Intro paragraph** — what entities exist, what multi-turn patterns look like ("building meal plans over a week, refining recipes through iterations")
- **Reference resolution table** — domain-specific ref patterns ("that recipe" → `recipe_1`, "the fish one" → ambiguous)
- **Context curation examples** — what entities to retain and why ("gen_meal_plan_1: User's ongoing weekly meal plan goal")
- **Quick mode detection table** — domain-specific quick commands ("show my inventory", "what recipes do I have?", "show my shopping list")
- **Valid subdomain names** — constrained enum that the LLM must pick from for `quick_subdomain` field (inventory, shopping, recipes, meal_plans, tasks, preferences)
- **All 6 examples** — with real entity names (Butter Chicken, Honey Glazed Cod, Thai Curry, Thai Cod en Papillote, etc.)
- **Key insight paragraph** — with domain context

#### Genericized example strategy: **Option A (Delete)**
All examples are 100% domain content. Generic "Item A", "show my items" teach the LLM nothing. Delete from core, inject pre-refactor content from domain.

#### New DomainConfig method needed
```python
def get_understand_prompt_content(self) -> str:
    """Return the full domain-specific Understand prompt body.
    Includes: intro, ref resolution table, curation examples,
    quick mode table, valid subdomain names, all examples, key insight."""
```

---

### Think

**Current template:** `src/alfred/prompts/templates/think.md` (383 lines)
**Kitchen injection:** `THINK_DOMAIN_CONTEXT` + `THINK_PLANNING_GUIDE` via `get_think_domain_context()` / `get_think_planning_guide()`
**Pre-refactor reference:** `prompt_logs_downloaded/20260203_014946/07_think.md`

#### Core owns (orchestration shell)
- `<identity>` — "You are Alfred's strategic planner. You decide WHAT to do, not HOW." Hard rules (prefer propose over plan_direct for ambiguity, etc.)
- `<precedence>` — conflict resolution rules
- Step type definitions (read/write/analyze/generate — the mechanics: what each does, how they compose)
- Entity lifecycle rules (`gen_*` refs live in memory, require explicit save, etc.)
- Context layer definitions (active entities, long-term memory, generated content — structural)
- Parallel step grouping mechanics (same group number = parallel)
- Modification + saving pattern (generate to modify, then write to save)
- `<output_contract>` field definitions (Pydantic `ThinkOutput`) — but NOT the examples
- Dynamic injection points: `{session_context}`, `{conversation_history}`, `{immediate_task}`

#### Domain injects (everything else — restored from pre-refactor)
- **`<alfred_context>`** entirely — philosophy ("efficient planning enables delicious cooking"), what Alfred enables, user personas
- **`<system_structure>`** entirely:
  - Subdomains table (inventory, shopping, recipes, meal_plans, tasks, preferences)
  - Linked tables (recipe_ingredients, ingredient backbone, meal_plan_items)
  - Complex domain descriptions (Recipes, Meal Plans as operation hubs)
  - Recipe workflow patterns (lookup → create)
  - Data level guidance (summary vs full, when to include instructions)
- **`<understanding_users>` examples** — domain-specific examples within this section ("diet, equipment, skill, cooking rhythm" vs genericized "constraints, equipment, skill level"). The structural frame ("Know the User", "Meet them where they are") stays in core.
- **`<conversation_management>` examples** — the section's structural frame (iterative workflows, phases, checkpoints pattern) stays in core. But the tables and examples within it were genericized/removed and must be restored:
  - Conversation before planning table ("plan my meals" → propose batch-cooking questions)
  - Iterative workflow examples (8-step meal plan workflow — removed entirely, must be restored)
  - Don't one-shot table ("week meal plan", "recipe creation", "shopping list")
  - Human-in-the-loop examples ("recipe selection", "day assignment")
  - Checkpoint table ("after reading recipes → which interest you?")
  - Post-action awareness table ("I cooked [recipe]" → update inventory — removed entirely, must be restored)
- **`<output_contract>` examples** — plan_direct, propose, clarify with domain context (currently genericized to "Read saved items", must restore "Read saved recipes" etc.)
- **Tone guidance examples** — "whats in my pantry" → just execute, "hosting people this weekend" → event

#### Genericized example strategy: **Option B (Keep as template documentation)**
The structural patterns around step types, entity lifecycle, parallel grouping are genuinely useful as documentation for domain implementors. Keep them in the core template. The domain injection restores the pre-refactor examples alongside them.

#### Existing DomainConfig methods (already wired)
- `get_think_domain_context()` — returns `THINK_DOMAIN_CONTEXT` (covers `<alfred_context>`)
- `get_think_planning_guide()` — returns `THINK_PLANNING_GUIDE` (covers `<system_structure>`)

#### Gap: what existing injection does NOT cover
These sections **exist in the core template but are hollowed out** — present structurally but with genericized/removed examples:

| Section | Status | What must be restored from pre-refactor |
|---------|--------|----------------------------------------|
| `<understanding_users>` | Structural frame intact, examples genericized | "diet, equipment, skill, cooking rhythm" and other domain-specific user signals |
| `<conversation_management>` | ~100 lines still in core, largely structural | Domain examples in tables: planning, one-shot, checkpoints, post-action. Some tables removed entirely. |
| `<output_contract>` examples | Present but genericized | "Read saved recipes" / "recipes" / "inventory" — the pre-refactor examples verbatim |
| Tone guidance | Present but genericized | "whats in my pantry" → just execute, "hosting people this weekend" → event |

**Action needed:** Expand kitchen's `THINK_PLANNING_GUIDE` (or add a new `THINK_CONVERSATION_GUIDE`) to include the conversation management examples, output contract examples, and tone guidance. Source: `prompt_logs_downloaded/20260203_014946/07_think.md`.

---

### Act

**Current template:** `src/alfred/prompts/templates/act/base.md` (74 lines) + step-type files (`read.md`, `write.md`, `generate.md`, `analyze.md`, `crud.md`)
**Kitchen injection:** `ACT_INJECTIONS[step_type]` via `get_act_prompt_injection(step_type)` + persona/examples via `get_act_subdomain_header()` / `get_examples()`
**Pre-refactor reference:** `prompt_logs_downloaded/20260203_014946/08_act.md`

#### Core owns (orchestration shell)
- Role: "You are Alfred's executor. You carry out Think's plan using CRUD tools."
- Core principles (structural): tool_call/step_complete/ask_user/blocked action taxonomy
- Exit contract structure
- CRUD tools reference (filter syntax, operators — these are core DB capabilities)
- `apply_filter()` documentation (core DB mechanic)
- Output contract (Pydantic `ActDecision` / `ActQuickDecision`)

#### Domain injects (everything else — restored from pre-refactor)
- **Step-type specific guidance:**
  - READ: broader intent interpretation ("pantry" = all inventory), semantic search, auto-includes, kitchen-specific notes
  - WRITE: cascade behavior (recipes → recipe_ingredients), batch insert patterns
  - ANALYZE: common analysis patterns (inventory vs shopping, recipe vs inventory, expiring items)
  - GENERATE: quality standards, personalization rules, entity tagging conventions
- **Examples in core template** — currently useless placeholders (`item_1`, `events` table) should be replaced with pre-refactor content via domain injection
- **Schema** — already correctly injected dynamically per subdomain
- **Persona** — already correctly injected via `get_persona()`

#### Current state: CLOSEST TO CORRECT
The Act node already has the right architecture:
1. Core template provides structural shell
2. `get_act_prompt_injection(step_type)` injects kitchen-specific patterns
3. `get_act_subdomain_header()` and `get_examples()` inject per-subdomain context

#### Remaining fix
Delete useless generic placeholders from core template (`item_1`, `events` table, etc.) and ensure domain injection restores the pre-refactor examples (`recipe_1`, `recipe_ingredients`, `expiry_date`, etc.).

---

### Reply

**Current template:** `src/alfred/prompts/templates/reply.md` (159 lines)
**Kitchen injection:** `get_system_prompt()` (system.md identity), `get_reply_subdomain_guide()` (formatting per entity type)
**Pre-refactor reference:** `prompt_logs_downloaded/20260203_014946/13_reply.md`

#### Core owns (orchestration shell)
- Role: "You are Alfred's voice. You present execution results to the user."
- What you receive (structural — Think plan + Act results)
- Outcomes aren't guaranteed (structural)
- Conversation continuity (structural — phase-appropriate responses)
- Editorial principles structure (lead with outcome, be specific, show content in full, be honest about failures)
- Output contract (Pydantic `ReplyOutput`)
- Dynamic injection points: `{domain_subdomain_guide}`, `{execution_summary}`

#### Domain injects (everything else — restored from pre-refactor)
- **System prompt header** — full identity ("Alfred - Your Kitchen Intelligence", capabilities, communication style) via `get_system_prompt()`
- **`<subdomains>` formatting guide** — how to render each entity type (inventory grouped by location, recipes in magazine style, etc.) via `get_reply_subdomain_guide()`
- **~8 genericized lines** in `<identity>` and `<principles>` that must be restored:
  - "Done! Added eggs to your shopping list." (not "Done! Added the items.")
  - "Here's your meal plan for the week:" (not "Here's your plan:")
  - "Your pantry has 2 cartons of milk" (not "You have 2 cartons")
  - "Chicken expires Jan 15" (not "Item expires Jan 15")

#### Current state: MOSTLY CORRECT
Reply is the best-shaped node. The injection architecture works. Only fix needed is restoring the ~8 genericized example lines to their pre-refactor content via domain injection.

---

### Summarize

**Current template:** `src/alfred/prompts/templates/summarize.md` (267 lines)
**Kitchen injection:** None needed

#### Core owns: EVERYTHING
The Summarize template is entirely structural:
- Role: summarize what was accomplished in one sentence
- Proposals vs completed actions distinction
- Use exact entity names from text
- Keep summaries specific

The examples happen to use kitchen nouns ("Mediterranean Chickpea Bowl", "recipes") but they illustrate the *behavior pattern* (use exact names, don't paraphrase), not domain knowledge. Any domain would follow the same rules. If a future domain (FPL, fitness) ever needed different summarization rules, the same injection pattern could be added — but this is unlikely since summarize is truly structural.

#### No action needed

---

### Router

**Current template:** `src/alfred/prompts/templates/router.md`
**Kitchen injection:** `get_router_prompt_injection()` → agent definitions

#### Core owns
- Role: route to the correct agent
- Output contract structure

#### Domain injects
- Agent definitions (pantry, coach, cellar) via `get_router_prompt_injection()`
- Already correctly structured

---

## Summary: What Needs to Change

| Node | Core Template | Domain Injection | Work Needed |
|------|--------------|-----------------|-------------|
| **Understand** | Keep structural shell (role, resolution types, what-not-to-do, contract fields) | Add `get_understand_prompt_content()` — restore ALL pre-refactor examples, quick mode table, ref resolution table, valid subdomain names | HIGH — new injection method + restore pre-refactor content to kitchen |
| **Think** | Keep structural shell (identity, precedence, step mechanics, entity lifecycle, contract fields) | Expand existing injections — restore conversation management examples, output examples, tone guidance from pre-refactor | HIGH — sections exist but are hollowed out; restore removed/genericized content |
| **Act** | Keep current structure, replace generic placeholders with domain injection | Ensure domain injection restores pre-refactor examples | LOW — architecture already correct, content restoration |
| **Reply** | Keep current structure | Restore ~8 genericized example lines to pre-refactor content | LOW — minor |
| **Summarize** | No change | No change | NONE |
| **Router** | No change | Already correct | NONE |

## Implementation Priority

1. **Think** — most critical node, most content to restore from pre-refactor logs
2. **Understand** — second most content, needs new injection method
3. **Act** — cleanup only, architecture already works
4. **Reply** — minor fix, architecture already works

## Source of Truth

Pre-refactor prompt logs at `prompt_logs_downloaded/20260203_014946/` contain the exact content that the LLM should see at runtime. The definition of done for each node is: **the assembled runtime prompt matches the pre-refactor log as closely as possible.** The only acceptable difference is *where* the content originates (core template vs domain injection), not *what* the LLM receives.

## Architectural Pattern

For every node, the runtime prompt assembles as:
```
CORE SHELL (role definition + output contract fields)
  + DOMAIN CONTENT (examples, entity guidance, workflow patterns, personality)
  + DYNAMIC CONTEXT (user profile, entities, conversation history, current message)
```

The assembled result must match pre-refactor behavior. The current genericized `.md` templates serve as **template documentation** for future domain implementors ("here's the shape your content should follow") but are NOT suitable as runtime prompts.

---

## Implementation Progress

Update this section after completing each node.

| Node | Status | Date | Notes |
|------|--------|------|-------|
| Understand | DONE | 2026-02-08 | Added `get_understand_prompt_content()` to DomainConfig + KitchenConfig. Created `alfred_kitchen/domain/prompts/understand_content.py` with pre-refactor content. `understand.py` uses domain injection, falls back to core template. |
| Think | DONE | 2026-02-08 | Added `get_think_prompt_content()` to DomainConfig + KitchenConfig. Created `alfred_kitchen/domain/prompts/think_content.py` with full pre-refactor system prompt (verbatim). `_get_system_prompt()` in think.py checks domain first, falls back to template+injection. All kitchen examples, conversation management patterns, post-action table, output contract examples restored. |
| Act | DONE | 2026-02-08 | Added `get_act_prompt_content(step_type)` to DomainConfig + KitchenConfig. Created `alfred_kitchen/domain/prompts/act_content.py` with pre-refactor base, crud, and all 4 step-type contents (read, write, analyze, generate). `_get_system_prompt()` in act.py checks domain first, falls back to template assembly+injection. All kitchen examples restored: recipe_1/inv_5/gen_recipe_1 refs, recipe_ingredients cascades, semantic search, broader intent, occasions/expiry_date fields, Honey Garlic Cod, chicken/cod expiry analysis example. |
| Reply | DONE | 2026-02-08 | Added `get_reply_prompt_content()` to DomainConfig + KitchenConfig. Created `alfred_kitchen/domain/prompts/reply_content.py` with pre-refactor reply template (verbatim). `_get_prompts()` in reply.py checks domain first, falls back to core template+subdomain injection. All ~12 genericized lines restored: recipe_1/gen_recipe_1 refs, "update a recipe"/"the recipe", "Here are 5 recipes that work with your inventory", "Added eggs to your shopping list", "Your pantry has 2 cartons of milk", "Chicken expires Jan 15", "recipe or meal plan", "Want me to save this recipe?", emoji markers in table headers. User prompt refs (entity key + bottom instruction) now derived from domain entity types. |
| Summarize | DONE (no action needed) | 2026-02-08 | Clean — no regression |
| Router | DONE (no action needed) | 2026-02-08 | Already correctly structured |
