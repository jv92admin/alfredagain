#!/usr/bin/env python3
"""
Re-run ingredient matching across all linked tables using improved algorithm.
"""

import asyncio
import sys
sys.path.insert(0, "src")

from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

from alfred_kitchen.domain.tools.ingredient_lookup import lookup_ingredient


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    return create_client(url, key)


async def relink_table(sb, table_name: str, execute: bool = False):
    """Re-link ingredients in a table."""
    print(f"\n{'='*60}")
    print(f"TABLE: {table_name}")
    print(f"{'='*60}")
    
    # Fetch all records
    result = sb.table(table_name).select("id, name, ingredient_id").execute()
    records = result.data
    print(f"Total records: {len(records)}")
    
    changes = []
    unchanged = 0
    newly_linked = 0
    relinked = 0
    still_unlinked = 0
    
    for rec in records:
        name = rec.get("name")
        old_id = rec.get("ingredient_id")
        
        if not name:
            continue
        
        # Run new matching
        match = await lookup_ingredient(name, operation="write", use_semantic=False)
        new_id = match.id if match else None
        
        if new_id == old_id:
            unchanged += 1
        elif old_id is None and new_id is not None:
            newly_linked += 1
            changes.append({
                "id": rec["id"],
                "name": name,
                "old": None,
                "new": match.name,
                "new_id": new_id,
                "category": match.category,
            })
        elif old_id is not None and new_id != old_id:
            relinked += 1
            changes.append({
                "id": rec["id"],
                "name": name,
                "old_id": old_id,
                "new": match.name if match else None,
                "new_id": new_id,
                "category": match.category if match else None,
            })
        else:
            still_unlinked += 1
    
    print(f"\nResults:")
    print(f"  Unchanged: {unchanged}")
    print(f"  Newly linked: {newly_linked}")
    print(f"  Re-linked (different match): {relinked}")
    print(f"  Still unlinked: {still_unlinked}")
    
    if changes:
        print(f"\nChanges ({len(changes)}):")
        for c in changes[:20]:
            old = c.get("old") or "(none)"
            new = c.get("new") or "(none)"
            print(f"  '{c['name']}': {old} -> {new}")
        if len(changes) > 20:
            print(f"  ... and {len(changes) - 20} more")
    
    if execute and changes:
        print(f"\nApplying changes...")
        for c in changes:
            update_data = {"ingredient_id": c["new_id"]}
            # Also copy category from the match
            if c.get("category"):
                update_data["category"] = c["category"]
            sb.table(table_name).update(update_data).eq("id", c["id"]).execute()
        print(f"  Updated {len(changes)} records")
    
    return {
        "table": table_name,
        "total": len(records),
        "unchanged": unchanged,
        "newly_linked": newly_linked,
        "relinked": relinked,
        "still_unlinked": still_unlinked,
    }


async def main():
    execute = "--execute" in sys.argv
    
    print("=" * 60)
    print("INGREDIENT RE-LINKING")
    print("=" * 60)
    
    if not execute:
        print("DRY RUN - use --execute to apply changes")
    
    sb = get_supabase()
    
    tables = ["recipe_ingredients", "inventory", "shopping_list"]
    results = []
    
    for table in tables:
        result = await relink_table(sb, table, execute)
        results.append(result)
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    total_newly = sum(r["newly_linked"] for r in results)
    total_relinked = sum(r["relinked"] for r in results)
    total_still = sum(r["still_unlinked"] for r in results)
    
    print(f"Newly linked: {total_newly}")
    print(f"Re-linked: {total_relinked}")
    print(f"Still unlinked: {total_still}")
    
    if not execute:
        print(f"\nRun with --execute to apply changes")


if __name__ == "__main__":
    asyncio.run(main())
