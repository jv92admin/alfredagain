#!/usr/bin/env python3
"""
Audit the ingredients database for:
1. Total row count
2. Duplicates / similar entries
3. Category coverage
4. Alias coverage
"""

from supabase import create_client
from dotenv import load_dotenv
from collections import Counter
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
    
    print("=" * 70)
    print("INGREDIENTS DATABASE AUDIT")
    print("=" * 70)
    
    # Get total count
    result = sb.table("ingredients").select("id", count="exact").execute()
    total_count = result.count
    print(f"\nTotal ingredients: {total_count}")
    
    # Fetch all for analysis (paginated if needed)
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
        print(f"  Fetched {len(all_ingredients)} / {total_count}...")
        
        if len(result.data) < page_size:
            break
    
    print(f"\nFetched {len(all_ingredients)} ingredients")
    
    # Category breakdown
    print("\n" + "-" * 70)
    print("CATEGORY BREAKDOWN")
    print("-" * 70)
    
    categories = Counter(i.get("category") or "NULL" for i in all_ingredients)
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")
    
    # Alias coverage
    print("\n" + "-" * 70)
    print("ALIAS COVERAGE")
    print("-" * 70)
    
    with_aliases = sum(1 for i in all_ingredients if i.get("aliases"))
    without_aliases = len(all_ingredients) - with_aliases
    print(f"  With aliases: {with_aliases} ({with_aliases*100/len(all_ingredients):.1f}%)")
    print(f"  Without aliases: {without_aliases}")
    
    # Check for duplicates by name
    print("\n" + "-" * 70)
    print("DUPLICATE CHECK (exact name match)")
    print("-" * 70)
    
    name_counts = Counter(i["name"].lower().strip() for i in all_ingredients)
    duplicates = [(name, count) for name, count in name_counts.items() if count > 1]
    
    if duplicates:
        print(f"\n  Found {len(duplicates)} duplicate names:")
        for name, count in sorted(duplicates, key=lambda x: -x[1])[:20]:
            print(f"    '{name}' appears {count} times")
        if len(duplicates) > 20:
            print(f"    ... and {len(duplicates) - 20} more")
    else:
        print("  No exact duplicates found")
    
    # Check for similar names (potential duplicates)
    print("\n" + "-" * 70)
    print("SIMILAR NAMES CHECK (base ingredient variations)")
    print("-" * 70)
    
    # Group by first word
    first_word_groups = {}
    for i in all_ingredients:
        name = i["name"].lower().strip()
        first_word = name.split()[0] if name.split() else name
        if first_word not in first_word_groups:
            first_word_groups[first_word] = []
        first_word_groups[first_word].append(name)
    
    # Find groups with many variations
    print("\n  Ingredients with many variations (by first word):")
    for word, names in sorted(first_word_groups.items(), key=lambda x: -len(x[1]))[:15]:
        if len(names) > 3:
            print(f"\n  '{word}' ({len(names)} variants):")
            for name in sorted(names)[:8]:
                print(f"    - {name}")
            if len(names) > 8:
                print(f"    ... and {len(names) - 8} more")
    
    # Sample some specific common ingredients
    print("\n" + "-" * 70)
    print("SAMPLE: Common ingredient variations")
    print("-" * 70)
    
    check_words = ["onion", "chicken", "egg", "garlic", "tomato", "cheese", "rice", "oil"]
    for word in check_words:
        matches = [i["name"] for i in all_ingredients if word in i["name"].lower()]
        if matches:
            print(f"\n  '{word}' appears in {len(matches)} ingredients:")
            for m in sorted(matches)[:5]:
                print(f"    - {m}")
            if len(matches) > 5:
                print(f"    ... and {len(matches) - 5} more")


if __name__ == "__main__":
    main()
