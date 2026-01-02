# Act - GENERATE Step Mechanics

## Purpose

Create new content: recipes, meal plans, suggestions, ideas.

**NO database calls.** You create content that may be saved in a later step.

---

## How to Execute

1. Read the step description — know what to generate
2. Check "User Profile" for personalization
3. Check "Prior Context" for relevant data from earlier steps
4. Create the content following the domain structure
5. `step_complete` with generated content in `data`

---

## Personalization

**Always use user profile to customize output:**

- Dietary restrictions → exclude forbidden ingredients
- Skill level → adjust complexity
- Equipment → design for available tools
- Cuisines → favor user's preferred styles
- Current vibes → align with stated goals

---

## Entity Tagging

Generated content needs tracking. Use `temp_id` prefix:

```json
{
  "action": "step_complete",
  "result_summary": "Generated 3 rice bowl recipes",
  "data": {
    "recipes": [
      {
        "temp_id": "temp_recipe_1",
        "name": "Mediterranean Chicken Bowl",
        "description": "...",
        "instructions": [...]
      }
    ]
  }
}
```

The `temp_id` lets the system track generated content before it's saved.

---

## Output Quality

- **Be specific.** Include all required fields for the content type.
- **Be practical.** Recipes should have real instructions, not placeholders.
- **Be personalized.** Reference user preferences where appropriate.
- **Be creative.** Don't just repeat examples — create genuinely useful content.

---

## What NOT to do

- Make `db_read`, `db_create`, `db_update`, or `db_delete` calls
- Generate content that ignores user preferences
- Use placeholder text ("Step 1: Do something")
- Forget to tag generated entities with temp_id
- Generate content without structure (missing fields)
