#!/usr/bin/env python3
"""Debug why 'fresh thai basil' doesn't match 'Thai basil'."""
import asyncio
import sys
sys.path.insert(0, "src")

from alfred_kitchen.db.client import get_client


async def main():
    client = get_client()
    
    # Check what "thai" fuzzy matches
    print("Fuzzy matches for 'thai':")
    result = client.rpc(
        "match_ingredient_fuzzy",
        {"query": "thai", "threshold": 0.5, "limit_n": 10}
    ).execute()
    for row in result.data or []:
        print(f"  {row['name']} - similarity: {row['similarity']:.2f}")
    
    # Check what "basil" fuzzy matches
    print("\nFuzzy matches for 'basil':")
    result = client.rpc(
        "match_ingredient_fuzzy",
        {"query": "basil", "threshold": 0.5, "limit_n": 10}
    ).execute()
    for row in result.data or []:
        print(f"  {row['name']} - similarity: {row['similarity']:.2f}")
    
    # Check Thai basil entry
    print("\n'Thai basil' entry:")
    result = client.table("ingredients").select("*").eq("name", "Thai basil").execute()
    for row in result.data or []:
        print(f"  {row}")


if __name__ == "__main__":
    asyncio.run(main())
