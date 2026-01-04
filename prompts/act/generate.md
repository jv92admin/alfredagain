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

## Recipe Generation Standards

You have access to the world's culinary knowledge. Generate recipes that would pass muster in a food magazine, not generic AI filler.

### What Makes a Good Recipe

**Instructions must teach, not just list:**

❌ BAD:
```
1. Cook the onions
2. Add spices
3. Add chickpeas
4. Serve
```

✅ GOOD:
```
1. Heat oil in a large skillet over medium-high heat until shimmering
2. Add onions and cook, stirring occasionally, until softened and golden at edges, 6-8 minutes
3. Add garlic and ginger, stir until fragrant, about 30 seconds
4. Add garam masala, cumin, and turmeric. Stir to coat onions and bloom spices, 1 minute
5. Add diced tomatoes with juices. Simmer until slightly thickened, 5 minutes
6. Add drained chickpeas and coconut milk. Simmer until flavors meld and sauce coats chickpeas, 10-12 minutes
7. Season with salt to taste. Garnish with fresh cilantro and serve over basmati rice
```

### Skill-Level Adaptation

| Skill | Instruction Detail | Complexity | Ingredients |
|-------|-------------------|------------|-------------|
| Beginner | Explain techniques ("sauté = cook in oil over medium heat") | Simple methods | 8-12 max |
| Intermediate | Assume basic skills, focus on timing/cues | Moderate | 10-15 |
| Advanced | Can be concise, complex techniques okay | Any | No limit |

### Required Recipe Fields

```json
{
  "temp_id": "temp_recipe_1",
  "name": "Crispy Chickpea Tikka Masala",
  "description": "Creamy tomato-based curry with crispy roasted chickpeas and warm spices",
  "prep_time": "15 min",
  "cook_time": "35 min",
  "servings": 4,
  "cuisine": "Indian",
  "difficulty": "intermediate",
  "ingredients": [
    {"name": "chickpeas", "quantity": 2, "unit": "cans", "notes": "drained and patted dry"},
    {"name": "olive oil", "quantity": 3, "unit": "tbsp"},
    {"name": "onion", "quantity": 1, "unit": "large", "notes": "diced"},
    ...
  ],
  "instructions": [
    "Preheat oven to 425°F. Toss chickpeas with 1 tbsp oil and 1 tsp garam masala. Roast 25 minutes until crispy.",
    "Meanwhile, heat remaining oil in a large pan over medium heat...",
    ...
  ],
  "tags": ["weeknight", "vegetarian", "batch-prep"]
}
```

## Ingredient Naming (for recipes)

Use **grocery-store names**, not recipe component names:
- ✅ GOOD: "chickpeas", "fresh basil", "dried oregano", "diced tomatoes"
- ❌ BAD: "crispy roasted chickpeas", "herby greens mix", "honey-mustard walnut crunch"

Keep meaningful descriptors (fresh vs dried, diced vs whole). Put in-recipe prep in `notes`:
```json
{"name": "chickpeas", "quantity": 1, "unit": "can", "notes": "drained, roasted with herbs"}
```

---

## What NOT to do

- Make `db_read`, `db_create`, `db_update`, or `db_delete` calls
- Generate content that ignores user preferences
- Use placeholder text ("Step 1: Do something")
- Forget to tag generated entities with temp_id
- Generate content without structure (missing fields)
