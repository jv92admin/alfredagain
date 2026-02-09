"""
Audit script for recipe metadata and ingredient linkage.

Checks:
1. Recipe metadata coverage (cuisines, tags, difficulties)
2. Ingredient linkage rate across tables
3. Ingredient category coverage in ingredients table

Run: python scripts/audit_metadata_and_ingredients.py
"""

import asyncio
import os
import sys
from collections import Counter

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

from alfred_kitchen.db.client import get_client


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def print_subsection(title: str):
    print(f"\n--- {title} ---")


async def audit_recipes():
    """Audit recipe metadata coverage."""
    print_section("RECIPE METADATA AUDIT")
    
    client = get_client()
    
    # Get all recipes
    result = client.table("recipes").select("id, name, cuisine, difficulty, tags, prep_time_minutes, cook_time_minutes").execute()
    recipes = result.data
    
    print(f"\nTotal recipes: {len(recipes)}")
    
    # Cuisine distribution
    print_subsection("Cuisines")
    cuisines = Counter(r.get("cuisine") or "NULL" for r in recipes)
    for cuisine, count in cuisines.most_common():
        print(f"  {cuisine}: {count}")
    
    # Difficulty distribution
    print_subsection("Difficulties")
    difficulties = Counter(r.get("difficulty") or "NULL" for r in recipes)
    for diff, count in difficulties.most_common():
        print(f"  {diff}: {count}")
    
    # Tag analysis
    print_subsection("Tags")
    all_tags = []
    recipes_with_tags = 0
    for r in recipes:
        tags = r.get("tags") or []
        if tags:
            recipes_with_tags += 1
            all_tags.extend(tags)
    
    print(f"  Recipes with tags: {recipes_with_tags}/{len(recipes)} ({100*recipes_with_tags/len(recipes):.0f}%)")
    print(f"  Unique tags: {len(set(all_tags))}")
    print(f"\n  Tag distribution:")
    tag_counts = Counter(all_tags)
    for tag, count in tag_counts.most_common(20):
        print(f"    {tag}: {count}")
    
    # Time coverage
    print_subsection("Time Fields")
    with_prep = sum(1 for r in recipes if r.get("prep_time_minutes"))
    with_cook = sum(1 for r in recipes if r.get("cook_time_minutes"))
    print(f"  With prep_time: {with_prep}/{len(recipes)}")
    print(f"  With cook_time: {with_cook}/{len(recipes)}")
    
    # List all recipes
    print_subsection("All Recipes")
    for r in recipes:
        tags_str = ", ".join(r.get("tags") or [])[:50]
        print(f"  - {r['name'][:40]:<40} | {r.get('cuisine', 'NULL'):<15} | {r.get('difficulty', 'NULL'):<10} | {tags_str}")


async def audit_ingredient_linkage():
    """Audit ingredient_id coverage across tables."""
    print_section("INGREDIENT LINKAGE AUDIT")
    
    client = get_client()
    
    tables = ["recipe_ingredients", "inventory", "shopping_list"]
    
    for table in tables:
        print_subsection(f"{table}")
        
        try:
            result = client.table(table).select("id, name, ingredient_id").execute()
            rows = result.data
            
            total = len(rows)
            linked = sum(1 for r in rows if r.get("ingredient_id"))
            unlinked = total - linked
            
            print(f"  Total rows: {total}")
            print(f"  With ingredient_id: {linked} ({100*linked/total:.0f}%)" if total > 0 else "  With ingredient_id: 0")
            print(f"  Without ingredient_id: {unlinked}")
            
            # Show unlinked items
            if unlinked > 0:
                print(f"\n  Unlinked items (first 10):")
                unlinked_items = [r["name"] for r in rows if not r.get("ingredient_id")][:10]
                for item in unlinked_items:
                    print(f"    - {item}")
        
        except Exception as e:
            print(f"  Error querying {table}: {e}")


async def audit_ingredients_table():
    """Audit the ingredients master table."""
    print_section("INGREDIENTS TABLE AUDIT")
    
    client = get_client()
    
    result = client.table("ingredients").select("id, name, category, aliases").execute()
    ingredients = result.data
    
    print(f"\nTotal ingredients in catalog: {len(ingredients)}")
    
    # Category distribution
    print_subsection("Categories")
    categories = Counter(i.get("category") or "NULL" for i in ingredients)
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")
    
    # Alias coverage
    print_subsection("Alias Coverage")
    with_aliases = sum(1 for i in ingredients if i.get("aliases"))
    total_aliases = sum(len(i.get("aliases") or []) for i in ingredients)
    print(f"  Ingredients with aliases: {with_aliases}/{len(ingredients)}")
    print(f"  Total aliases: {total_aliases}")
    
    # Sample by category
    print_subsection("Sample Ingredients by Category (first 5 each)")
    by_category = {}
    for i in ingredients:
        cat = i.get("category") or "NULL"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(i["name"])
    
    for cat in sorted(by_category.keys()):
        items = by_category[cat][:5]
        print(f"  {cat}: {', '.join(items)}")


async def main():
    print("\n" + "="*60)
    print("  ALFRED METADATA & INGREDIENT AUDIT")
    print("="*60)
    
    await audit_recipes()
    await audit_ingredient_linkage()
    await audit_ingredients_table()
    
    print("\n" + "="*60)
    print("  AUDIT COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
