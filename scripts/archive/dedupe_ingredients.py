#!/usr/bin/env python3
"""
Deduplicate ingredients - keep the one with more aliases.
"""

import sys
from supabase import create_client
from dotenv import load_dotenv
from collections import defaultdict
import os

load_dotenv()


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY")
    return create_client(url, key)


def main():
    execute = "--execute" in sys.argv
    
    sb = get_supabase()
    
    # Fetch all ingredients
    all_ingredients = []
    page_size = 1000
    offset = 0
    
    while True:
        result = sb.table("ingredients").select(
            "id, name, category, aliases"
        ).range(offset, offset + page_size - 1).execute()
        
        if not result.data:
            break
        all_ingredients.extend(result.data)
        offset += page_size
        if len(result.data) < page_size:
            break
    
    print(f"Fetched {len(all_ingredients)} ingredients\n")
    
    # Group by name
    by_name = defaultdict(list)
    for i in all_ingredients:
        key = i["name"].lower().strip()
        by_name[key].append(i)
    
    # Find duplicates and decide which to delete
    to_delete = []
    
    for name, items in by_name.items():
        if len(items) > 1:
            # Sort by alias count (descending) - keep the one with most aliases
            items_sorted = sorted(items, key=lambda x: len(x.get("aliases") or []), reverse=True)
            keep = items_sorted[0]
            delete = items_sorted[1:]
            
            print(f"'{name}':")
            print(f"  KEEP: [{keep['id'][:8]}] {keep['category']} ({len(keep.get('aliases') or [])} aliases)")
            for d in delete:
                print(f"  DEL:  [{d['id'][:8]}] {d['category']} ({len(d.get('aliases') or [])} aliases)")
                to_delete.append(d['id'])
    
    print(f"\n{'='*60}")
    print(f"Total to delete: {len(to_delete)}")
    print(f"{'='*60}")
    
    if execute:
        # Build mapping: delete_id -> keep_id
        delete_to_keep = {}
        for name, items in by_name.items():
            if len(items) > 1:
                items_sorted = sorted(items, key=lambda x: len(x.get("aliases") or []), reverse=True)
                keep_id = items_sorted[0]["id"]
                for d in items_sorted[1:]:
                    delete_to_keep[d["id"]] = keep_id
        
        # Tables that reference ingredients
        ref_tables = ["recipe_ingredients", "inventory", "shopping_list", "flavor_preferences"]
        
        print("\nUpdating foreign key references...")
        for table in ref_tables:
            for delete_id, keep_id in delete_to_keep.items():
                # Update references from delete_id to keep_id
                result = sb.table(table).update({"ingredient_id": keep_id}).eq("ingredient_id", delete_id).execute()
                if result.data:
                    print(f"  {table}: Updated {len(result.data)} refs from {delete_id[:8]} -> {keep_id[:8]}")
        
        print("\nDeleting duplicates...")
        deleted = 0
        for i, id in enumerate(to_delete):
            try:
                result = sb.table("ingredients").delete().eq("id", id).execute()
                deleted += 1
                if (deleted) % 10 == 0:
                    print(f"  Deleted {deleted}/{len(to_delete)}")
            except Exception as e:
                print(f"  [WARN] Could not delete {id[:8]}: {e}")
        print(f"\n[OK] Deleted {deleted} duplicates")
        
        # Verify
        result = sb.table("ingredients").select("id", count="exact").execute()
        print(f"Remaining ingredients: {result.count}")
    else:
        print("\nRun with --execute to delete duplicates")


if __name__ == "__main__":
    main()
