# Phase 0.2: Act Quick vs Act Audit

## Executive Summary

Act Quick is designed as a fast path for simple single-step queries. However, it's currently a stripped-down version lacking critical context that Act receives. This creates inconsistencies and potential for errors.

---

## 1. Context Injection Comparison

### Act (Normal) Context Sources

| Context Section | Source | Purpose |
|-----------------|--------|---------|
| Conversation History | `format_full_context()` | Last 2 turns, entities, engagement summary |
| User Profile | `format_profile_for_prompt()` | Constraints, equipment, cuisines (for analyze/generate) |
| Subdomain Content | `get_full_subdomain_content()` | Intro + step-type persona |
| Contextual Examples | `get_contextual_examples()` | Pattern-matched examples |
| Turn Entities | `_format_turn_entities()` | IDs created this turn for cross-step linking |
| Previous Step Results | `_format_step_results()` | Data from prior steps |
| Content Archive | `content_archive` state | Generated content from previous turns |
| Schema | `get_schema_with_fallback()` | Database schema |
| Today's Date | `date.today()` | For date inference |

### Act Quick Context Sources

| Context Section | Source | Purpose |
|-----------------|--------|---------|
| Intent | `quick_intent` from Understand | What to do |
| User Message | `user_message` from state | Raw user input |
| Subdomain Intro | `get_subdomain_intro()` | Basic domain description |
| Schema | `get_schema_with_fallback()` | Database schema |
| Today's Date | `date.today()` | For date inference |
| Quick Examples | `_get_quick_mode_examples()` | Subdomain-specific CRUD examples |

### Gap Analysis Table

| Context | Act | Act Quick | Gap Impact |
|---------|-----|-----------|------------|
| **Engagement Summary** | ✅ Via `format_full_context` | ❌ Missing | No session awareness |
| **User Profile** | ✅ For analyze/generate | ❌ Missing | No allergy/restriction awareness |
| **Subdomain Persona** | ✅ Step-type specific | ❌ Only basic intro | No behavioral guidance |
| **Conversation History** | ✅ Last 2 turns | ❌ Missing | No context from prior turns |
| **Active Entities** | ✅ IDs for reference | ❌ Missing | Can't resolve "that recipe" |
| **Turn Entities** | ✅ Cross-step linking | N/A (single step) | N/A |
| **Content Archive** | ✅ Generated content | ❌ Missing | Can't access unsaved content |
| **Schema** | ✅ | ✅ | - |
| **Today's Date** | ✅ | ✅ | - |

---

## 2. Prompt Structure Comparison

### Act Prompt Structure (Read/Write Steps)

```
{subdomain_content}
---
## STATUS
| Step | X of Y |
| Goal | step description |
| Type | read/write |
| Today | YYYY-MM-DD |
---
## 1. Task
User said: "..."
Your job this step: **{step_description}**
---
{contextual_examples}
---
## 2. Data Available
{turn_entities}
{prev_step_results}
{archive_section}
---
## 3. Context
{conversation_section}
---
## DECISION
...
```

### Act Quick Prompt Structure

```
# Act Quick Mode

Execute ONE tool call and return the result. No step_complete loop.

## Tools
| Tool | Purpose | Required Params |
|------|---------|-----------------|
...

## Filter Syntax
...

## Output Contract
Return JSON with `tool` and `params`.
---
## Intent
{intent}

## User Message
{user_message}

## Today
{today}

## Subdomain
{subdomain_intro}

## Schema
{schema}

## Quick Examples
{subdomain_examples}

## Execute
Call the appropriate db_ tool for this intent. Return tool and params.
```

---

## 3. Key Differences

### 3.1 Persona

**Act:** Has subdomain-specific personas with behavioral guidance:
```markdown
**Chef Mode (Search)**
- Use OR filters for fuzzy keyword search
- Join `recipe_ingredients` by recipe_id for full details
```

**Act Quick:** No persona, just "Execute ONE tool call".

### 3.2 User Awareness

**Act:** Gets user profile with:
- Dietary restrictions (HARD constraints)
- Allergies
- Equipment available
- Cuisines preferences

