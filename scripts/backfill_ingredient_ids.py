"""
Backfill ingredient_id for existing records.

Links existing inventory, shopping_list, and recipe_ingredients records
to canonical ingredients using fuzzy matching.

Run: python scripts/backfill_ingredient_ids.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from alfred.db.client import get_client
from alfred.tools.ingredient_lookup import lookup_ingredient

# Tables to backfill
TABLES_WITH_INGREDIENTS = [
    "inventory",
    "shopping_list",
    "recipe_ingredients",
]

# Minimum confidence to auto-link (lower for backfill since we're reviewing)
MIN_CONFIDENCE = 0.5


async def backfill_table(supabase, table: str) -> dict:
    """Backfill ingredient_id for a single table."""
    print(f"\n  Processing {table}...")
    
    stats = {"total": 0, "matched": 0, "unmatched": 0, "errors": 0}
    
    # Get records with NULL ingredient_id
    try:
        result = supabase.table(table).select("id, name").is_("ingredient_id", "null").execute()
        records = result.data
    except Exception as e:
        print(f"    Error fetching {table}: {e}")
        return stats
    
    stats["total"] = len(records)
    print(f"    Found {len(records)} records without ingredient_id")
    
    if not records:
        return stats
    
    # Process each record
    for record in records:
        record_id = record["id"]
        name = record.get("name", "")
        
        if not name:
            stats["unmatched"] += 1
            continue
        
        try:
            # Use read operation threshold (more lenient)
            match = await lookup_ingredient(name, operation="read")
            
            if match and match.confidence >= MIN_CONFIDENCE:
                # Update the record with ingredient_id AND category (denormalized)
                update_data = {"ingredient_id": match.id}
                if match.category:
                    update_data["category"] = match.category
                
                supabase.table(table).update(update_data).eq("id", record_id).execute()
                
                stats["matched"] += 1
                cat_str = f" [{match.category}]" if match.category else ""
                print(f"      + {name} -> {match.name}{cat_str} ({match.confidence:.0%})")
            else:
                stats["unmatched"] += 1
                if match:
                    print(f"      - {name} (low confidence: {match.confidence:.0%})")
                else:
                    print(f"      - {name} (no match)")
                    
        except Exception as e:
            stats["errors"] += 1
            print(f"      ! Error processing {name}: {e}")
    
    return stats


async def backfill_all():
    """Backfill all tables."""
    print("=" * 60)
    print("Ingredient ID Backfill")
    print("=" * 60)
    
    supabase = get_client()
    
    total_stats = {"total": 0, "matched": 0, "unmatched": 0, "errors": 0}
    
    for table in TABLES_WITH_INGREDIENTS:
        stats = await backfill_table(supabase, table)
        for key in total_stats:
            total_stats[key] += stats[key]
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total records processed: {total_stats['total']}")
    print(f"  Matched and linked:      {total_stats['matched']}")
    print(f"  Unmatched (left NULL):   {total_stats['unmatched']}")
    print(f"  Errors:                  {total_stats['errors']}")
    
    if total_stats['total'] > 0:
        match_rate = total_stats['matched'] / total_stats['total'] * 100
        print(f"\n  Match rate: {match_rate:.1f}%")


if __name__ == "__main__":
    asyncio.run(backfill_all())

