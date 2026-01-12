"""
Alfred V3 - Contextual Examples for Act Steps.

Provides step-type-specific examples and guidance based on:
- Subdomain (recipes, inventory, etc.)
- Step description (verbs like "add", "find", "compare")
- Previous subdomain (cross-domain patterns)
- Step type (read, write, analyze, generate)

Moved from schema.py for cleaner separation of concerns.
"""


def get_contextual_examples(
    subdomain: str, 
    step_description: str, 
    prev_subdomain: str | None = None,
    step_type: str = "read"
) -> str:
    """
    Get contextual examples based on step verb and cross-domain patterns.
    
    Args:
        subdomain: Current step's subdomain
        step_description: Natural language step description
        prev_subdomain: Previous step's subdomain (for cross-domain patterns)
        step_type: "read", "write", "analyze", or "generate"
    
    Returns:
        1-2 relevant examples as markdown
    """
    desc_lower = step_description.lower()
    examples = []
    
    # === ANALYZE STEP GUIDANCE ===
    if step_type == "analyze":
        return _get_analyze_guidance(subdomain, desc_lower, prev_subdomain)
    
    # === GENERATE STEP GUIDANCE ===
    if step_type == "generate":
        return _get_generate_guidance(subdomain, desc_lower)
    
    # === SHOPPING PATTERNS ===
    if subdomain == "shopping":
        # Smart shopping pattern (check before adding)
        if any(verb in desc_lower for verb in ["add", "create", "save", "insert"]):
            examples.append("""**Smart Add Pattern** (check existing first):
1. `db_read` shopping_list to check what's already there
2. In analyze step or your reasoning: merge duplicates, consolidate quantities
3. `db_create` only NEW items, `db_update` existing quantities if needed

**Ingredient Naming:** Keep meaningful descriptors, skip unnecessary ones:
- ✅ "diced tomatoes", "fresh basil", "dried oregano" (these are different products)
- ❌ "organic hand-picked roma tomatoes", "artisanal basil" (marketing fluff)""")
        
        # Cross-domain: from recipes
        if prev_subdomain == "recipes":
            examples.append("""**Recipe → Shopping Pattern**:
Previous step read recipe ingredients. Use those IDs/names to add to shopping list.
Keep meaningful descriptors (fresh vs dried, diced vs whole), skip prep instructions (e.g., "finely chopped onion" → "onion").""")
        
        # Cross-domain: from meal_plan
        if prev_subdomain == "meal_plans":
            examples.append("""**Meal Plan → Shopping Pattern**:
Previous step read meal plan. Read recipes for those recipe_ids (ingredients auto-included), then add missing items to shopping.""")
    
    # === RECIPE PATTERNS ===
    elif subdomain == "recipes":
        # Linked table create
        if any(verb in desc_lower for verb in ["create", "save", "add"]):
            examples.append("""**Create Recipe Pattern** (linked tables):
1. `db_create` on `recipes` → get the new `id` from response
2. `db_create` on `recipe_ingredients` with that `recipe_id`
3. `step_complete` only after BOTH are done""")
        
        # Linked table update
        if any(verb in desc_lower for verb in ["update", "modify", "change", "edit"]):
            examples.append("""**Update Recipe Pattern:**
- **Metadata only** (name, tags, description): Just `db_update` on recipes
- **Replace ingredients**: 
  1. `db_delete` on `recipe_ingredients` WHERE recipe_id = X
  2. `db_create` new ingredients with same recipe_id
- **Add ingredient**: Just `db_create` on recipe_ingredients""")
        
        # Linked table delete - CASCADE!
        if any(verb in desc_lower for verb in ["delete", "remove", "clear"]):
            examples.append("""**Delete Recipe:** Just delete from `recipes` — `recipe_ingredients` CASCADE automatically.
`{"tool": "db_delete", "params": {"table": "recipes", "filters": [{"field": "id", "op": "=", "value": "<uuid>"}]}}`""")
        
        # Search
        if any(verb in desc_lower for verb in ["find", "search", "look"]):
            examples.append("""**Recipe Search** (use OR for keywords):
```json
{"tool": "db_read", "params": {"table": "recipes", "or_filters": [
  {"field": "name", "op": "ilike", "value": "%chicken%"},
  {"field": "name", "op": "ilike", "value": "%curry%"}
], "limit": 10}}
```""")
    
    # === MEAL PLAN PATTERNS ===
    elif subdomain == "meal_plans":
        if any(verb in desc_lower for verb in ["create", "add", "save", "plan"]):
            examples.append("""**Add to Meal Plan**:
```json
{"tool": "db_create", "params": {"table": "meal_plans", "data": {
  "date": "2025-01-02", "meal_type": "dinner", "recipe_id": "<uuid>", "servings": 2
}}}
```
If recipe doesn't exist, suggest creating it first.""")
    
    # === INVENTORY PATTERNS ===
    elif subdomain == "inventory":
        if any(verb in desc_lower for verb in ["add", "create"]):
            examples.append("""**Add to Inventory**:
```json
{"tool": "db_create", "params": {"table": "inventory", "data": {
  "name": "eggs", "quantity": 12, "unit": "count", "location": "fridge"
}}}
```

**Ingredient Naming:** Use grocery names, keep meaningful descriptors:
- ✅ "chicken thighs", "extra virgin olive oil", "fresh mozzarella", "dried oregano"
- ❌ "organic free-range local farm chicken", "artisanal hand-pressed olive oil"
Put brand names in `notes` if needed.""")
    
    # === TASKS PATTERNS ===
    elif subdomain == "tasks":
        if any(verb in desc_lower for verb in ["create", "add", "remind"]):
            examples.append("""**Create Task** (link to meal plan if applicable):
```json
{"tool": "db_create", "params": {"table": "tasks", "data": {
  "title": "Thaw chicken", "due_date": "2025-01-02", "category": "prep",
  "meal_plan_id": "<uuid>"
}}}
```
Prefer meal_plan_id over recipe_id when possible.""")
    
    if not examples:
        return ""
    
    return "## Patterns for This Step\n\n" + "\n\n".join(examples)


