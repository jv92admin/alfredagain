#!/usr/bin/env python3
"""Fill in missing tags for recipes."""

import sys
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()


# Manual fills based on recipe content
FILLS = {
    # Indian-Inspired Cod Curry
    "ba7169e8-3cd4-4846-8210-96862c9bc41d": {
        "flavor_tags": ["savory", "rich"],
        "equipment_tags": ["oven"],
    },
    # Air Fryer Paneer Tikka
    "8519b0fc-55d3-4eac-b5c9-8266f0e6945c": {
        "flavor_tags": ["savory", "spicy"],
    },
    # Air Fryer Chicken Tikka Bites
    "6f660299-02c5-4dbd-8c52-be262c544189": {
        "flavor_tags": ["savory", "spicy"],
        "health_tags": ["high-protein"],
    },
    # Crispy Air Fryer Dry Rub Wings
    "3f86d793-1526-44c6-9bc2-51668822da25": {
        "flavor_tags": ["savory", "tangy"],
        "health_tags": ["high-protein"],
    },
    # Thai Chicken Pad See Ew
    "ce221431-93ab-42e9-b7a7-b72ab5fc8b25": {
        "flavor_tags": ["savory", "umami"],
        "equipment_tags": ["stovetop"],
    },
    # Beginner's Thai Yellow Curry
    "68ddfaeb-bd03-4dea-8922-f6b79b68119d": {
        "flavor_tags": ["savory", "rich"],
        "equipment_tags": ["one-pot"],
    },
    # Malaysian-Style Sambal Stir Fry Noodles
    "7a28b548-dbd2-4392-8954-d6fdb08e9890": {
        "equipment_tags": ["stovetop"],
    },
    # Decadent Chai-Spiced French Toast
    "cca357c3-aefd-4deb-8e2f-400fec9e1526": {
        "equipment_tags": ["stovetop"],
    },
}


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY")
    return create_client(url, key)


def main():
    execute = "--execute" in sys.argv
    
    sb = get_supabase()
    
    # Get recipe names for display
    result = sb.table("recipes").select("id, name").execute()
    names = {r["id"]: r["name"] for r in result.data}
    
    print("=" * 70)
    print("FILLING MISSING TAGS")
    print("=" * 70)
    
    for recipe_id, fills in FILLS.items():
        name = names.get(recipe_id, recipe_id)
        print(f"\n{name[:50]}...")
        for key, value in fills.items():
            print(f"  {key}: {value}")
        
        if execute:
            result = sb.table("recipes").update(fills).eq("id", recipe_id).execute()
            if result.data:
                print("  [OK] Updated")
            else:
                print(f"  [FAIL] {result}")
    
    if not execute:
        print("\n" + "-" * 70)
        print("Run with --execute to apply changes")
        print("-" * 70)
    else:
        print("\n[OK] All done!")


if __name__ == "__main__":
    main()
