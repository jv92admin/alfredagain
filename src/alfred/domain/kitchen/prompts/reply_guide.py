"""
Kitchen-specific Reply subdomain formatting guide.

Extracted from the original reply.md <subdomains> section.
Injected into the Reply prompt via DomainConfig.get_reply_subdomain_guide().
"""

REPLY_SUBDOMAIN_GUIDE = """\
<subdomains>
## How to Present Each Domain

Use user language: "pantry" not "inventory", "fridge" not "refrigerator location".

---

### Inventory (Pantry/Fridge/Freezer)

**Key fields:** name, quantity, location, expiry_date

**Format:** Group by location, show quantities and expiry when relevant.

```
**Fridge:**
- Milk (2 cartons)
- Eggs (12 count)
- Chicken breast (2 lb, expires Jan 15)

**Pantry:**
- Rice (2 bags)
- Olive oil (1 bottle)
```

**Detail level:**
- Summary: name + quantity
- Full: include expiry, notes

---

### Shopping List

**Key fields:** item_name, quantity, category, is_purchased

**Format:** Group by category if available.

```
**Produce:**
- Onions (3)
- Garlic (1 head)

**Protein:**
- Chicken breast (2 lb)
```

**Detail level:**
- Usually full list is shown
- For confirmations: just count ("Added 5 items")

---

### Recipes

**Key fields:** name, cuisine, servings, prep_time, cook_time, ingredients, instructions

**Format:** Magazine-style when showing full recipe.

```
**Mediterranean Chickpea Bowl**
*Prep: 15 min | Cook: 20 min | Serves: 4*

**Ingredients:**
- 2 cans chickpeas, drained
- 1 cup rice
- 2 cups vegetable broth
...

**Instructions:**
1. Cook rice in broth until fluffy (18 min).
2. Roast chickpeas with cumin at 400°F (25 min).
3. Assemble bowls.
```

**Detail level:**
- Summary: name, cuisine, servings (for browsing/selecting)
- Full: include ingredients + instructions (for cooking/reviewing)

**Generated vs Saved:**
- `gen_recipe_1` → show in full, offer to save
- `recipe_3` → already saved, DON'T offer to save again

---

### Meal Plans

**Key fields:** date, meal_type (lunch/dinner), recipe_id, notes

**Format:** Simple calendar view — one day at a time, in date order.

```
**Tuesday, Jan 14**
- Lunch: Open (takeout or pantry meal)
- Dinner: Air Fryer Chicken Tikka (cook fresh, serves 4)

**Wednesday, Jan 15**
- Lunch: Leftover Chicken Tikka
- Dinner: Open
```

**Detail level:**
- Always show by date, chronologically
- DON'T reorganize by "cooking days"

---

### Tasks

**Key fields:** description, due_date, is_completed

**Format:** Simple list with dates.

```
- [ ] Thaw chicken (due: Jan 14)
- [ ] Prep vegetables for stir fry (due: Jan 15)
- [x] Buy groceries (completed)
```

---

### Preferences

**Key fields:** diet restrictions, allergies, equipment, skill level, cooking rhythm

**Format:** Acknowledge when relevant, don't recite back.

- "Since you have an air fryer, here's a recipe that uses it..."
- NOT: "Your preferences show: air-fryer, beginner skill, no shellfish..."

</subdomains>"""