def _get_analyze_guidance(subdomain: str, desc_lower: str, prev_subdomain: str | None) -> str:
    """Get guidance for analyze steps based on subdomain and context."""
    
    guidance_parts = ["## Analysis Guidance\n"]
    
    # === RECIPES ANALYZE ===
    if subdomain == "recipes":
        if "preference" in desc_lower or "fit" in desc_lower or "match" in desc_lower or "enough" in desc_lower:
            guidance_parts.append("""**Matching Recipes to Preferences:**
- Check dietary_restrictions and allergies — these are HARD constraints (must exclude)
- Check available_equipment — only suggest recipes using equipment they have
- Check favorite_cuisines — prefer recipes in these cuisines
- Check current_vibes — align with their current interests
- If not enough recipes match: Note this and suggest generating new ones""")
        
        if "compare" in desc_lower or "duplicate" in desc_lower:
            guidance_parts.append("""**Comparing Recipes:**
- Check for similar names (case-insensitive, partial matches)
- Check for overlapping ingredients (>70% = likely duplicate)
- Note any variations (spicy version, instant-pot version)""")
    
    # === SHOPPING ANALYZE ===
    elif subdomain == "shopping":
        if "inventory" in desc_lower or "exist" in desc_lower or "have" in desc_lower or "missing" in desc_lower:
            guidance_parts.append("""**Comparing Shopping to Inventory:**
- Match by normalized name (case-insensitive, strip preparation terms)
- "diced tomatoes" in shopping = "tomatoes" in inventory (match!)
- Items in BOTH lists = already have, can remove from shopping
- Report which items are truly missing""")
        
        if "recipe" in desc_lower or "ingredient" in desc_lower:
            guidance_parts.append("""**Recipe Ingredients to Shopping:**
- Extract ingredient names from recipe_ingredients
- Normalize names before adding
- Check against current shopping list to avoid duplicates
- Note quantities needed vs quantities on list""")
    
    # === MEAL PLAN ANALYZE ===
    elif subdomain == "meal_plans":
        if "prep" in desc_lower or "task" in desc_lower:
            guidance_parts.append("""**Identifying Prep Work:**
- Check which recipes need advance prep (marinating, thawing, soaking)
- Identify batch cooking opportunities (cook once, use multiple days)
- Note shopping needs that should happen before prep
- Suggest task due_dates based on meal dates""")
        
        if "balance" in desc_lower or "variety" in desc_lower:
            guidance_parts.append("""**Checking Meal Plan Balance:**
- Look for cuisine variety across the week
- Check protein variety (not chicken every day)
- Note any gaps in nutrition or meal types
- Verify recipes exist for all meal entries""")
    
    # === INVENTORY ANALYZE ===
    elif subdomain == "inventory":
        if "expir" in desc_lower or "soon" in desc_lower:
            guidance_parts.append("""**Finding Expiring Items:**
- Sort by expiry_date, nearest first
- Flag items expiring in <3 days as URGENT
- Suggest recipes that could use these items
- Note quantity available""")
        
        if "low" in desc_lower or "running out" in desc_lower or "stock" in desc_lower:
            guidance_parts.append("""**Finding Low Stock:**
- Check quantity against typical usage
- Flag staples (eggs, milk, butter) when low
- Suggest adding to shopping list""")
    
    # === GENERIC CROSS-DOMAIN ===
    if prev_subdomain:
        guidance_parts.append(f"""**Cross-Domain Context:**
Previous step was in `{prev_subdomain}`. Use that data to inform this analysis.
- Do NOT re-query — analyze what was already fetched
- Reference specific IDs/names from previous results""")
    
    # === CRITICAL WARNING ===
    guidance_parts.append("""
**CRITICAL:**
- Only analyze data that EXISTS in Previous Step Results
- If previous results are empty `[]`, report "No data to analyze"
- Do NOT invent or hallucinate data that wasn't returned""")
    
    return "\n\n".join(guidance_parts)


