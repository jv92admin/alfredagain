#!/usr/bin/env python3
"""
Test Phase 2 capabilities:
1. Recipe read auto-includes ingredients
2. Formatting groups ingredients by category
3. Instructions toggle (with vs without)
4. Ingredient matching on inventory/shopping writes
"""

import asyncio
import sys
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()


async def test_recipe_read_includes_ingredients():
    """Test that db_read for recipes auto-includes recipe_ingredients."""
    print("\n" + "="*60)
    print("TEST 1: Recipe read auto-includes ingredients")
    print("="*60)
    
    from alfred.tools.crud import db_read, DbReadParams
    
    # Read recipes without specifying columns
    params = DbReadParams(table="recipes", limit=2)
    
    # Need a user_id - get from a user who has recipes
    from supabase import create_client
    import os
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    # Find user with recipes
    recipes_check = sb.table("recipes").select("user_id").limit(1).execute()
    if not recipes_check.data:
        print("No recipes in DB")
        return False
    user_id = recipes_check.data[0]["user_id"]
    
    results = await db_read(params, user_id)
    
    print(f"Fetched {len(results)} recipes")
    
    if results:
        recipe = results[0]
        print(f"\nRecipe: {recipe.get('name')}")
        print(f"Has 'recipe_ingredients' key: {'recipe_ingredients' in recipe}")
        
        ingredients = recipe.get("recipe_ingredients", [])
        print(f"Ingredients count: {len(ingredients)}")
        
        if ingredients:
            print(f"Sample ingredient: {ingredients[0]}")
            has_category = any(ing.get("category") for ing in ingredients)
            print(f"Ingredients have category: {has_category}")
        
        return "recipe_ingredients" in recipe and len(ingredients) > 0
    
    return False


async def test_recipe_formatting():
    """Test that _format_recipe_record groups ingredients by category."""
    print("\n" + "="*60)
    print("TEST 2: Recipe formatting with grouped ingredients")
    print("="*60)
    
    from alfred_kitchen.domain.formatters import format_recipe_record as _format_recipe_record
    
    # Mock recipe record with nested ingredients
    mock_recipe = {
        "id": "recipe_1",
        "name": "Test Chicken Curry",
        "cuisine": "indian",
        "prep_time_minutes": 15,
        "cook_time_minutes": 30,
        "servings": 4,
        "difficulty": "beginner",
        "occasions": ["weeknight", "batch-prep"],
        "health_tags": ["high-protein"],
        "recipe_ingredients": [
            {"name": "chicken thigh", "category": "proteins"},
            {"name": "onion", "category": "vegetables"},
            {"name": "garlic", "category": "vegetables"},
            {"name": "ginger", "category": "vegetables"},
            {"name": "yogurt", "category": "dairy"},
            {"name": "garam masala", "category": "spices"},
            {"name": "turmeric", "category": "spices"},
            {"name": "cumin", "category": "spices"},
        ]
    }
    
    formatted = _format_recipe_record(mock_recipe, {})
    print("\nFormatted output:")
    print(formatted)
    
    # Check key elements
    checks = [
        "proteins:" in formatted,
        "vegetables:" in formatted,
        "dairy:" in formatted,
        "spices:" in formatted,
        "chicken thigh" in formatted,
    ]
    
    print(f"\nCategory grouping works: {all(checks)}")
    return all(checks)


async def test_instructions_toggle():
    """Test formatting with and without instructions."""
    print("\n" + "="*60)
    print("TEST 3: Instructions toggle")
    print("="*60)
    
    from alfred_kitchen.domain.formatters import format_recipe_record as _format_recipe_record
    
    # Without instructions
    recipe_summary = {
        "id": "recipe_2",
        "name": "Quick Stir Fry",
        "cuisine": "thai",
        "servings": 2,
        "recipe_ingredients": [
            {"name": "tofu", "category": "proteins"},
        ]
    }
    
    # With instructions
    recipe_full = {
        **recipe_summary,
        "instructions": [
            "Press tofu to remove moisture",
            "Heat wok over high heat",
            "Stir fry tofu until golden",
        ]
    }
    
    fmt_summary = _format_recipe_record(recipe_summary, {})
    fmt_full = _format_recipe_record(recipe_full, {})
    
    print("\nSummary (no instructions):")
    print(fmt_summary)
    print("\nFull (with instructions):")
    print(fmt_full)
    
    has_instructions_marker = "[instructions:" in fmt_full
    no_instructions_in_summary = "[instructions:" not in fmt_summary
    
    print(f"\nSummary excludes instructions: {no_instructions_in_summary}")
    print(f"Full shows instructions marker: {has_instructions_marker}")
    
    return has_instructions_marker and no_instructions_in_summary


