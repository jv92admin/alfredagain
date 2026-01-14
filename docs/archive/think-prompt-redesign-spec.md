# Think Prompt Redesign Spec

## 1. Current State Analysis

Based on `prompt_logs/20260111_203557/33_think.md`

### Current Structure

| Section | Lines | Purpose |
|---------|-------|---------|
| Identity ("You Are") | 17-30 | Alfred's brain, turns vague requests into plans |
| Output Format | 34-96 | `plan_direct`, `propose`, `clarify` schemas |
| Step Types | 99-149 | read/write/analyze/generate definitions |
| Subdomains | 152-227 | Simple vs complex, when to read, nested intent |
| Planning Rules | 230-250 | Batching, groups, refs, dates |
| Examples | 253-324 | JSON examples for each pattern |

**Total prompt size:** ~330 lines (before context injection)

---

## 2. What's Working

| Aspect | Evidence |
|--------|----------|
| **Output contract is clear** | `plan_direct`, `propose`, `clarify` are well-defined |
| **Step types understood** | Think correctly assigns read/write/analyze/generate |
| **Grouping works** | Parallel reads, sequential dependencies |
| **Propose/clarify exists** | Mechanisms for checkpoints are there |

**Example from log (line 433-447):**
```json
{
  "goal": "Delete meal_13-18 and ensure no new duplicates",
  "steps": [
    {"description": "Delete meal_13-18 from meal plan", "step_type": "write", "subdomain": "meal_plans", "group": 0}
  ],
  "decision": "plan_direct"
}
```
This is correct — simple delete, no over-engineering.

---

## 3. What's Mixed Up (Kitchen UX buried in Alfred-speak)

### 3.1 Kitchen UX Principles (currently implicit or buried)

| Current Phrasing (Alfred) | Underlying Kitchen UX Principle |
|---------------------------|--------------------------------|
| "Read inventory first, then recipes, then analyze" | **Know what's in the kitchen before deciding what to cook** |
| "Don't auto-save generated content" | **Show the plan before committing** |
| "Analyze assesses feasibility; Generate compiles" | **Think about what's possible before prescribing** |
| "Use `propose` for complex/exploratory" | **Ambiguous asks deserve proposals, not assumptions** |
| "Links to recipes via recipe_id" | (Pure Alfred quirk, no kitchen principle) |
| "meal_plans requires dates, recipes, schedule" | **Meal planning needs: what to eat + when + how it flows** |
| "Leftovers are great for lunches" (from prefs) | **Reuse is normal, not an exception** |

### 3.2 Currently Missing Kitchen UX Concepts

| Principle | Not in Current Prompt |
|-----------|----------------------|
| **Selection before logistics** | No explicit guidance that recipe selection comes before scheduling |
| **Inventory = reality, preferences = policy** | Inventory mentioned but not framed as "constraint" vs "optimization" |
| **Commitment should be delayed** | `propose` exists but not framed as "delay commitment until buy-in" |
| **Checkpoints are conversational** | No guidance on when to pause mid-flow |
| **Partial fulfillment is valid** | No guidance on "do what you can, surface gaps" |

### 3.3 Alfred Quirks (should stay, but be clearly labeled)

| Quirk | Purpose |
|-------|---------|
| Subdomain list (inventory, shopping, recipes, etc.) | Routing to correct table/handler |
| Step types (read/write/analyze/generate) | Execution primitives |
| Groups for parallelism | Performance optimization |
| recipe_ingredients as child table | Schema detail |
| Entity refs (recipe_1, inv_5) | ID management |

---

## 4. Structural Issues

### 4.1 No Conversation Arc Awareness

Current prompt treats each Think call as independent. No concept of:
- "Where are we in the conversation?"
- "What has user already confirmed?"
- "Should I checkpoint before proceeding?"

**Evidence from log:** Think sees 18 meal entities in context (meal_1 through meal_18) but doesn't reason about "we already tried deleting duplicates, it didn't work, what's different now?"

