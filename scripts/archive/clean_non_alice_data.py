"""
Clean slate migration - Delete all user data except Alice's.

Alice's user_id: 00000000-0000-0000-0000-000000000002

Usage:
    python scripts/clean_non_alice_data.py
    
Add --dry-run to preview without deleting:
    python scripts/clean_non_alice_data.py --dry-run
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alfred_kitchen.db.client import get_client

ALICE_USER_ID = "00000000-0000-0000-0000-000000000002"

# Tables with user_id column (order matters for FK constraints)
USER_TABLES = [
    "recipe_ingredients",  # FK to recipes, delete first
    "recipes",
    "meal_plans",
    "inventory",
    "shopping_list",
    "tasks",
    "cooking_log",
    "user_top_ingredients",
]


def clean_all_except_alice(dry_run: bool = False):
    """Delete all user data except Alice's."""
    client = get_client()
    
    print(f"\n{'=' * 60}")
    print(f"CLEAN SLATE - Delete all data except Alice's")
    print(f"Alice user_id: {ALICE_USER_ID}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will delete!)'}")
    print(f"{'=' * 60}\n")
    
    total_deleted = 0
    
    for table in USER_TABLES:
        try:
            # Count records to delete
            if table == "recipe_ingredients":
                # recipe_ingredients doesn't have user_id, linked via recipes
                # Get recipe IDs that are NOT Alice's
                non_alice_recipes = (
                    client.table("recipes")
                    .select("id")
                    .neq("user_id", ALICE_USER_ID)
                    .execute()
                )
                recipe_ids = [r["id"] for r in non_alice_recipes.data]
                
                if recipe_ids:
                    count_result = (
                        client.table(table)
                        .select("id", count="exact")
                        .in_("recipe_id", recipe_ids)
                        .execute()
                    )
                    count = count_result.count or 0
                    
                    if not dry_run and count > 0:
                        client.table(table).delete().in_("recipe_id", recipe_ids).execute()
                else:
                    count = 0
            else:
                # Regular user_id based tables
                count_result = (
                    client.table(table)
                    .select("id", count="exact")
                    .neq("user_id", ALICE_USER_ID)
                    .execute()
                )
                count = count_result.count or 0
                
                if not dry_run and count > 0:
                    client.table(table).delete().neq("user_id", ALICE_USER_ID).execute()
            
            status = "would delete" if dry_run else "deleted"
            print(f"  {table}: {status} {count} records")
            total_deleted += count
            
        except Exception as e:
            print(f"  {table}: ERROR - {e}")
    
    print(f"\n{'=' * 60}")
    print(f"Total: {'would delete' if dry_run else 'deleted'} {total_deleted} records")
    if dry_run:
        print("\nRun without --dry-run to actually delete.")
    else:
        print("\n✅ Clean slate complete! Only Alice's data remains.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    clean_all_except_alice(dry_run=dry_run)