async def test_inventory_ingredient_linking():
    """Test that adding to inventory auto-links ingredient_id and category."""
    print("\n" + "="*60)
    print("TEST 4: Inventory ingredient linking")
    print("="*60)
    
    from alfred.tools.crud import db_create, db_delete, DbCreateParams, DbDeleteParams
    
    # Get user_id
    from supabase import create_client
    import os
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    users = sb.table("users").select("id").limit(1).execute()
    user_id = users.data[0]["id"]
    
    # Create inventory item with natural name
    test_item = {
        "name": "fresh basil leaves",
        "quantity": 1,
        "unit": "bunch",
        "location": "fridge",
    }
    
    params = DbCreateParams(table="inventory", data=test_item)
    result = await db_create(params, user_id)
    
    print(f"\nCreated: {result.get('name')}")
    print(f"ingredient_id: {result.get('ingredient_id')}")
    print(f"category: {result.get('category')}")
    
    # Check linking worked
    has_ingredient_id = result.get("ingredient_id") is not None
    has_category = result.get("category") is not None
    
    print(f"\nAuto-linked ingredient_id: {has_ingredient_id}")
    print(f"Auto-populated category: {has_category}")
    
    # Cleanup - delete the test item
    if result.get("id"):
        delete_params = DbDeleteParams(
            table="inventory",
            filters=[{"field": "id", "op": "=", "value": result["id"]}]
        )
        await db_delete(delete_params, user_id)
        print("Cleaned up test item")
    
    return has_ingredient_id and has_category


async def test_recipe_ingredient_creation():
    """Test that recipe ingredients get proper linking."""
    print("\n" + "="*60)
    print("TEST 5: Recipe ingredient creation & linking")
    print("="*60)
    
    from alfred.tools.crud import db_create, db_delete, DbCreateParams, DbDeleteParams
    
    # Get user_id and a recipe_id
    from supabase import create_client
    import os
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    users = sb.table("users").select("id").limit(1).execute()
    user_id = users.data[0]["id"]
    
    recipes = sb.table("recipes").select("id").eq("user_id", user_id).limit(1).execute()
    if not recipes.data:
        print("No recipes found, skipping test")
        return True
    recipe_id = recipes.data[0]["id"]
    
    # Create recipe ingredient with canonical name
    test_ingredient = {
        "recipe_id": recipe_id,
        "name": "garlic",  # canonical name
        "quantity": 3,
        "unit": "cloves",
        "notes": "minced",  # qualifier in notes
    }
    
    params = DbCreateParams(table="recipe_ingredients", data=test_ingredient)
    result = await db_create(params, user_id)
    
    print(f"\nCreated: {result.get('name')}")
    print(f"ingredient_id: {result.get('ingredient_id')}")
    print(f"category: {result.get('category')}")
    
    has_ingredient_id = result.get("ingredient_id") is not None
    has_category = result.get("category") is not None
    
    print(f"\nAuto-linked ingredient_id: {has_ingredient_id}")
    print(f"Auto-populated category: {has_category}")
    
    # Cleanup
    if result.get("id"):
        delete_params = DbDeleteParams(
            table="recipe_ingredients",
            filters=[{"field": "id", "op": "=", "value": result["id"]}]
        )
        await db_delete(delete_params, user_id)
        print("Cleaned up test ingredient")
    
    return has_ingredient_id


async def main():
    print("="*60)
    print("PHASE 2 CAPABILITY TESTS")
    print("="*60)
    
    results = {}
    
    results["recipe_read_ingredients"] = await test_recipe_read_includes_ingredients()
    results["recipe_formatting"] = await test_recipe_formatting()
    results["instructions_toggle"] = await test_instructions_toggle()
    results["inventory_linking"] = await test_inventory_ingredient_linking()
    results["recipe_ingredient_linking"] = await test_recipe_ingredient_creation()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_passed = True
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed"))
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
