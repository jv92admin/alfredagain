#!/usr/bin/env python3
"""Debug why basil doesn't exact match."""
import asyncio
import sys
sys.path.insert(0, "src")

from alfred_kitchen.domain.tools.ingredient_lookup import lookup_ingredient_exact, lookup_ingredient_fuzzy


async def main():
    # Test exact match on "basil"
    print("Testing exact match on 'basil':")
    match = await lookup_ingredient_exact("basil")
    print(f"  Result: {match}")
    
    print("\nTesting fuzzy match on 'basil':")
    match = await lookup_ingredient_fuzzy("basil", threshold=0.6)
    print(f"  Result: {match}")
    
    print("\nTesting fuzzy match on 'leaves':")
    match = await lookup_ingredient_fuzzy("leaves", threshold=0.6)
    print(f"  Result: {match}")


if __name__ == "__main__":
    asyncio.run(main())
