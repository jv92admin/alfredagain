#!/usr/bin/env python3
"""Test lean semantic search (name + description only)."""

from alfred_kitchen.db.client import get_client
from alfred_kitchen.domain.tools.ingredient_lookup import generate_embedding

client = get_client()

# Vague queries (should use semantic)
vague_queries = ["comfort food", "date night dinner", "something light", "cozy winter meal"]

# Concrete queries (should use structured filters instead)
concrete_queries = ["vegetarian", "spicy", "air fryer", "quick"]

print("=" * 60)
print("VAGUE QUERIES (semantic search is appropriate)")
print("=" * 60)

for query in vague_queries:
    query_embedding = generate_embedding(query)
    result = client.rpc(
        "match_recipe_semantic",
        {
            "query_embedding": query_embedding,
            "user_id_filter": "00000000-0000-0000-0000-000000000002",
            "limit_n": 3,
            "max_distance": 0.8,
        }
    ).execute()
    
    print(f"\n'{query}':")
    for r in result.data:
        print(f"  {r['distance']:.3f} | {r['name'][:50]}")

print("\n" + "=" * 60)
print("CONCRETE QUERIES (should use structured filters, not semantic)")
print("=" * 60)

for query in concrete_queries:
    query_embedding = generate_embedding(query)
    result = client.rpc(
        "match_recipe_semantic",
        {
            "query_embedding": query_embedding,
            "user_id_filter": "00000000-0000-0000-0000-000000000002",
            "limit_n": 3,
            "max_distance": 0.8,
        }
    ).execute()
    
    print(f"\n'{query}' (Act should use filter instead):")
    for r in result.data:
        print(f"  {r['distance']:.3f} | {r['name'][:50]}")
