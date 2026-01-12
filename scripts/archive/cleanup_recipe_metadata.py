#!/usr/bin/env python3
"""
Recipe Metadata Cleanup Script

This script:
1. Shows current state of all recipe tags
2. Proposes migrations and tag mappings
3. Applies cleanup when run with --execute

Run: python scripts/cleanup_recipe_metadata.py
Execute: python scripts/cleanup_recipe_metadata.py --execute
"""

import asyncio
import sys
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

# === CONFIGURATION: Tag Mappings ===

# Tags to move to occasions[] (new column)
TAG_TO_OCCASION = {
    "quick": "weeknight",
    "weeknight": "weeknight",
    "hosting": "hosting",
    "make-ahead-friendly": "batch-prep",
    "meal-prep": "batch-prep",
    "brunch": "weekend",
    "party-food": "hosting",
}

# Tags to move to health_tags[] (new column)
TAG_TO_HEALTH = {
    "vegetarian": "vegetarian",
    "vegan": "vegan",
    "high-protein": "high-protein",
    "low-carb": "low-carb",
    "light": "light",
    "gluten-free": "gluten-free",
    "dairy-free": "dairy-free",
}

# Tags to move to flavor_tags[] (new column)
TAG_TO_FLAVOR = {
    "spicy": "spicy",
    "mild": "mild",
    "savory": "savory",
    "sweet": "sweet",
    "saucy": "rich",  # map saucy -> rich
    "tangy": "tangy",
    "rich": "rich",
}

# Tags to move to equipment_tags[] (new column)
TAG_TO_EQUIPMENT = {
    "air-fryer": "air-fryer",
    "air fryer": "air-fryer",  # normalize
    "instant-pot": "instant-pot",
    "one-pot": "one-pot",
    "one-pan": "one-pan",
    "no-cook": "no-cook",
    "grill": "grill",
    "slow-cooker": "slow-cooker",
}

# Tags to REMOVE (redundant with fields, or ingredient-based)
REMOVE_TAGS = {
    # Difficulty -> use difficulty field
    "beginner-friendly", "beginner", "medium",
    # Cuisine -> use cuisine field
    "indian", "thai", "malaysian", "indian-thai fusion",
    # Ingredients -> search by ingredient instead
    "rice", "noodles", "chicken", "cod", "fish",
    # Too specific
    "make-ahead sauce", "make-ahead-dip",
}


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY")
    return create_client(url, key)


def analyze_recipe_tags(recipes: list[dict]) -> dict:
    """Analyze current tags and compute proposed changes."""
    analysis = []
    
    for recipe in recipes:
        recipe_id = recipe["id"]
        name = recipe["name"]
        current_tags = recipe.get("tags") or []
        cuisine = recipe.get("cuisine")
        difficulty = recipe.get("difficulty")
        
        new_occasions = []
        new_health_tags = []
        new_flavor_tags = []
        new_equipment_tags = []
        removed = []
        
        for tag in current_tags:
            tag_lower = tag.lower().strip()
            
            if tag_lower in TAG_TO_OCCASION:
                new_occasions.append(TAG_TO_OCCASION[tag_lower])
            elif tag_lower in TAG_TO_HEALTH:
                new_health_tags.append(TAG_TO_HEALTH[tag_lower])
            elif tag_lower in TAG_TO_FLAVOR:
                new_flavor_tags.append(TAG_TO_FLAVOR[tag_lower])
            elif tag_lower in TAG_TO_EQUIPMENT:
                new_equipment_tags.append(TAG_TO_EQUIPMENT[tag_lower])
            elif tag_lower in REMOVE_TAGS:
                removed.append(tag)
            else:
                # Unknown tag - flag it
                print(f"  [!] Unknown tag '{tag}' in {name} - SKIPPING")
                removed.append(tag)
        
        # If no occasions assigned, infer from time
        prep_time = recipe.get("prep_time_minutes") or 0
        cook_time = recipe.get("cook_time_minutes") or 0
        total_time = prep_time + cook_time
        if not new_occasions:
            if total_time <= 45:
                new_occasions.append("weeknight")
            else:
                new_occasions.append("weekend")
        
        # Dedupe
        new_occasions = list(set(new_occasions))
        new_health_tags = list(set(new_health_tags))
        new_flavor_tags = list(set(new_flavor_tags))
        new_equipment_tags = list(set(new_equipment_tags))
        
        analysis.append({
            "id": recipe_id,
            "name": name,
            "current_tags": current_tags,
            "new_occasions": new_occasions,
            "new_health_tags": new_health_tags if new_health_tags else None,
            "new_flavor_tags": new_flavor_tags if new_flavor_tags else None,
            "new_equipment_tags": new_equipment_tags if new_equipment_tags else None,
            "removed": removed,
            "cuisine": cuisine,
            "difficulty": difficulty,
            "total_time": total_time,
        })
    
    return analysis


def print_analysis(analysis: list[dict]):
    """Print proposed changes."""
    print("\n" + "=" * 70)
    print("PROPOSED CHANGES (4 new columns, removing generic tags)")
    print("=" * 70)
    
    for item in analysis:
        print(f"\n>> {item['name']}")
        print(f"   Cuisine: {item['cuisine']}, Difficulty: {item['difficulty']}, Time: {item['total_time']}min")
        print(f"   Current tags: {item['current_tags']}")
        print(f"   => occasions[]:      {item['new_occasions']}")
        print(f"   => health_tags[]:    {item['new_health_tags']}")
        print(f"   => flavor_tags[]:    {item['new_flavor_tags']}")
        print(f"   => equipment_tags[]: {item['new_equipment_tags']}")
        if item['removed']:
            print(f"   x Removed: {item['removed']}")