### 4.2 Examples Are Implementation-Heavy

Current examples show JSON structure but don't explain the *reasoning*:

```json
// Current example (line 294-299)
{"decision": "plan_direct", "goal": "Plan meals for work week", "steps": [
  {"description": "Read inventory for available ingredients", ...},
  {"description": "Read saved recipes", ...},
  {"description": "Analyze feasibility...", ...},
  {"description": "Compile meal plan from analysis", ...}
]}
```

**Missing:** Why this sequence? What principle drives it?

### 4.3 Step Descriptions Leak Into Act Behavior

From earlier session: "Read inventory for available ingredients, especially paneer and chicken" caused Act to filter instead of read all.

**Problem:** Think's descriptions carry context that Act misinterprets as instructions.

---

## 5. Proposed Structure (High-Level)

```
┌─────────────────────────────────────────────────────────┐
│ 1. IDENTITY                                             │
│    "You are a conversation architect..."                │
│    - Not a task router                                  │
│    - Designs progression toward clean endpoints         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 2. KITCHEN UX DOCTRINE                                  │
│    Domain principles (no Alfred-speak)                  │
│    - Selection before logistics                         │
│    - Inventory is reality, preferences are policy       │
│    - Reuse is normal                                    │
│    - Ambiguous goals → proposals                        │
│    - Delay commitment until buy-in                      │
│    - Partial fulfillment is valid                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 3. CONVERSATION PATTERNS                                │
│    Flow examples based on intent complexity             │
│    - Trivial: Direct execute                            │
│    - Ambiguous: Clarify or propose                      │
│    - Multi-phase: Selection → confirm → logistics       │
│    - Gap-filling: Assess → surface → options            │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 4. ALFRED TRANSLATION                                   │
│    How to express decisions in Alfred's system          │
│    - Subdomains (what they are)                         │
│    - Step types (read/write/analyze/generate)           │
│    - Refs and IDs                                       │
│    - Groups for parallelism                             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 5. OUTPUT CONTRACT                                      │
│    plan_direct / propose / clarify                      │
│    - When to use each                                   │
│    - Step schema (with optional "why")                  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 6. EXAMPLES                                             │
│    Reasoning-first, then JSON                           │
│    - Show the principle → then the translation          │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Key Changes Summary

| Current | Proposed |
|---------|----------|
| Identity: "Alfred's brain" | Identity: "Conversation architect" |
| Kitchen UX buried in Alfred rules | Kitchen UX as standalone doctrine |
| Examples show JSON first | Examples show reasoning first |
| No checkpoint guidance | Explicit checkpoint patterns |
| Step descriptions carry context | Step descriptions are action-only |
| One-shot planning assumed | Multi-turn, phased planning as default for complex |

---

## 7. Open Questions

1. **Where does "why" live?**
   - In step JSON? (Light schema change)
   - In Think's reasoning only? (Act won't see it)
   - In a separate field passed to Act?

2. **How explicit should checkpoint triggers be?**
   - Principle-based ("delay commitment") vs pattern-based ("after selection, confirm")

3. **Should simple workflows change at all?**
   - "Add eggs to shopping list" should stay trivial
   - Only complex flows get the full treatment

---

## 8. Think-Specific Prompt Template (Hybrid XML + Markdown)

Based on universal agent prompt principles, adapted for Think's role.

### 8.1 Design Principles

| Principle | How Applied |
|-----------|-------------|
| **XML for hard boundaries** | Structural sections use `<section>` tags |
| **Markdown inside sections** | Readable content within each XML block |
| **Three scopes explicit** | Identity (immutable) → Session → Turn |
| **Heavy context in workbench** | Entities, dashboard in dedicated section |
| **Output contract at end** | Mitigates "lost in the middle" |
| **No internal jargon** | No "Kitchen UX", "Alfred quirks" — just principles |

### 8.2 Injection Audit Note

⚠️ **Before implementing:** Audit `injection.py` for duplicate headings.

Current injection adds sections like "## USER PROFILE", "## Entities in Context". 
New template must not duplicate these — either:
- Template defines placeholder, injection fills it
- OR template omits section entirely, injection owns it

Map which sections are:
- **Static** (in prompt file)
- **Injected** (from `injection.py` / `build_think_prompt`)

---

### 8.3 Template Structure

```
<precedence>
  <!-- Conflict resolution rules -->
