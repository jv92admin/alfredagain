#!/usr/bin/env python3
"""Debug specific matching cases."""
import asyncio
import sys
sys.path.insert(0, "src")

from alfred_kitchen.db.client import get_client
from alfred_kitchen.domain.tools.ingredient_lookup import _extract_ingredient_words


async def main():
    client = get_client()
    
    # Debug "boneless skinless chicken thighs"
    print("=== 'boneless skinless chicken thighs' ===")
    words = _extract_ingredient_words("boneless skinless chicken thighs")
    print(f"Extracted words: {words}")
    
    for word in words:
        print(f"\nFuzzy matches for '{word}':")
        result = client.rpc(
            "match_ingredient_fuzzy",
            {"query": word.lower(), "threshold": 0.6, "limit_n": 5}
        ).execute()
        for row in result.data or []:
            name_words = set(row["name"].lower().split())
            print(f"  {row['name']} (sim={row['similarity']:.2f}) - name_words: {name_words}")
    
    # Debug "frozen cod filet"
    print("\n\n=== 'frozen cod filet' ===")
    words = _extract_ingredient_words("frozen cod filet")
    print(f"Extracted words: {words}")
    
    for word in words:
        print(f"\nFuzzy matches for '{word}':")
        result = client.rpc(
            "match_ingredient_fuzzy",
            {"query": word.lower(), "threshold": 0.5, "limit_n": 5}
        ).execute()
        for row in result.data or []:
            name_words = set(row["name"].lower().split())
            print(f"  {row['name']} (sim={row['similarity']:.2f}) - name_words: {name_words}")


if __name__ == "__main__":
    asyncio.run(main())