def generate_migration_sql():
    """Generate SQL for schema migration."""
    return """
-- Migration: Replace generic tags with 4 specific tag columns
-- Run this in Supabase SQL editor

-- Add new columns
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS occasions text[];
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS health_tags text[];
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS flavor_tags text[];
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS equipment_tags text[];

-- Add check constraints for valid values
ALTER TABLE recipes ADD CONSTRAINT valid_occasions 
  CHECK (occasions IS NULL OR occasions <@ ARRAY['weeknight', 'batch-prep', 'hosting', 'weekend', 'comfort']::text[]);

ALTER TABLE recipes ADD CONSTRAINT valid_health_tags
  CHECK (health_tags IS NULL OR health_tags <@ ARRAY['high-protein', 'low-carb', 'vegetarian', 'vegan', 'light', 'gluten-free', 'dairy-free', 'keto']::text[]);

ALTER TABLE recipes ADD CONSTRAINT valid_flavor_tags
  CHECK (flavor_tags IS NULL OR flavor_tags <@ ARRAY['spicy', 'mild', 'savory', 'sweet', 'tangy', 'rich', 'light', 'umami']::text[]);

ALTER TABLE recipes ADD CONSTRAINT valid_equipment_tags
  CHECK (equipment_tags IS NULL OR equipment_tags <@ ARRAY['air-fryer', 'instant-pot', 'one-pot', 'one-pan', 'grill', 'no-cook', 'slow-cooker', 'oven', 'stovetop']::text[]);

-- Index for filtering
CREATE INDEX IF NOT EXISTS idx_recipes_occasions ON recipes USING GIN (occasions);
CREATE INDEX IF NOT EXISTS idx_recipes_health_tags ON recipes USING GIN (health_tags);
CREATE INDEX IF NOT EXISTS idx_recipes_flavor_tags ON recipes USING GIN (flavor_tags);
CREATE INDEX IF NOT EXISTS idx_recipes_equipment_tags ON recipes USING GIN (equipment_tags);

-- Drop old generic tags column (run AFTER data migration)
-- ALTER TABLE recipes DROP COLUMN IF EXISTS tags;
"""


def generate_update_sql(analysis: list[dict]) -> str:
    """Generate SQL for updating recipes."""
    sqls = []
    for item in analysis:
        occasions_sql = f"ARRAY{item['new_occasions']}::text[]" if item['new_occasions'] else "ARRAY['weeknight']::text[]"
        health_sql = f"ARRAY{item['new_health_tags']}::text[]" if item['new_health_tags'] else "NULL"
        flavor_sql = f"ARRAY{item['new_flavor_tags']}::text[]" if item['new_flavor_tags'] else "NULL"
        equipment_sql = f"ARRAY{item['new_equipment_tags']}::text[]" if item['new_equipment_tags'] else "NULL"
        
        sql = f"""
UPDATE recipes SET
  tags = NULL,
  occasions = {occasions_sql},
  health_tags = {health_sql},
  flavor_tags = {flavor_sql},
  equipment_tags = {equipment_sql}
WHERE id = '{item['id']}';
-- {item['name']}"""
        sqls.append(sql)
    
    return "\n".join(sqls)


async def execute_updates(sb, analysis: list[dict]):
    """Execute the updates."""
    print("\n" + "=" * 70)
    print("EXECUTING UPDATES")
    print("=" * 70)
    
    for item in analysis:
        print(f"\n  Updating: {item['name']}...")
        
        update_data = {
            "tags": None,  # Clear old generic tags
            "occasions": item["new_occasions"],
            "health_tags": item["new_health_tags"],
            "flavor_tags": item["new_flavor_tags"],
            "equipment_tags": item["new_equipment_tags"],
        }
        
        result = sb.table("recipes").update(update_data).eq("id", item["id"]).execute()
        
        if result.data:
            print(f"    [OK] Updated")
        else:
            print(f"    [FAIL] Failed: {result}")


async def main():
    execute = "--execute" in sys.argv
    
    print("Recipe Metadata Cleanup")
    print("=" * 70)
    
    sb = get_supabase()
    
    # Fetch recipes
    result = sb.table("recipes").select("id, name, tags, cuisine, difficulty, prep_time_minutes, cook_time_minutes").execute()
    recipes = result.data
    
    print(f"\nFound {len(recipes)} recipes")
    
    # Analyze
    analysis = analyze_recipe_tags(recipes)
    
    # Print analysis
    print_analysis(analysis)
    
    # Print migration SQL
    print("\n" + "=" * 70)
    print("MIGRATION SQL (run first in Supabase)")
    print("=" * 70)
    print(generate_migration_sql())
    
    # Print update SQL
    print("\n" + "=" * 70)
    print("UPDATE SQL (or use --execute flag)")
    print("=" * 70)
    print(generate_update_sql(analysis))
    
    if execute:
        auto_yes = "--yes" in sys.argv
        if auto_yes:
            await execute_updates(sb, analysis)
            print("\n[OK] Done!")
        else:
            confirm = input("\n[!] Execute updates? (yes/no): ")
            if confirm.lower() == "yes":
                await execute_updates(sb, analysis)
                print("\n[OK] Done!")
            else:
                print("\nAborted.")
    else:
        print("\n" + "-" * 70)
        print("Run with --execute to apply changes")
        print("-" * 70)


if __name__ == "__main__":
    asyncio.run(main())