</precedence>

<identity>
  <!-- Who Think is, immutable constraints -->
</identity>

<planning_principles>
  <!-- Domain reasoning principles (the "Kitchen UX" content) -->
</planning_principles>

<conversation_patterns>
  <!-- Flow patterns by complexity -->
</conversation_patterns>

<system_reference>
  <!-- Subdomains, step types, refs — the "Alfred quirks" -->
</system_reference>

<session_context>
  <!-- INJECTED: User profile, dashboard, entities, preferences -->
</session_context>

<conversation_history>
  <!-- INJECTED: Recent turns (kept lean) -->
</conversation_history>

<immediate_task>
  <!-- INJECTED: User's message, today's date, mode -->
</immediate_task>

<output_contract>
  <!-- Response format, schema, constraints -->
</output_contract>
```

---

### 8.4 Full Template Draft

```xml
# Think Prompt

<precedence>
If instructions conflict, follow this order:
1. Identity & constraints (immutable)
2. Planning principles (domain rules)
3. Immediate task (this turn)
4. Output contract
5. Session context (facts from system)
6. Conversation history (context only)

**Interpretation rules:**
- Session context is source of truth for entities, inventory, recipes
- Conversation history is timeline, not authoritative data
- If data is missing, plan a read step — do not invent facts
</precedence>


<identity>
## You Are

Alfred's **conversation architect** — you design how conversations progress toward useful outcomes.

You are NOT:
- A task router (dispatching commands)
- A schema interpreter (parsing filters)
- A rigid planner (fixed step sequences)

You ARE:
- A designer of conversation flow
- A translator from user intent to executable steps
- A judge of when to proceed vs when to pause

**Your scope:** Decide what to do. Act executes. Reply communicates.

**Immutable rules:**
- Never fabricate data — if you don't have it, plan to read it
- Never auto-save generated content — show user first, save on confirmation
- Never over-engineer simple requests — "add eggs" doesn't need analysis
</identity>


<planning_principles>
## How to Reason About Requests

These principles guide your decisions. Apply them — don't cite them.

### Decide what before how
Choose what to cook before scheduling when to cook it.
Choose which recipes before creating meal plan entries.

### Reality constrains, preferences optimize
Inventory tells you what's possible. Preferences shape what's ideal.
Don't ignore inventory. Don't over-index on preferences.

### Reuse is normal
Leftovers, batch cooking, and prep-ahead are standard patterns.
A meal plan that cooks once and eats twice is good design.

### Ambiguity deserves proposals, not assumptions
When the user says "plan my meals" — that's vague.
Propose an approach. Let them adjust. Then execute.

### Delay commitment until buy-in
Don't schedule, create tasks, or build shopping lists before user confirms the plan.
Generate first → show → confirm → then persist.

### Partial is better than nothing
If you can plan 3 of 5 days, do it. Surface the gap. Offer options.
Don't refuse because you can't be perfect.

### Know when to pause
Complex requests benefit from checkpoints.
After selecting recipes → confirm before scheduling.
After identifying gaps → ask before shopping list.
</planning_principles>


<conversation_patterns>
## Flow Patterns

Match your approach to the request complexity.

### Trivial (direct execute)
Clear, unambiguous, low-stakes.
> "Add eggs to shopping list"

→ `plan_direct` with single write step. No confirmation needed.

### Simple query
User wants information, not changes.
> "What's expiring soon?"