**Act Quick:** No user profile. Could potentially:
- Add items to shopping that user is allergic to
- Create records that violate dietary restrictions

### 3.3 Session Awareness

**Act:** Gets engagement summary like:
> "User is planning rice bowls for next week, focusing on batch prep"

**Act Quick:** No session context. Each call is isolated.

### 3.4 Entity Resolution

**Act:** Gets active entities for reference resolution:
```markdown
- recipe: Mediterranean Chicken Bowl (id: `abc123`)
- meal_plan: Tuesday dinner (id: `def456`)
```

**Act Quick:** No entity awareness. Can't resolve "that recipe".

---

## 4. Risk Analysis

### RISK-1: User Safety (Medium-High)
Without user profile, Act Quick could:
- Add items user is allergic to
- Ignore dietary restrictions

**Example:** User says "add peanuts to shopping" but has peanut allergy.
- Act would check profile and potentially warn
- Act Quick has no way to know

### RISK-2: Context Loss (Medium)
Without conversation history, Act Quick may:
- Misinterpret ambiguous references
- Miss context from prior turns

**Example:** User says "add more of those tomatoes"
- Act could see prior turn mentioned "cherry tomatoes"
- Act Quick can only guess from user message

### RISK-3: Inconsistent Behavior (Low)
Different personas between Act and Act Quick may cause:
- Naming inconsistencies (how items are labeled)
- Different filter strategies

---

## 5. Recommendations

### 5.1 Add Shared Context (High Priority)

Update `build_act_quick_prompt()` signature:

```python
def build_act_quick_prompt(
    intent: str,
    subdomain: str,
    action_type: str,
    schema: str,
    today: str,
    user_message: str = "",
    engagement_summary: str = "",      # NEW
    user_preferences: dict | None = None,  # NEW
) -> tuple[str, str]:
```

### 5.2 Add Compact User Preferences (High Priority)

Format user preferences compactly:
```markdown
## User Profile (Quick)
Allergies: shellfish, peanuts
Diet: vegetarian
```

### 5.3 Add Subdomain Persona (Medium Priority)

Use `get_persona_for_subdomain(subdomain, action_type)` to inject behavioral guidance.

### 5.4 Consider Entity Context (Low Priority)

For update/delete operations, might need active entities for resolution.

---

## 6. Code Locations

| Component | File | Lines |
|-----------|------|-------|
| Act Quick Node | `src/alfred/graph/nodes/act.py` | 1354-1495 |
| Act Quick Prompt Builder | `src/alfred/prompts/injection.py` | 416-518 |
| Act Node | `src/alfred/graph/nodes/act.py` | 663-1100+ |
| Subdomain Personas | `src/alfred/prompts/personas.py` | 67-189 |
| Profile Formatter | `src/alfred/background/profile_builder.py` | 214-279 |

---

## Appendix: Act Quick System Prompt (Current)

```markdown
# Act Quick Mode

Execute ONE tool call and return the result. No step_complete loop.

## Tools

| Tool | Purpose | Required Params |
|------|---------|-----------------|
| `db_read` | Fetch rows | table, filters, limit |
| `db_create` | Insert row(s) | table, data |
| `db_update` | Modify rows | table, filters, data |
| `db_delete` | Remove rows | table, filters |

## Filter Syntax

Structure: `{"field": "<column>", "op": "<operator>", "value": <value>}`

| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Exact match | `{"field": "id", "op": "=", "value": "uuid"}` |
| `>` `<` `>=` `<=` | Comparison | `{"field": "quantity", "op": ">", "value": 5}` |
| `in` | Value in array | `{"field": "name", "op": "in", "value": ["milk", "eggs"]}` |
| `ilike` | Pattern match | `{"field": "name", "op": "ilike", "value": "%chicken%"}` |
| `is_null` | Null check | `{"field": "expiry_date", "op": "is_null", "value": true}` |

## Output Contract

Return JSON with `tool` and `params`. Extract values from the intent.

Example: "Add 1lb popcorn" → 
`{"tool": "db_create", "params": {"table": "inventory", "data": {"name": "popcorn", "quantity": 1, "unit": "lb"}}}`
```

