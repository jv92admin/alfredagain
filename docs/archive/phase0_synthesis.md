# Phase 0: Audit Synthesis & Design Decisions

## Audit Summary

| Audit | Key Finding | Priority |
|-------|-------------|----------|
| Think (0.1) | No system awareness, CRUD caution buried, flat rule hierarchy | High |
| Act Quick (0.2) | Missing user profile, engagement summary, personas | Medium-High |
| Constraints (0.3) | Explicit counts compressed to narrative, lost across turns | High |

---

## Root Cause → UX Failure Mapping

| UX Failure | Root Cause | Audit |
|------------|------------|-------|
| Think planned write steps for exploratory request | CRUD caution buried in Rule 11, no emphasis | 0.1 |
| Meal plan had 4 meals instead of 8 | Explicit count lost in summarization | 0.3 |
| Too many dinner breaks in final plan | "8 meals with gaps" ambiguous after compression | 0.3 |
| Reply summarized recipes instead of showing full | Not from audit (Reply prompt issue) | - |
| Dashboard showed "4 saved" when 0 were saved | Not from audit (state sync bug) | - |

---

## Design Decisions

### D1: Think Prompt Restructuring

**Gap Addressed:** GAP-1, GAP-2, GAP-3 from Think audit

**Decision:** Restructure Think prompt with:

1. **System Context at TOP** (before Role):
   - Pipeline position (step 2 of 4)
   - Act is stateless, only sees step description
   - Each step must be self-contained

2. **CRITICAL Rules Section** (before Planning Rules):
   - CRUD caution (exploratory = no write steps)
   - Moved from Rule 11 to top prominence

3. **Rule Hierarchy**:
   - CRITICAL (check first)
   - PLANNING (how to structure)
   - DOMAIN (subdomain-specific)

**Files:** `prompts/think.md`

### D2: Subdomain Dependencies + Analyze Pattern

**Gap Addressed:** GAP-5 from Think audit

**Decision:** Add explicit dependencies table and mandate analyze pattern:

```markdown
| Subdomain | Required Reads | Then |
|-----------|---------------|------|
| meal_plans | recipes, inventory | analyze → generate |
| shopping | inventory | analyze → generate |
| recipes (2+) | inventory, preferences | analyze → generate |
```

Pattern: `read → analyze → generate` for complex generation.

**Files:** `prompts/think.md`

### D3: Act Quick Context Enhancement

**Gap Addressed:** All gaps from Act Quick audit

**Decision:** Update `build_act_quick_prompt()` to include:

1. **Engagement summary** (session awareness)
2. **User preferences compact** (allergies, restrictions)
3. **Subdomain persona** (behavioral guidance)

**Files:** 
- `src/alfred/prompts/injection.py`
- `src/alfred/graph/nodes/act.py` (pass new params)

### D4: Active Constraints System

**Gap Addressed:** All gaps from Constraints audit

**Decision:** Implement structured constraint preservation:

1. **Extraction:** Add to Understand output (or simple LLM call)
2. **Storage:** New `active_constraints` field in ConversationContext
3. **Injection:** 
   - Think: Prominent constraints section
   - Act (generate): In user context section
4. **Expiry:** After 5 turns or explicit override

**Model:**
```python
class ActiveConstraints(BaseModel):
    meal_count: int | None = None
    date_range: str | None = None
    recipe_count: int | None = None
    lighter_dinner_count: int | None = None
    custom: dict[str, Any] | None = None
    source_turn: int = 0
    expires_at_turn: int | None = None
```

**Files:**
- `src/alfred/graph/nodes/understand.py` or new extraction
- `src/alfred/memory/conversation.py`
- `src/alfred/graph/nodes/think.py`
- `src/alfred/prompts/injection.py`

### D5: Reply Magazine Editor Persona

**Gap Addressed:** Observation from session (Reply summarizing recipes)

**Decision:** Strengthen Reply prompt for recipe presentation:

- Full ingredients list (not summary)
- Complete instructions (not truncated)
- "Magazine editor" persona for generated content

**Files:** `prompts/reply.md`

### D6: Linked Tables Split Pattern

**Gap Addressed:** From session audit (UUID errors, complex same-step operations)

**Decision:** Update Think to plan TWO steps for recipe writes:

1. **Write recipes** (parent table) → note IDs
2. **Write recipe_ingredients** (child table) → use IDs from note

**Files:** `prompts/think.md`

### D7: Dashboard Recipe Names

**Gap Addressed:** GAP-6 from Think audit

**Decision:** Enhance dashboard to show recipe names, not just counts:

```markdown
- **Recipes:** 4 saved
  - Indian: Paneer & Veggie Skillet
  - Mediterranean: Chickpea Rice Bowl
```

**Files:** `src/alfred/background/profile_builder.py`

---

## Implementation Priority

| Priority | Decision | Effort | Impact | Dependencies |
|----------|----------|--------|--------|--------------|
| 1 | D1: Think CRUD Caution + System Context | Low | High | None |
| 2 | D5: Reply Magazine Editor | Low | High | None |
| 3 | D2: Subdomain Dependencies | Low | Medium | D1 |
| 4 | D4: Active Constraints | Medium | High | None |
| 5 | D3: Act Quick Context | Low | Medium | None |
| 6 | D6: Linked Tables Split | Medium | Medium | D1 |
| 7 | D7: Dashboard Recipe Names | Low | Medium | None |

---

## Implementation Plan

### Phase 2.1: Think Prompt (D1, D2, D6)

1. Add system context section at top
2. Add CRITICAL rules section  
3. Restructure rule hierarchy
4. Add subdomain dependencies table
5. Add analyze pattern guidance
6. Add linked tables split pattern

### Phase 2.2: Reply Prompt (D5)

1. Add magazine editor persona for recipes
2. Add explicit instructions for full content display

### Phase 2.3: Constraints System (D4)

1. Define ActiveConstraints model
2. Add extraction logic (simple patterns or LLM)
3. Add to ConversationContext
4. Inject to Think prompt
5. Inject to Act (generate steps)
6. Add expiry logic to Summarize

### Phase 2.4: Act Quick (D3)

1. Update `build_act_quick_prompt()` signature
2. Pass engagement_summary and user_preferences from act.py
3. Add to prompt template

### Phase 2.5: Dashboard (D7)

1. Fetch recipe names in `build_kitchen_dashboard()`
2. Update `format_dashboard_for_prompt()` to show names

---

## Deferred / Out of Scope

| Item | Reason |
|------|--------|
| Dashboard sync bug (4 saved when 0) | Separate investigation needed |
| UUID generation issues | Supabase-side, not prompt engineering |
| Entity lifecycle improvements | V4 scope |

