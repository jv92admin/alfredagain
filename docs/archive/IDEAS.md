# Alfred V2 - Future Ideas & Roadmap

> Ideas preserved from v1 planning that remain relevant for the rebuild.

---

## High Priority (Consider for v2)

### 1. Notifications / Reminders Vault

**Source:** `notifications_vault_plan.md`

Let Alfred remember temporary instructions and prompt users on due dates:

> "Only cardio for the next month because of a knee injury."

On the due date, Alfred prompts: "Your cardio-only plan ends today. Resume full workouts, extend 2 weeks, or snooze?"

**Why it matters:** Enables proactive time-based suggestions without external cron jobs. Fits naturally with the proactive suggestions system.

**Implementation hint:** Simple `notifications` table with `due_date`, `status`, `proposed_actions`. Check on session start.

---

### 2. Preference Learning from Usage History

**Source:** `Business_Features_Implementation_Plan.md`

Automatically adjust `flavor_preferences` based on behavior:

| Trigger | Delta | Confirmation |
|---------|-------|--------------|
| Ingredient purchased/added | +0.1 | Silent |
| Ingredient used in meal plan | +0.2 | Silent |
| Ingredient wasted/removed unused | -0.1 | Ask if score goes negative |
| User explicit dislike | Set to -1.0 | Immediate |

**Why it matters:** Alfred gets smarter over time without explicit preference setting.

**Implementation hint:** Postgres trigger on inventory mutations that updates `flavor_preferences` table.

---

### 3. Prep Checklist Generation

**Source:** `alfred_pantry_extensions.md`

Generate daily prep checklists from meal plans:

```
Monday Prep List:
□ 9:00 AM - Start marinating chicken (for dinner)
□ 5:00 PM - Dice onions (10 min)
□ 5:15 PM - Start rice (for stir fry)
□ 5:30 PM - Cook stir fry (20 min)
```

**Why it matters:** Bridges the gap from "plan" to "action" - makes meal plans actually usable.

**Implementation hint:** Generate from meal_plan + recipe.instructions. Include timing hints for marinating, defrosting.

---

### 4. Recipe Variants System

**Source:** `future_improvements.md`, `alfred_pantry_extensions.md`

Instead of duplicating recipes, use variant overlays:

```python
base_recipe = "chicken_stir_fry"
variants = {
    "asian_style": {"add": {"soy_sauce": "2 tbsp"}},
    "spicy": {"add": {"red_pepper_flakes": "1 tsp"}},
    "low_sodium": {"remove": ["soy_sauce"], "add": {"coconut_aminos": "2 tbsp"}}
}
```

**Why it matters:** Reduces recipe catalog bloat, enables on-the-fly customization.

**Implementation hint:** Store variants in recipe JSONB. Resolve at query time.

---

### 5. Flavor-Driven Auto-Substitutions

**Source:** `future_improvements.md`

When ingredients are missing, suggest substitutes based on flavor compounds:

```
Missing: soy sauce
In stock: tamari, coconut aminos
Suggestion: "Tamari is a perfect substitute (same umami profile)"
```

**Why it matters:** Reduces friction, leverages seeded FlavorDB data.

**Implementation hint:** Use flavor_compounds array on ingredients table. Match compounds for substitution candidates.

---

## Medium Priority (Phase 2+)

### 6. Unit Conversion with Density Tables

Convert between volume and weight units using ingredient density:

```python
convert_units(qty=1, from_unit="cup", to_unit="g", ingredient="flour")
# Returns: 125g (based on flour density)
```

**Why it matters:** Accurate shopping list aggregation, nutrition calculations.

**Data needed:** Density table for ~50 common ingredients.

---

### 7. Cross-Agent Memory Sharing

Coach agent knows what Pantry agent learned:

- "You mentioned you're training for a marathon" (Coach context)
- → Affects Pantry: "High-carb meals recommended for your training"

**Why it matters:** True cross-domain intelligence (critical feature).

**Implementation hint:** Shared `conversation_memory` table with agent tags. All agents can read, only relevant agent writes.

---

### 8. Batch Cooking Coordination

Optimize prep across multiple meals:

> "You're making both pasta sauce and pizza this week. Make a double batch of tomato base on Sunday."

**Why it matters:** Real efficiency gains for users who meal prep.

**Implementation hint:** Analyze meal_plan for shared ingredients/steps across the week.

---

## Lower Priority (Future)

### 9. Budget-Aware Meal Planning

Consider ingredient costs when planning:

> "Here's a week of meals under $75"

**Data needed:** Price data (manual entry or API integration).

---

### 10. Nutritional Goal Tracking

Track macros across meal plans:

> "Your meal plan averages 2,100 kcal/day with 140g protein"

**Why it matters:** Health-conscious users want this.

**Implementation hint:** Use nutrition_per_100g from seeded ingredient data.

---

### 11. Social/Family Meal Planning

Coordinate meals for multiple household members:

> "Alex is vegetarian on Tuesdays. Here's a plan that works for everyone."

**Implementation hint:** Multiple preference profiles, constraint satisfaction.

---

## Ideas Explicitly NOT Carrying Forward

| Idea | Why Not |
|------|---------|
| Named/declarative queries | v2 uses SQL - this was a workaround for JSON limitations |
| Task code construction rules | Replaced with natural language intent |
| Complex step dependencies | LangGraph handles natively |
| Custom conversation summarizer | OpenAI Responses API handles this |
| Confidence-tracked values (CTV) | Over-engineered for v1's JSON limitations |

---

## Contributing Ideas

As we build v2, new ideas should be added here with:
1. **Clear problem statement** - What user pain does this solve?
2. **Implementation hint** - How might we build it?
3. **Priority assessment** - Does it align with core magic (memory, cross-domain, proactive, natural)?


