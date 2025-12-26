#!/usr/bin/env python3
"""
Seed the ingredients table from Open Food Facts API.

This script fetches common food ingredients and seeds them into the database
with categories and aliases for better matching.

Usage:
    python scripts/seed_ingredients.py [--limit 100] [--dry-run]
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

# Try to import from alfred, fallback to direct supabase if not in venv
try:
    from alfred.db.client import get_client
except ImportError:
    import os
    from supabase import create_client, Client
    
    def get_client() -> Client:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        return create_client(url, key)


# Category mapping from Open Food Facts categories to our simplified categories
CATEGORY_MAP = {
    # Produce
    "fruits": "produce",
    "vegetables": "produce",
    "fresh-vegetables": "produce",
    "fresh-fruits": "produce",
    "herbs": "produce",
    "legumes": "produce",
    "salads": "produce",
    
    # Dairy
    "dairy": "dairy",
    "milk": "dairy",
    "cheeses": "dairy",
    "yogurts": "dairy",
    "butter": "dairy",
    "eggs": "dairy",
    "cream": "dairy",
    
    # Proteins
    "meats": "protein",
    "poultry": "protein",
    "beef": "protein",
    "pork": "protein",
    "lamb": "protein",
    "fish": "protein",
    "seafood": "protein",
    "shellfish": "protein",
    "tofu": "protein",
    
    # Grains
    "cereals": "grains",
    "breads": "grains",
    "pastas": "grains",
    "rice": "grains",
    "flour": "grains",
    "noodles": "grains",
    
    # Pantry
    "oils": "pantry",
    "sauces": "pantry",
    "condiments": "pantry",
    "canned-foods": "pantry",
    "dried-products": "pantry",
    "nuts": "pantry",
    "seeds": "pantry",
    "sweeteners": "pantry",
    "sugars": "pantry",
    "honey": "pantry",
    
    # Spices
    "spices": "spices",
    "seasonings": "spices",
    "herbs-and-spices": "spices",
    
    # Beverages (exclude from ingredients)
    "beverages": None,
    "sodas": None,
    "alcoholic-beverages": None,
}


# Common ingredients with aliases (for when API data is insufficient)
CORE_INGREDIENTS = [
    # Produce
    {"name": "onion", "category": "produce", "aliases": ["onions", "yellow onion", "white onion"]},
    {"name": "garlic", "category": "produce", "aliases": ["garlic cloves", "fresh garlic"]},
    {"name": "tomato", "category": "produce", "aliases": ["tomatoes", "roma tomato", "cherry tomatoes"]},
    {"name": "potato", "category": "produce", "aliases": ["potatoes", "russet potato", "yukon gold"]},
    {"name": "carrot", "category": "produce", "aliases": ["carrots"]},
    {"name": "celery", "category": "produce", "aliases": ["celery stalks", "celery ribs"]},
    {"name": "bell pepper", "category": "produce", "aliases": ["bell peppers", "capsicum", "sweet pepper"]},
    {"name": "broccoli", "category": "produce", "aliases": ["broccoli florets"]},
    {"name": "spinach", "category": "produce", "aliases": ["baby spinach", "fresh spinach"]},
    {"name": "lettuce", "category": "produce", "aliases": ["romaine", "iceberg lettuce"]},
    {"name": "cucumber", "category": "produce", "aliases": ["cucumbers", "english cucumber"]},
    {"name": "mushroom", "category": "produce", "aliases": ["mushrooms", "cremini", "button mushrooms"]},
    {"name": "lemon", "category": "produce", "aliases": ["lemons", "lemon juice", "fresh lemon"]},
    {"name": "lime", "category": "produce", "aliases": ["limes", "lime juice"]},
    {"name": "avocado", "category": "produce", "aliases": ["avocados"]},
    {"name": "ginger", "category": "produce", "aliases": ["fresh ginger", "ginger root"]},
    {"name": "green onion", "category": "produce", "aliases": ["scallions", "spring onions"]},
    {"name": "cilantro", "category": "produce", "aliases": ["coriander", "fresh cilantro"]},
    {"name": "parsley", "category": "produce", "aliases": ["fresh parsley", "italian parsley"]},
    {"name": "basil", "category": "produce", "aliases": ["fresh basil", "sweet basil"]},
    
    # Dairy
    {"name": "butter", "category": "dairy", "aliases": ["unsalted butter", "salted butter"]},
    {"name": "milk", "category": "dairy", "aliases": ["whole milk", "2% milk", "skim milk"]},
    {"name": "eggs", "category": "dairy", "aliases": ["large eggs", "egg", "whole eggs"]},
    {"name": "cheese", "category": "dairy", "aliases": ["shredded cheese", "cheddar", "mozzarella"]},
    {"name": "cream", "category": "dairy", "aliases": ["heavy cream", "whipping cream", "half-and-half"]},
    {"name": "sour cream", "category": "dairy", "aliases": []},
    {"name": "yogurt", "category": "dairy", "aliases": ["greek yogurt", "plain yogurt"]},
    {"name": "parmesan", "category": "dairy", "aliases": ["parmesan cheese", "parmigiano reggiano"]},
    {"name": "feta", "category": "dairy", "aliases": ["feta cheese", "crumbled feta"]},
    
    # Proteins
    {"name": "chicken breast", "category": "protein", "aliases": ["chicken breasts", "boneless chicken"]},
    {"name": "chicken thighs", "category": "protein", "aliases": ["bone-in thighs", "boneless thighs"]},
    {"name": "ground beef", "category": "protein", "aliases": ["beef mince", "hamburger meat"]},
    {"name": "beef steak", "category": "protein", "aliases": ["steak", "sirloin", "ribeye"]},
    {"name": "pork chops", "category": "protein", "aliases": ["pork loin chops"]},
    {"name": "bacon", "category": "protein", "aliases": ["bacon strips", "streaky bacon"]},
    {"name": "salmon", "category": "protein", "aliases": ["salmon fillet", "fresh salmon"]},
    {"name": "shrimp", "category": "protein", "aliases": ["prawns", "jumbo shrimp"]},
    {"name": "tofu", "category": "protein", "aliases": ["firm tofu", "silken tofu", "bean curd"]},
    {"name": "ground turkey", "category": "protein", "aliases": ["turkey mince"]},
    
    # Grains
    {"name": "rice", "category": "grains", "aliases": ["white rice", "basmati rice", "jasmine rice", "brown rice"]},
    {"name": "pasta", "category": "grains", "aliases": ["spaghetti", "penne", "linguine", "fettuccine"]},
    {"name": "bread", "category": "grains", "aliases": ["sliced bread", "loaf", "sandwich bread"]},
    {"name": "flour", "category": "grains", "aliases": ["all-purpose flour", "plain flour", "wheat flour"]},
    {"name": "oats", "category": "grains", "aliases": ["rolled oats", "oatmeal", "old-fashioned oats"]},
    {"name": "quinoa", "category": "grains", "aliases": []},
    {"name": "breadcrumbs", "category": "grains", "aliases": ["panko", "bread crumbs"]},
    
    # Pantry
    {"name": "olive oil", "category": "pantry", "aliases": ["extra virgin olive oil", "evoo"]},
    {"name": "vegetable oil", "category": "pantry", "aliases": ["cooking oil", "canola oil"]},
    {"name": "soy sauce", "category": "pantry", "aliases": ["shoyu", "tamari"]},
    {"name": "vinegar", "category": "pantry", "aliases": ["white vinegar", "apple cider vinegar", "rice vinegar"]},
    {"name": "honey", "category": "pantry", "aliases": ["raw honey"]},
    {"name": "sugar", "category": "pantry", "aliases": ["white sugar", "granulated sugar", "cane sugar"]},
    {"name": "brown sugar", "category": "pantry", "aliases": ["light brown sugar", "dark brown sugar"]},
    {"name": "tomato sauce", "category": "pantry", "aliases": ["marinara", "pasta sauce"]},
    {"name": "chicken broth", "category": "pantry", "aliases": ["chicken stock", "chicken bouillon"]},
    {"name": "beef broth", "category": "pantry", "aliases": ["beef stock", "beef bouillon"]},
    {"name": "coconut milk", "category": "pantry", "aliases": ["canned coconut milk"]},
    {"name": "peanut butter", "category": "pantry", "aliases": []},
    {"name": "canned tomatoes", "category": "pantry", "aliases": ["diced tomatoes", "crushed tomatoes"]},
    {"name": "beans", "category": "pantry", "aliases": ["black beans", "kidney beans", "pinto beans", "chickpeas"]},
    
    # Spices
    {"name": "salt", "category": "spices", "aliases": ["sea salt", "kosher salt", "table salt"]},
    {"name": "black pepper", "category": "spices", "aliases": ["pepper", "ground pepper", "cracked pepper"]},
    {"name": "garlic powder", "category": "spices", "aliases": ["granulated garlic"]},
    {"name": "onion powder", "category": "spices", "aliases": []},
    {"name": "paprika", "category": "spices", "aliases": ["smoked paprika", "sweet paprika"]},
    {"name": "cumin", "category": "spices", "aliases": ["ground cumin", "cumin powder"]},
    {"name": "oregano", "category": "spices", "aliases": ["dried oregano"]},
    {"name": "thyme", "category": "spices", "aliases": ["dried thyme", "fresh thyme"]},
    {"name": "rosemary", "category": "spices", "aliases": ["dried rosemary", "fresh rosemary"]},
    {"name": "cinnamon", "category": "spices", "aliases": ["ground cinnamon", "cinnamon sticks"]},
    {"name": "chili powder", "category": "spices", "aliases": ["chile powder"]},
    {"name": "cayenne", "category": "spices", "aliases": ["cayenne pepper", "red pepper flakes"]},
    {"name": "italian seasoning", "category": "spices", "aliases": []},
    {"name": "curry powder", "category": "spices", "aliases": []},
    {"name": "turmeric", "category": "spices", "aliases": ["ground turmeric"]},
    {"name": "garam masala", "category": "spices", "aliases": []},
]


async def fetch_from_open_food_facts(limit: int = 100) -> list[dict]:
    """
    Fetch ingredients from Open Food Facts API.
    
    Note: Open Food Facts is primarily a product database, not ingredients.
    We use it to supplement our core ingredients list.
    """
    ingredients = []
    
    async with httpx.AsyncClient() as client:
        # Search for common ingredient categories
        categories_to_search = [
            "vegetables", "fruits", "cheeses", "meats", "fish", 
            "spices", "oils", "pasta", "rice"
        ]
        
        for category in categories_to_search:
            if len(ingredients) >= limit:
                break
                
            try:
                # Open Food Facts API endpoint
                url = f"https://world.openfoodfacts.org/cgi/search.pl"
                params = {
                    "action": "process",
                    "tagtype_0": "categories",
                    "tag_contains_0": "contains",
                    "tag_0": category,
                    "page_size": min(20, limit - len(ingredients)),
                    "json": 1,
                }
                
                response = await client.get(url, params=params, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    products = data.get("products", [])
                    
                    for product in products:
                        name = product.get("product_name", "").lower().strip()
                        if not name or len(name) < 2 or len(name) > 50:
                            continue
                        
                        # Determine category
                        product_categories = product.get("categories_hierarchy", [])
                        our_category = "other"
                        for pc in product_categories:
                            pc_clean = pc.replace("en:", "").lower()
                            if pc_clean in CATEGORY_MAP:
                                mapped = CATEGORY_MAP[pc_clean]
                                if mapped:
                                    our_category = mapped
                                    break
                        
                        ingredients.append({
                            "name": name,
                            "category": our_category,
                            "aliases": [],
                            "source": "open_food_facts",
                        })
                        
            except Exception as e:
                print(f"  Warning: Failed to fetch {category}: {e}")
    
    return ingredients[:limit]


async def seed_ingredients(limit: int = 200, dry_run: bool = False) -> None:
    """
    Seed ingredients into the database.
    
    Strategy:
    1. Always insert core ingredients (they have aliases and proper categories)
    2. Optionally supplement with Open Food Facts data
    """
    print("🌱 Seeding ingredients...")
    
    # Start with core ingredients
    all_ingredients = list(CORE_INGREDIENTS)
    print(f"  Core ingredients: {len(all_ingredients)}")
    
    # Optionally fetch more from API
    if limit > len(all_ingredients):
        print(f"  Fetching additional ingredients from Open Food Facts...")
        api_ingredients = await fetch_from_open_food_facts(limit - len(all_ingredients))
        
        # Dedupe: don't add if name already exists
        existing_names = {ing["name"].lower() for ing in all_ingredients}
        for ing in api_ingredients:
            if ing["name"].lower() not in existing_names:
                all_ingredients.append(ing)
                existing_names.add(ing["name"].lower())
        
        print(f"  Added {len(api_ingredients)} from API")
    
    print(f"  Total ingredients to seed: {len(all_ingredients)}")
    
    if dry_run:
        print("\n🔍 Dry run - would insert:")
        for ing in all_ingredients[:10]:
            print(f"  - {ing['name']} ({ing['category']})")
        if len(all_ingredients) > 10:
            print(f"  ... and {len(all_ingredients) - 10} more")
        return
    
    # Insert into database
    client = get_client()
    
    # Format for Supabase
    records = [
        {
            "name": ing["name"],
            "category": ing["category"],
            "aliases": ing.get("aliases", []),
        }
        for ing in all_ingredients
    ]
    
    # Use upsert to avoid duplicates (assuming name has unique constraint)
    try:
        # Try batch upsert first
        result = client.table("ingredients").upsert(
            records, 
            on_conflict="name",
            ignore_duplicates=True
        ).execute()
        print(f"  ✅ Upserted {len(records)} ingredients")
    except Exception as e:
        print(f"  ⚠️ Batch upsert failed: {e}")
        print("  Trying individual inserts...")
        
        success = 0
        skipped = 0
        for record in records:
            try:
                client.table("ingredients").upsert(
                    record, 
                    on_conflict="name",
                    ignore_duplicates=True
                ).execute()
                success += 1
            except Exception:
                skipped += 1
        
        print(f"  ✅ Inserted {success}, skipped {skipped}")
    
    print("\n✨ Seeding complete!")


def main():
    parser = argparse.ArgumentParser(description="Seed ingredients into database")
    parser.add_argument("--limit", type=int, default=200, help="Max ingredients to seed")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted")
    args = parser.parse_args()
    
    asyncio.run(seed_ingredients(limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()

