# Phase 0.1: Think Prompt Audit

## Executive Summary

Think's responsibility is to create execution plans that Act can execute step-by-step. The current prompt structure has gaps in system awareness, rule prioritization, and constraint handling.

---

## 1. Static Prompt Structure (`prompts/think.md`)

### Current Organization (242 lines)

| Section | Lines | Content |
|---------|-------|---------|
| Role | 1-11 | "You are the Planner" - minimal persona |
| Output Contract | 13-46 | JSON schemas for plan_direct/propose/clarify |
| When to Use Each | 48-58 | Decision table |
| Step Types | 62-77 | read/write/analyze/generate definitions |
| Subdomains | 79-98 | Domain tables and relationships |
| Planning Rules | 100-164 | 13 numbered rules (flat hierarchy) |
| Examples | 166-220 | 7 examples |
| Tasks | 222-233 | Task-specific guidance |
| Exit | 235-241 | Return instructions |

### Persona Analysis

**Current:**
> "You are the **Planner** — you decide how to approach a request."

**Issues:**
- No warmth or guidance style
- No awareness of position in pipeline
- No understanding of Act's limitations (stateless, sees only step description)

### Rule Hierarchy Analysis

**Current:** 13 rules numbered sequentially with no grouping:

| Rule # | Topic | Criticality |
|--------|-------|-------------|
| 1 | Match complexity | Planning |
| 2 | Batch = 1 step | Planning |
| 3 | Groups enable parallelism | Planning |
| 4 | Analyze before mutate | Planning |
| 5 | Don't over-expand scope | Scope |
| 6 | Context vs Database | Data |
| 7 | Saved = READ, not regenerate | Data |
| 8 | Linked tables | Domain |
| 9 | Count accurately | Quality |
| 10 | Dashboard = ground truth | Data |
| 11 | **Exploratory vs Actionable** | **CRITICAL** |
| 12 | Dates need full year | Format |
| 13 | Not enough data? Generate more | Planning |

**Problem:** Rule 11 (CRUD caution) is buried at position 11 with no special emphasis.

---

## 2. Dynamic Context Injection (from `think.py`)

### What Gets Injected at Runtime

```
User Prompt Structure:
├── pending_section (if previous turn was propose/clarify)
├── ## Task
│   ├── Goal (from router)
│   ├── User said (raw message)
│   ├── Agent (pantry/etc)
│   ├── Today (YYYY-MM-DD)
│   ├── Mode guidance (QUICK/COOK/PLAN/CREATE)
│   └── Entity counts
├── ---
├── profile_section (from format_profile_for_prompt)
├── dashboard_section (from format_dashboard_for_prompt)
├── dependencies_section (from get_subdomain_dependencies_summary)
├── ---
├── ## Conversation Context
│   ├── engagement_summary
│   ├── active_entities (Recent items)
│   ├── recent_turns (last 2, condensed)
│   └── history_summary (Earlier)
├── ---
└── ## Instructions (step patterns, group guidance)
```

### Context Source Functions

| Function | Source | Output |
|----------|--------|--------|
| `format_profile_for_prompt()` | preferences table | Constraints, Equipment, Likes, Cooking Schedule, Vibes |
| `format_dashboard_for_prompt()` | count queries | Inventory count, Recipe count by cuisine, Meal plan count |
| `get_subdomain_dependencies_summary()` | static | Domain relationships |
| `format_condensed_context()` | conversation state | Engagement, Recent items, Recent turns, Earlier |

### What's Missing

1. **No active constraints section** - Explicit user counts (8 meals, 2 dinners) are compressed into narrative
2. **Dashboard lacks recipe names** - Shows "Recipes: 4 saved (indian: 1, mediterranean: 1)" not actual names
3. **No archive awareness** - Think doesn't know if content was generated but not saved

---

## 3. Audit Questions Answered

### Q1: Does Think understand that Act is stateless?

**NO.** The prompt says nothing about:
- Act only sees the step description
- Each step description must be complete and self-contained
- Act cannot ask Think for clarification mid-execution

**Evidence from `think.md`:**
> "**What Act can do:** 4 CRUD tools, batch operations, annotate what it did for next step."
> "**What Act CANNOT do:** See the overall plan. Each step is isolated — cross-step reasoning is YOUR job."

This is mentioned but buried in the Subdomains section (line 97-98), not prominently featured.

### Q2: Does Think know session vs foundational preferences?

**PARTIAL.** The profile format includes:
- Hard constraints (dietary_restrictions, allergies) - clearly marked
- Current vibes (session interests)

But nothing explicitly tells Think:
- "8 meals for this week" = session preference (don't save)
- "I'm a beginner cook" = foundational preference (save to preferences)

### Q3: Does Think have enough recipe/meal plan detail?

**NO.** Dashboard shows:
```
- **Recipes:** 4 saved (indian: 1, mediterranean: 1, mexican: 1)
```

Missing:
- Actual recipe names
- Which recipes are "lighter" vs "hearty"
- Recipe cooking times
- Recipe ingredient compatibility with inventory

---

## 4. Gap Analysis

### GAP-1: No System Awareness
Think doesn't understand:
- Its position in the pipeline (step 2 of 4)
- That Act is stateless and isolated
- That Reply presents results, not Think

**Impact:** Step descriptions lack necessary context for Act to execute independently.

### GAP-2: CRUD Caution Buried
Rule 11 (exploratory vs actionable) is:
- Not at the top of the prompt
- Not emphasized as CRITICAL
- Lacks strong examples

**Impact:** Think plans write steps for exploratory requests (see step 48 in session audit).

### GAP-3: Flat Rule Hierarchy
All 13 rules are presented equally. No distinction between:
- CRITICAL (must check first)
- PLANNING (how to structure steps)
- DOMAIN (subdomain-specific)

**Impact:** LLM may prioritize less important rules over critical ones.

### GAP-4: Constraints Compressed into Narrative
When user says "8 meals, 2 lighter dinners", this becomes:
> "User requested 8 meals planned for Jan 5-9 with 4 batch prep recipes including 2 lighter dinner options"

By the next turn, this is further compressed. Explicit counts are lost.

**Impact:** Meal plan generation doesn't match explicit user requirements.

### GAP-5: No Analyze Step Pattern
For complex generation (meal plans, multiple recipes), Think should mandate:
```
read → analyze → generate
```

But this pattern is only mentioned as an example, not a rule.

**Impact:** Generate steps have high cognitive load (must read, analyze, and generate in one call).

### GAP-6: Dashboard Lacks Detail
Dashboard shows counts and cuisine breakdowns, not:
- Recipe names
- Which recipes are "lighter" vs "hearty"
- Content archive status (generated but not saved)

**Impact:** Think can't make intelligent decisions about when to read existing vs generate new.

---

## 5. Recommendations (Tentative)

Based on this audit, the design phase should consider:

1. **Add System Context Section** at top of prompt explaining pipeline position
2. **Restructure Rules** into CRITICAL > PLANNING > DOMAIN hierarchy
3. **Add Active Constraints Field** to conversation context (structured, not narrative)
4. **Mandate Analyze Pattern** for complex generation in rules
5. **Enhance Dashboard** to include recipe names and archive status
6. **Add Archive Awareness** section so Think knows what's generated but unsaved

---

## Appendix: Full Static Prompt Reference

See `prompts/think.md` (242 lines)

