# Act Quick Node — Prompt Regression Audit

**Pre-refactor:** `prompt_logs_downloaded/20260203_014946/88_act_quick.md`
**Post-refactor:** `prompt_logs/20260207_235146/10_act_quick.md`

## System Prompt

Act Quick uses the same system prompt as regular Act (the core Act template). The differences mirror the Act node audit exactly:

| Pre-refactor | Post-refactor |
|---|---|
| Same core Act template as pre-refactor Act | Same core Act template as post-refactor Act |
| Kitchen examples inline | Generic placeholders + "Kitchen-Specific Read Patterns" injection |

See [03_act.md](03_act.md) for the full system prompt diff.

## User Prompt (Dynamic)

The user prompt is entirely dynamic — schema, step description, entities, context. Structure is identical in both versions. The subdomain-specific content (schema tables, field enums, examples) comes from domain injection and is correctly kitchen-specific in both.

**Notable:** The post-refactor Act Quick includes a "Kitchen-Specific Read Patterns" section injected after the generic core template, same as regular Act. This section correctly contains:
- Broader Intent Before Filtering (pantry/fridge/freezer)
- Think Intent Examples (recipes, inventory)
- Semantic Search (Recipes only)
- Kitchen-Specific Notes

## Verdict: SAME AS ACT (Mixed)

Act Quick follows the same pattern as Act — architecturally reasonable split with useless generic placeholders in the core template. See Act audit for details.
