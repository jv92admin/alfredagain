# Act - GENERATE Step

## Purpose

Create new content: recipes, meal plans, suggestions, ideas.

**NO database calls.** You create content that may be saved in a later step.

---

## How to Execute

1. Read the step description — know what to generate
2. Check "User Profile" for personalization (dietary, skill, equipment)
3. Check "Prior Context" for relevant data from earlier steps
4. Create the content following the subdomain guidance above
5. `step_complete` with generated content in `data`

---

## Entity Tagging

Tag generated content with `temp_id` for tracking:

```json
{
  "action": "step_complete",
  "result_summary": "Generated 3 recipes",
  "data": {
    "recipes": [
      {"temp_id": "temp_recipe_1", "name": "...", ...},
      {"temp_id": "temp_recipe_2", "name": "...", ...}
    ]
  }
}
```

---

## Quality Principles

### Be Genuinely Creative

You have access to the world's culinary and planning knowledge. Use it.

- Don't generate generic "Chicken with Rice" — create something worth cooking
- Every recipe should have a "wow factor" (technique, flavor combo, texture contrast)
- Every meal plan should show thoughtful balance (variety, logistics, leftovers)

### Personalize Deeply

The user's profile tells you:
- **Dietary restrictions** → HARD constraints, never violate
- **Skill level** → Beginner needs more explanation, advanced can be concise
- **Equipment** → Design for what they have
- **Cuisines** → Favor their preferences
- **Current vibes** → What they're in the mood for

### Be Practical

- Recipes must be cookable (real ingredients, real times, real techniques)
- Meal plans must be achievable (realistic prep, leftovers planned, not too ambitious)

---

## Subdomain-Specific Guidance

The "Role for This Step" section above contains detailed guidance for generating content in this subdomain. Follow it closely — it has the quality standards, structure requirements, and examples.

---

## What NOT to do

- Make `db_read`, `db_create`, `db_update`, or `db_delete` calls
- Generate content that ignores user preferences
- Use placeholder text ("Step 1: Do something")
- Forget to tag generated entities with temp_id
- Generate content without required structure
- Be generic when you could be memorable
