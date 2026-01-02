# Act Prompt Architecture

**Document Type:** Design Reference  
**Last Updated:** December 26, 2024  
**Status:** Implemented

---

## Overview

The Act node is Alfred's **execution engine** — it receives planned steps from Think and executes them via CRUD tools. This document describes the **dynamic prompt construction** architecture that makes Act context-aware across different subdomains.

---

## Design Philosophy

| Principle | Implementation |
|-----------|----------------|
| **Context over rules** | Inject relevant guidance, not exhaustive warnings |
| **Persona over instructions** | "Be an operations manager" vs "Don't forget to normalize names" |
| **Dynamic over static** | Inject what's needed per step, not everything always |
| **Examples over warnings** | Show patterns, don't lecture |

---

## Prompt Structure

```
┌─────────────────────────────────────────────────────────────┐
│ DYNAMIC: Subdomain-Specific                                 │
├─────────────────────────────────────────────────────────────┤
│ ## Persona                                                  │
│ [Chef / Ops Manager / Planner — based on subdomain]         │
│                                                             │
│ ## Scope                                                    │
│ [What this subdomain handles, linked tables, dependencies]  │
├─────────────────────────────────────────────────────────────┤
│ GENERIC: Always Present (from act.md)                       │
├─────────────────────────────────────────────────────────────┤
│ ## Core Mechanics                                           │
│ [Tools, operators, exit contract — static baseline]         │
├─────────────────────────────────────────────────────────────┤
│ DYNAMIC: Step-Specific                                      │
├─────────────────────────────────────────────────────────────┤
│ ## Previous Step Note                                       │
│ [IDs and context from prior CRUD step — if present]         │
│                                                             │
│ ## STATUS                                                   │
│ [Step number, goal, progress, date]                         │
│                                                             │
│ ## Task                                                     │
│ [User message, step description]                            │
│                                                             │
│ ## Tool Results This Step                                   │
│ [What's been called, quick ID reference, full JSON]         │
│                                                             │
│ ## Schema                                                   │
│ [Tables for THIS subdomain only]                            │
│                                                             │
│ ## Contextual Examples                                      │
│ [1-2 patterns relevant to current step verb + context]      │
└─────────────────────────────────────────────────────────────┘
```

---

## Personas

Three persona groups cover all subdomains:

### Chef (recipes)

Recipes are complex — they have linked tables, require naming conventions, and span both creative (generate) and organizational (CRUD) work. The Chef persona splits by step type:

| Step Type | Mode | Focus |
|-----------|------|-------|
| **CRUD** | Organizational | Clean naming, useful tags, linked tables (recipes + recipe_ingredients) |
| **Generate** | Creative | Flavor balance, dietary restrictions, personalization |

### Ops Manager (inventory, shopping, preferences)

Focuses on **accurate cataloging and organization**:

- **Normalize names:** "diced chillies" → "chillies"
- **Deduplicate:** Check before adding, merge quantities
- **Tag consistently:** Location, category
- **Cross-domain awareness:** Items may come from recipes or meal plans

### Planner (meal_plan, tasks)

Focuses on **scheduling and dependencies**:

- **Meal plan is primary:** Tasks flow from it
- **Recipe linking:** Real meals should have recipes (graceful fallback if missing)
- **Task categories:** prep, shopping, cleanup, other
- **Prefer meal_plan_id:** Tasks link to meal plans, recipes derivable from there

---

## Step Notes

CRUD steps can pass context to subsequent steps via `note_for_next_step`:

```
Step 1 (recipes/crud): Creates recipe
  → note_for_next_step: "Recipe ID abc123 created with 8 ingredients"

Step 2 (meal_plan/crud): Creates meal plan entry
  → Sees previous note, uses recipe ID
  → note_for_next_step: "Meal plan entry xyz789 for lunch Dec 30"

Step 3 (tasks/crud): Creates task
  → Sees previous note, links to meal plan
```

This enables multi-step workflows without re-reading data.

---

## Subdomain Scope Configuration

Each subdomain has scope metadata that informs prompt construction:

```python
SUBDOMAIN_SCOPE = {
    "recipes": {
        "implicit_children": ["recipe_ingredients"],  # Always together
        "description": "Recipes and their ingredients",
    },
    "shopping": {
        "influenced_by": ["recipes", "meal_plan", "inventory"],
        "description": "Shopping list. Often populated from recipes or meal plans.",
    },
    "meal_plan": {
        "implicit_dependencies": ["recipes"],
        "exception_meal_types": ["prep", "other"],  # Don't need recipes
        "related": ["tasks"],
    },
    # ...
}
```

---

## Contextual Examples

Instead of static examples for all steps, we inject relevant examples based on:

| Signal | Example Triggered |
|--------|-------------------|
| Step verb = "add" + subdomain = shopping | Smart shopping pattern (read first, merge duplicates) |
| Step verb = "delete" + subdomain = recipes | Linked table delete pattern (FK-safe order) |
| Previous subdomain = recipes | Cross-domain pattern (recipe → shopping) |
| Step type = generate + subdomain = recipes | Creative recipe generation guidance |

---

## Files Involved

| File | Role |
|------|------|
| `prompts/act.md` | Static baseline (core mechanics, tools, exit contract) |
| `src/alfred/tools/schema.py` | Personas, scope config, contextual example functions |
| `src/alfred/graph/nodes/act.py` | Prompt construction, dynamic injection |
| `src/alfred/graph/state.py` | Step note fields in state |

---

## Key Design Decisions

### Why personas instead of rules?

Rules are **negative framing** ("don't do X"). Personas are **positive framing** ("be this kind of assistant"). LLMs respond better to identity-based guidance.

### Why only recipes has CRUD/Generate split?

Recipes are uniquely complex — they require both **creative** work (generating balanced recipes) and **organizational** work (clean naming, linked tables). Other subdomains are primarily CRUD-focused.

### Why step notes instead of re-reading?

Re-reading data costs tokens and tool calls. Step notes pass just enough context (IDs, counts) to enable subsequent steps without redundant queries.

### Why inject schema per subdomain?

The LLM sees only relevant tables. This:
- Reduces token usage
- Prevents confusion from irrelevant schemas
- Keeps focus tight per step

