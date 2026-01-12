#!/usr/bin/env python3
"""
Backfill category from ingredients table to linked tables.
"""

from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    return create_client(url, key)


def backfill_table(sb, table_name: str, execute: bool = False):
    """Backfill category for a table from ingredients."""
    print(f"\n{'='*60}")
    print(f"TABLE: {table_name}")
    print(f"{'='*60}")
    
    # Fetch records with ingredient_id but missing category
    result = sb.table(table_name).select("id, name, ingredient_id, category").not_.is_("ingredient_id", "null").execute()
    records = result.data
    print(f"Total linked records: {len(records)}")
    
    # Filter to those missing category
    missing = [r for r in records if not r.get("category")]
    print(f"Missing category: {len(missing)}")
    
    if not missing:
        print("Nothing to backfill")
        return
    
    # Get all ingredients we need
    ingredient_ids = list(set(r["ingredient_id"] for r in missing))
    ing_result = sb.table("ingredients").select("id, category").in_("id", ingredient_ids).execute()
    ing_map = {i["id"]: i["category"] for i in ing_result.data}
    
    changes = []
    for rec in missing:
        ing_id = rec["ingredient_id"]
        category = ing_map.get(ing_id)
        if category:
            changes.append({
                "id": rec["id"],
                "name": rec["name"],
                "category": category,
            })
    
    print(f"Records to update: {len(changes)}")
    
    if changes:
        print("\nSample changes:")
        for c in changes[:10]:
            print(f"  '{c['name']}' -> category: {c['category']}")
        if len(changes) > 10:
            print(f"  ... and {len(changes) - 10} more")
    
    if execute and changes:
        print(f"\nApplying changes...")
        for c in changes:
            sb.table(table_name).update({"category": c["category"]}).eq("id", c["id"]).execute()
        print(f"  Updated {len(changes)} records")


def main():
    import sys
    execute = "--execute" in sys.argv
    
    print("=" * 60)
    print("CATEGORY BACKFILL")
    print("=" * 60)
    
    if not execute:
        print("DRY RUN - use --execute to apply changes")
    
    sb = get_supabase()
    
    tables = ["recipe_ingredients", "inventory", "shopping_list"]
    for table in tables:
        backfill_table(sb, table, execute)
    
    if not execute:
        print(f"\nRun with --execute to apply changes")


if __name__ == "__main__":
    main()
