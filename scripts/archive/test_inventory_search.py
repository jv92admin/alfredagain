#!/usr/bin/env python3
"""Test smart inventory search with ingredient matching."""

import asyncio
from alfred.tools.crud import db_read, DbReadParams, FilterClause

async def test():
    user_id = "00000000-0000-0000-0000-000000000002"
    
    print("=" * 60)
    print("Testing smart inventory search")
    print("=" * 60)
    
    # Test 1: Search for "chicken" - should find chicken breasts, chicken thighs, etc.
    print("\n1. Search: 'chicken'")
    result = await db_read(
        DbReadParams(
            table="inventory",
            filters=[FilterClause(field="name", op="ilike", value="%chicken%")],
            limit=10
        ),
        user_id=user_id
    )
    print(f"   Found {len(result)} items:")
    for item in result:
        print(f"   - {item.get('name')} (ingredient_id: {item.get('ingredient_id')})")
    
    # Test 2: Search for "paneer"
    print("\n2. Search: 'paneer'")
    result = await db_read(
        DbReadParams(
            table="inventory",
            filters=[FilterClause(field="name", op="ilike", value="%paneer%")],
            limit=10
        ),
        user_id=user_id
    )
    print(f"   Found {len(result)} items:")
    for item in result:
        print(f"   - {item.get('name')} (ingredient_id: {item.get('ingredient_id')})")
    
    # Test 3: OR filters for multiple ingredients
    print("\n3. OR search: 'chicken' OR 'paneer'")
    result = await db_read(
        DbReadParams(
            table="inventory",
            filters=[],
            or_filters=[
                FilterClause(field="name", op="ilike", value="%chicken%"),
                FilterClause(field="name", op="ilike", value="%paneer%"),
            ],
            limit=10
        ),
        user_id=user_id
    )
    print(f"   Found {len(result)} items:")
    for item in result:
        print(f"   - {item.get('name')} (ingredient_id: {item.get('ingredient_id')})")

if __name__ == "__main__":
    asyncio.run(test())
