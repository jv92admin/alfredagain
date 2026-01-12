#!/usr/bin/env python3
"""Audit recipe tags to show what's missing."""

from supabase import create_client
from dotenv import load_dotenv
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
    
    result = sb.table("recipes").select(
        "id, name, cuisine, difficulty, occasions, health_tags, flavor_tags, equipment_tags"
    ).execute()
    recipes = result.data
    
    print("=" * 80)
    print("RECIPE TAG AUDIT - What's Missing?")
    print("=" * 80)
    
    missing_summary = {
        "health_tags": [],
        "flavor_tags": [],
        "equipment_tags": [],
    }
    
    for r in recipes:
        name = r["name"][:50]
        print(f"\n{name}")
        print(f"  cuisine: {r['cuisine']}, difficulty: {r['difficulty']}")
        print(f"  occasions:      {r['occasions']}")
        print(f"  health_tags:    {r['health_tags'] or '[MISSING]'}")
        print(f"  flavor_tags:    {r['flavor_tags'] or '[MISSING]'}")
        print(f"  equipment_tags: {r['equipment_tags'] or '[MISSING]'}")
        
        if not r['health_tags']:
            missing_summary['health_tags'].append(name)
        if not r['flavor_tags']:
            missing_summary['flavor_tags'].append(name)
        if not r['equipment_tags']:
            missing_summary['equipment_tags'].append(name)
    
    print("\n" + "=" * 80)
    print("SUMMARY - Recipes Missing Tags")
    print("=" * 80)
    
    print(f"\nMissing health_tags ({len(missing_summary['health_tags'])}):")
    for name in missing_summary['health_tags']:
        print(f"  - {name}")
    
    print(f"\nMissing flavor_tags ({len(missing_summary['flavor_tags'])}):")
    for name in missing_summary['flavor_tags']:
        print(f"  - {name}")
    
    print(f"\nMissing equipment_tags ({len(missing_summary['equipment_tags'])}):")
    for name in missing_summary['equipment_tags']:
        print(f"  - {name}")
    
    print("\n" + "-" * 80)
    print("Note: Not all recipes NEED all tags.")
    print("  - health_tags: Only if diet-specific (vegetarian, gluten-free, etc)")
    print("  - flavor_tags: Primary taste profile (spicy, savory, sweet, etc)")
    print("  - equipment_tags: Only if special equipment needed")
    print("-" * 80)


if __name__ == "__main__":
    main()