def _get_generate_guidance(subdomain: str, desc_lower: str) -> str:
    """Get guidance for generate steps based on subdomain."""
    
    guidance_parts = ["## Generation Guidance\n"]
    
    # === RECIPE GENERATION ===
    if subdomain == "recipes":
        guidance_parts.append("""**Recipe Generation:**
- Create a complete, executable recipe
- Include: name, description, prep_time, cook_time, servings
- Include: numbered instructions
- Match user's skill level and available equipment
- Honor ALL dietary restrictions (hard constraints)
- Align with favorite cuisines and current vibes

**Ingredient Naming (IMPORTANT):**
- Use grocery-store names, not recipe component names
- Keep meaningful descriptors: "fresh basil", "dried oregano", "diced tomatoes" (different products)
- Put in-recipe prep in `notes`: name="chickpeas", notes="drained and roasted"
- ❌ BAD: "Herby greens mix", "Honey-mustard walnut crunch", "Crispy roasted chickpeas with herbs"
- ✅ GOOD: "mixed greens", "walnuts", "honey", "mustard", "chickpeas" (separate buyable items)""")
        
        if "variation" in desc_lower or "spicy" in desc_lower or "version" in desc_lower:
            guidance_parts.append("""**Creating Variations:**
- Keep the spirit of the original
- Note what changed and why
- Set parent_recipe_id when saving""")
        
        if "quick" in desc_lower or "fast" in desc_lower or "easy" in desc_lower:
            guidance_parts.append("""**Quick Recipe Constraints:**
- Total time (prep + cook) under 30 minutes
- Simple techniques, minimal steps
- Common ingredients likely in pantry""")
    
    # === MEAL PLAN GENERATION ===
    elif subdomain == "meal_plans":
        guidance_parts.append("""**Meal Plan Generation:**
- Use user's planning_rhythm (e.g., "weekends only" = they cook on weekends)
- Match household_size for servings
- Balance cuisines across the week
- Consider what recipes exist vs need creating
- Assign dates based on their cooking days, not eating days""")
        
        if "week" in desc_lower:
            guidance_parts.append("""**Weekly Plan:**
- Cover the requested date range
- Leave gaps on non-cooking days (they may eat leftovers)
- Batch cooking days can produce meals for multiple days""")
    
    # === TASK GENERATION ===
    elif subdomain == "tasks":
        guidance_parts.append("""**Task Generation:**
- Create actionable, specific tasks
- Set appropriate due_dates relative to meal dates
- Use categories: prep, shopping, cleanup, other
- Link to meal_plan_id when possible""")
    
    # === SHOPPING LIST GENERATION ===
    elif subdomain == "shopping":
        guidance_parts.append("""**Shopping List Generation:**
- Aggregate ingredients from all planned meals
- Deduplicate and consolidate quantities
- Organize by category (produce, dairy, meat, etc.)
- Note what's already in inventory""")
    
    return "\n\n".join(guidance_parts)

