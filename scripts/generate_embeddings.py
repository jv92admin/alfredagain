#!/usr/bin/env python3
"""
Generate embeddings for ingredients and recipes using OpenAI.

Stores embeddings in Supabase pgvector columns for semantic search.

Usage:
    python scripts/generate_embeddings.py --table ingredients [--batch-size 50]
    python scripts/generate_embeddings.py --table recipes [--batch-size 20]
    python scripts/generate_embeddings.py --all
"""

import argparse
import asyncio
import os
from typing import Literal

from openai import OpenAI

# Try to import from alfred, fallback to direct supabase if not in venv
try:
    from alfred.db.client import get_client
    from alfred.config import settings
    OPENAI_API_KEY = settings.openai_api_key
except ImportError:
    from supabase import create_client, Client
    
    def get_client() -> Client:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        return create_client(url, key)
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def get_openai_client() -> OpenAI:
    """Get OpenAI client."""
    return OpenAI(api_key=OPENAI_API_KEY)


def create_ingredient_text(ingredient: dict) -> str:
    """
    Create text representation of an ingredient for embedding.
    
    Combines name, category, and aliases into a single searchable text.
    """
    parts = [ingredient.get("name", "")]
    
    category = ingredient.get("category")
    if category:
        parts.append(f"category: {category}")
    
    aliases = ingredient.get("aliases", [])
    if aliases:
        parts.append(f"also known as: {', '.join(aliases)}")
    
    return " | ".join(parts)


def create_recipe_text(recipe: dict) -> str:
    """
    Create text representation of a recipe for embedding.
    
    Combines name, description, cuisine, tags, and difficulty.
    """
    parts = [recipe.get("name", "")]
    
    description = recipe.get("description")
    if description:
        parts.append(description[:200])  # Limit description length
    
    cuisine = recipe.get("cuisine")
    if cuisine:
        parts.append(f"cuisine: {cuisine}")
    
    tags = recipe.get("tags", [])
    if tags:
        parts.append(f"tags: {', '.join(tags[:5])}")
    
    difficulty = recipe.get("difficulty")
    if difficulty:
        parts.append(f"difficulty: {difficulty}")
    
    return " | ".join(parts)


def batch_embeddings(texts: list[str], client: OpenAI) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.
    
    Uses OpenAI's batch embedding API for efficiency.
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    
    return [item.embedding for item in response.data]


async def generate_ingredient_embeddings(batch_size: int = 50, force: bool = False) -> None:
    """Generate embeddings for all ingredients."""
    print("🔍 Generating ingredient embeddings...")
    
    supabase = get_client()
    openai = get_openai_client()
    
    # Fetch ingredients without embeddings (or all if force)
    query = supabase.table("ingredients").select("id, name, category, aliases")
    if not force:
        query = query.is_("embedding", "null")
    
    result = query.limit(1000).execute()
    ingredients = result.data
    
    if not ingredients:
        print("  No ingredients need embeddings")
        return
    
    print(f"  Found {len(ingredients)} ingredients to embed")
    
    # Process in batches
    total_updated = 0
    for i in range(0, len(ingredients), batch_size):
        batch = ingredients[i:i + batch_size]
        
        # Create text for each ingredient
        texts = [create_ingredient_text(ing) for ing in batch]
        
        try:
            # Generate embeddings
            embeddings = batch_embeddings(texts, openai)
            
            # Update each ingredient with its embedding
            for ing, embedding in zip(batch, embeddings):
                supabase.table("ingredients").update(
                    {"embedding": embedding}
                ).eq("id", ing["id"]).execute()
                total_updated += 1
            
            print(f"  Processed batch {i // batch_size + 1}: {len(batch)} ingredients")
            
        except Exception as e:
            print(f"  ⚠️ Error processing batch: {e}")
    
    print(f"  ✅ Updated {total_updated} ingredient embeddings")


async def generate_recipe_embeddings(batch_size: int = 20, force: bool = False) -> None:
    """Generate embeddings for all recipes."""
    print("🔍 Generating recipe embeddings...")
    
    supabase = get_client()
    openai = get_openai_client()
    
    # Fetch recipes without embeddings (or all if force)
    query = supabase.table("recipes").select("id, name, description, cuisine, tags, difficulty")
    if not force:
        query = query.is_("embedding", "null")
    
    result = query.limit(1000).execute()
    recipes = result.data
    
    if not recipes:
        print("  No recipes need embeddings")
        return
    
    print(f"  Found {len(recipes)} recipes to embed")
    
    # Process in batches
    total_updated = 0
    for i in range(0, len(recipes), batch_size):
        batch = recipes[i:i + batch_size]
        
        # Create text for each recipe
        texts = [create_recipe_text(recipe) for recipe in batch]
        
        try:
            # Generate embeddings
            embeddings = batch_embeddings(texts, openai)
            
            # Update each recipe with its embedding
            for recipe, embedding in zip(batch, embeddings):
                supabase.table("recipes").update(
                    {"embedding": embedding}
                ).eq("id", recipe["id"]).execute()
                total_updated += 1
            
            print(f"  Processed batch {i // batch_size + 1}: {len(batch)} recipes")
            
        except Exception as e:
            print(f"  ⚠️ Error processing batch: {e}")
    
    print(f"  ✅ Updated {total_updated} recipe embeddings")


async def check_vector_columns() -> bool:
    """Check if embedding columns exist in the database."""
    supabase = get_client()
    
    # Try to query with embedding column
    try:
        supabase.table("ingredients").select("id").limit(1).execute()
        return True
    except Exception as e:
        if "embedding" in str(e).lower():
            print("⚠️ Embedding column not found. Run this migration first:")
            print("""
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS embedding vector(1536);
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_ingredients_embedding ON ingredients 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_recipes_embedding ON recipes 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
            """)
            return False
        raise


async def main(table: str, batch_size: int, force: bool) -> None:
    """Main entry point."""
    print("🚀 Embedding Generation Script")
    print(f"   Model: {EMBEDDING_MODEL}")
    print(f"   Batch size: {batch_size}")
    print(f"   Force regenerate: {force}")
    print()
    
    if table == "ingredients" or table == "all":
        await generate_ingredient_embeddings(batch_size, force)
    
    if table == "recipes" or table == "all":
        await generate_recipe_embeddings(batch_size, force)
    
    print("\n✨ Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate embeddings for semantic search")
    parser.add_argument(
        "--table", 
        choices=["ingredients", "recipes", "all"],
        default="all",
        help="Which table to generate embeddings for"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of items to embed per batch"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate embeddings even if they already exist"
    )
    
    args = parser.parse_args()
    asyncio.run(main(args.table, args.batch_size, args.force))