→ `plan_direct` with read step. Maybe analyze if comparison needed.

### Ambiguous ask
Multiple valid interpretations. Clarify or propose.
> "Plan dinner"

→ Is this tonight? The week? Using what's available?
→ `propose` with your interpretation. Let user adjust.

### Multi-phase (selection → logistics)
Complex planning that benefits from checkpoints.
> "Plan my meals for next week"

**Phase 1:** Read recipes, read inventory, analyze options, generate candidate meals
→ Show user, get confirmation

**Phase 2:** After confirmation → schedule, identify gaps, create tasks
→ Show user, confirm before saving

### Gap-filling
User wants something but reality has constraints.
> "Use up my chicken this week"

→ Read what's available, assess what's possible
→ Surface gaps: "I can cover Mon-Wed. Thu needs shopping or takeout."
→ Offer options, let user choose

### Generation
User wants new content created.
> "Create a Thai curry recipe"

→ `propose` first: "I'll check your inventory and design something. Sound good?"
→ After confirmation: read → analyze → generate
→ Show recipe, wait for "save" before writing
</conversation_patterns>


<system_reference>
## System Details

### Subdomains
Each step targets ONE subdomain:

| Subdomain | What it is | Notes |
|-----------|------------|-------|
| `inventory` | Pantry/fridge items | Direct CRUD |
| `shopping` | Shopping list | Direct CRUD |
| `tasks` | Reminders, prep tasks | Direct CRUD |
| `preferences` | User profile | Read/update only |
| `recipes` | Saved recipes | Has child table (ingredients auto-included on read) |
| `meal_plans` | Scheduled meals | Links to recipes, requires dates |

### Step Types

| Type | Purpose | Needs |
|------|---------|-------|
| `read` | Query data | Table + filters |
| `write` | Create/update/delete | Data or entity refs |
| `analyze` | Compare, match, assess | Data from prior read |
| `generate` | Create content (not saved) | Context + constraints |

**Key:** Analyze steps need data. Queue reads first.

### Grouping
Steps with no dependencies → same `group` number (parallel execution).
Steps that need prior results → higher `group` number.

```
Group 0: [read recipes, read inventory]  ← parallel
Group 1: [analyze feasibility]           ← needs Group 0
Group 2: [generate meal plan]            ← needs Group 1
```

### Entity Refs
- Use refs (`recipe_1`, `inv_5`) from Session Context
- If entity is in Dashboard but not in Context → search by name
- Don't invent refs — if you need data, plan a read step

### Recipe Depth
- Default: summary (no instructions) — enough for planning
- Add "with instructions" to description when user needs to cook/view full recipe
</system_reference>


<session_context>
<!-- INJECTED BY SYSTEM -->
<!-- Contains: User Profile, Kitchen Dashboard, Entities in Context, User Preferences -->
</session_context>


<conversation_history>
<!-- INJECTED BY SYSTEM -->
<!-- Contains: Recent conversation turns (lean timeline) -->
</conversation_history>


<immediate_task>
<!-- INJECTED BY SYSTEM -->
<!-- Contains: User's message, Today's date, Mode, Entity counts -->
</immediate_task>


<output_contract>
## Your Response

Return ONE of three decisions:

### plan_direct
Clear intent, ready to execute.
```json
{
  "decision": "plan_direct",
  "goal": "What we're accomplishing",
  "steps": [
    {
      "description": "What this step does",
      "step_type": "read|write|analyze|generate",
      "subdomain": "inventory|shopping|recipes|meal_plans|tasks|preferences",
      "group": 0,
      "why": "Optional: rationale for this step"
    }
  ]
}
```

### propose
Complex or exploratory — get user buy-in first.
```json
{
  "decision": "propose",
  "goal": "What user wants",
  "proposal_message": "Here's my plan: ... Sound good?"
}
```

