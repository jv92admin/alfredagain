#!/usr/bin/env python3
"""Test the improved ingredient matching with word-by-word fallback."""

import asyncio
import sys
sys.path.insert(0, "src")

from alfred.tools.ingredient_lookup import lookup_ingredient, _extract_ingredient_words


async def main():
    print("=" * 70)
    print("INGREDIENT MATCHING TEST")
    print("=" * 70)
    
    # Test cases that should now match
    test_cases = [
        # (input, expected_match)
        # Word-overlap cases (multi-word ingredients)
        ("fresh thai basil", "thai basil"),
        ("chicken thighs", "chicken thigh"),
        ("boneless skinless chicken thighs", "chicken thigh"),
        ("extra virgin olive oil", "olive oil"),
        # Prep word filtering cases
        ("frozen cod filet", "cod"),
        ("Trader Joe's organic eggs", "eggs"),  
        ("minced garlic", "garlic"),
        ("fresh basil leaves", "basil"),
        ("diced yellow onion", "onion"),
        ("large russet potato", "potato"),
        # Control cases - should still work
        ("garlic", "garlic"),
        ("eggs", "eggs"),
        ("chicken", "chicken"),
        ("Thai basil", "Thai basil"),
        ("olive oil", "olive oil"),
    ]
    
    print("\n--- Word Extraction Test ---")
    for test_input, _ in test_cases:
        words = _extract_ingredient_words(test_input)
        print(f"  '{test_input}' -> {words}")
    
    print("\n--- Full Matching Test ---")
    for test_input, expected in test_cases:
        match = await lookup_ingredient(test_input, operation="write")
        if match:
            status = "OK" if expected.lower() in match.name.lower() else "UNEXPECTED"
            print(f"  [{status}] '{test_input}' -> '{match.name}' ({match.match_type}, {match.confidence:.2f})")
        else:
            print(f"  [MISS] '{test_input}' -> NO MATCH (expected: {expected})")


if __name__ == "__main__":
    asyncio.run(main())
