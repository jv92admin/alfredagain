#!/usr/bin/env python3
"""Show duplicate ingredients with their categories."""

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
    
    # Find duplicates
    duplicates = {name: items for name, items in by_name.items() if len(items) > 1}
    
    print("=" * 80)
    print(f"DUPLICATE INGREDIENTS ({len(duplicates)} unique names with duplicates)")
    print("=" * 80)
    
    # Group duplicates by their category pairs
    category_pairs = defaultdict(list)
    
    for name, items in sorted(duplicates.items()):
        cats = tuple(sorted(i["category"] for i in items))
        category_pairs[cats].append((name, items))
    
    print("\n" + "-" * 80)
    print("GROUPED BY CATEGORY PAIRS")
    print("-" * 80)
    
    for cats, dupes in sorted(category_pairs.items(), key=lambda x: -len(x[1])):
        print(f"\n{cats[0]} + {cats[1]} ({len(dupes)} duplicates):")
        for name, items in dupes[:10]:
            ids = [i["id"][:8] for i in items]
            print(f"  '{name}' - IDs: {ids}")
        if len(dupes) > 10:
            print(f"  ... and {len(dupes) - 10} more")
    
    # Full list
    print("\n" + "=" * 80)
    print("FULL DUPLICATE LIST (for manual review)")
    print("=" * 80)
    
    for name, items in sorted(duplicates.items()):
        print(f"\n'{name}':")
        for i in items:
            aliases = i.get("aliases") or []
            alias_str = f" (aliases: {len(aliases)})" if aliases else ""
            print(f"  [{i['id'][:8]}] category: {i['category']}{alias_str}")


if __name__ == "__main__":
    main()