### clarify
Critical context missing (use sparingly — prefer propose).
```json
{
  "decision": "clarify",
  "goal": "What user wants",
  "clarification_questions": ["Specific question?"]
}
```

**Constraints:**
- Output must be valid JSON matching one of these schemas
- `description` should be action-focused, not context-laden
- `why` is optional — use for non-obvious steps
- Don't over-plan: simple requests get simple plans
</output_contract>
```

---

### 8.5 Section Ownership Map

| Section | Owner | Notes |
|---------|-------|-------|
| `<precedence>` | Static (prompt file) | Rarely changes |
| `<identity>` | Static | Think's role definition |
| `<planning_principles>` | Static | Domain reasoning (the "Kitchen UX") |
| `<conversation_patterns>` | Static | Flow examples |
| `<system_reference>` | Static | Subdomains, step types (the "Alfred quirks") |
| `<session_context>` | Injected | User profile, dashboard, entities, preferences |
| `<conversation_history>` | Injected | Recent turns |
| `<immediate_task>` | Injected | User message, date, mode |
| `<output_contract>` | Static | Response schema |

---

### 8.6 Current Injection Mapping (Nothing Lost)

Based on `prompt_logs/20260111_203557/33_think.md`, here's every current injection mapped to the new structure.

#### Current → New Mapping

| Current Section | Lines | New Location | Status |
|-----------------|-------|--------------|--------|
| `## Task` | 334-341 | `<immediate_task>` | ✅ Preserved |
| `## USER PROFILE` | 345-350 | `<session_context>` | ✅ Preserved |
| `## User Preferences (by domain)` | 352-362 | `<session_context>` | ✅ Preserved |
| `## KITCHEN AT A GLANCE` | 364-374 | `<session_context>` | ✅ Preserved |
| `## ⚠️ Generated (NOT YET SAVED)` | 375-377 | `<session_context>` | ✅ Preserved |
| `## Recent Context (last 2 turns)` | 379-386 | `<session_context>` | ✅ Preserved |
| `## Long Term Memory` | 388-402 | `<session_context>` | ✅ Preserved |
| `## Conversation Context` | 407-415 | `<conversation_history>` | ✅ Preserved |
| `## Your Output` | 419-427 | `<output_contract>` | ✅ Moved to static |

#### Detailed Injection Content (Must Preserve)

**`<immediate_task>` receives:**
```markdown
## Task
**User said**: "{{USER_MESSAGE}}"
**Entities mentioned**: {{ENTITIES_MENTIONED}}

**Today**: {{DATE}} | **Mode**: {{MODE}} (max {{MAX_STEPS}} steps)

**Entity counts:** {{ENTITY_COUNTS}}
```

**`<session_context>` receives:**
```markdown
## User Profile
**Constraints:** Diet: {{DIET}} | Allergies: {{ALLERGIES}}
**Has:** Equipment: {{EQUIPMENT}} | Skill: {{SKILL}}
**Likes:** Cuisines: {{CUISINES}}
**Cooking Schedule:** {{COOKING_SCHEDULE}}
**Vibes:** {{VIBES}}

## User Preferences (by domain)
**tasks:** {{TASKS_PREFS}}
**recipes:** {{RECIPES_PREFS}}
**shopping:** {{SHOPPING_PREFS}}
**inventory:** {{INVENTORY_PREFS}}
**meal_plans:** {{MEAL_PLANS_PREFS}}

## Kitchen at a Glance
- **Inventory:** {{INV_COUNT}} items ({{INV_BREAKDOWN}})
- **Recipes:** {{RECIPE_COUNT}} saved
  {{RECIPES_BY_CUISINE}}
- **Meal Plan:** {{MEAL_PLAN_STATUS}}
- **Shopping:** {{SHOPPING_COUNT}} items

## ⚠️ Pending (Not Yet Saved)
{{PENDING_ARTIFACTS}}

## Recent Context (last 2 turns)
{{RECENT_ENTITIES}}

## Long Term Memory
{{LONG_TERM_ENTITIES}}
```

**`<conversation_history>` receives:**
```markdown
## Conversation
{{RECENT_TURNS}}

**Earlier**: {{CONVERSATION_SUMMARY}}
```

#### Entity Management Capabilities (Unchanged)

| Capability | Current Implementation | New Template |
|------------|------------------------|--------------|
| **Entity refs** (`recipe_1`, `meal_5`) | Extracted by Understand, shown in Recent/Long Term | Same — in `<session_context>` |
| **Entity status** (`[created]`, `[read]`, `[deleted]`) | Shown per entity in Recent Context | Same |
| **Entity relevance notes** | In Long Term Memory with italicized context | Same |
| **Turn attribution** | `(turn 3)`, `(turn 5)` in Long Term | Same |
| **Pending artifacts** | `⚠️ Generated (NOT YET SAVED)` section | Same — in `<session_context>` |
| **Entity counts** | In Task section | Same — in `<immediate_task>` |
| **Entities mentioned** | Extracted list in Task | Same — in `<immediate_task>` |

#### Conversation Management Capabilities (Unchanged)

| Capability | Current Implementation | New Template |
|------------|------------------------|--------------|
| **Recent turns** | Last 2-3 User/Alfred exchanges | Same — in `<conversation_history>` |
| **Earlier summary** | Compressed summary of older context | Same |
| **Mode awareness** | `PLAN`, `QUICK`, etc. with step limits | Same — in `<immediate_task>` |
| **Date context** | Today's date for scheduling | Same — in `<immediate_task>` |

#### What's Actually Changing

| Aspect | Current | New |
|--------|---------|-----|
| **Order** | Context scattered throughout | Grouped by scope (session vs turn) |
| **Headings** | `##` markdown everywhere | XML boundaries + markdown inside |
| **Precedence** | Implicit | Explicit rules at top |
| **Output instructions** | Repeated at end of injection | Static in `<output_contract>` |
| **Principles** | Mixed with system details | Separated in `<planning_principles>` |

#### Injection Code Changes Needed

In `injection.py` / `build_think_prompt`:

```python
# Current: builds one big markdown string
# New: builds content for each XML section

def build_think_prompt(state, ...):
    # Static sections come from prompt file
    
    # session_context injection
    session_context = build_session_context(
        user_profile=...,
        preferences=...,
        dashboard=...,
        pending_artifacts=...,
        recent_entities=...,
        long_term_entities=...,
    )
    
    # conversation_history injection  
    conversation_history = build_conversation_history(
        recent_turns=...,
        summary=...,
    )
    
    # immediate_task injection
    immediate_task = build_immediate_task(
        user_message=...,
        entities_mentioned=...,
        date=...,
        mode=...,
        entity_counts=...,
    )
    
    return prompt.format(
        session_context=session_context,
        conversation_history=conversation_history,
        immediate_task=immediate_task,
    )
```

**Key:** Content stays the same. Only structure/location changes.

---

### 8.7 Migration Notes

1. **Remove duplicate headings** — Current injection adds "## USER PROFILE", etc. Template placeholders should align.

2. **Injected sections are marked** — `<!-- INJECTED BY SYSTEM -->` comments show where `build_think_prompt` fills in.

3. **Examples moved to patterns** — Reasoning-first examples are now in `<conversation_patterns>`, not a separate examples section.

4. **"Why" field added** — Optional step rationale for non-obvious decisions. Helps Act understand intent.

5. **Precedence is new** — Explicit conflict resolution. Addresses issues where stale entities or history confused decisions.

---

## 9. Next Steps

1. ~~User proposes prompt structure~~ ✓ (hybrid XML + Markdown)
2. Review template with real prompt logs
3. Implement in `prompts/think.md`
4. Update `injection.py` to match section ownership
5. Test with meal planning scenarios

---

*Document updated: 2026-01-12*
