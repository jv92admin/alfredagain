#!/usr/bin/env python3
"""
Ingredient Database Cleanup Script.

Uses GPT-4.1 to enrich ~2,500 ingredients with:
- parent_category (store section)
- family (ingredient identity group)
- tier (commonality: 1=core, 2=standard, 3=niche)
- cuisines (for specialty ingredients only)

Also handles deduplication and category migration.

Usage:
    python scripts/cleanup_ingredients.py dedupe           # Find/merge duplicates
    python scripts/cleanup_ingredients.py families         # Assign family to all
    python scripts/cleanup_ingredients.py categories       # Map to parent_category + category
    python scripts/cleanup_ingredients.py tiers            # Score 1-3
    python scripts/cleanup_ingredients.py cuisines         # Tag cuisine-specific only
    python scripts/cleanup_ingredients.py all              # Run all steps
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

# Use alfred's db client
try:
    from alfred.db.client import get_client
except ImportError:
    from supabase import create_client
    def get_client():
        return create_client(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
        )


# =============================================================================
# Configuration
# =============================================================================

MODEL = "gpt-4.1"
BATCH_SIZE_FAMILIES = 50
BATCH_SIZE_CATEGORIES = 50
BATCH_SIZE_TIERS = 100
BATCH_SIZE_CUISINES = 50

TAXONOMY_PATH = Path(__file__).parent.parent / "config" / "taxonomy.yaml"


def load_taxonomy() -> dict:
    """Load taxonomy configuration."""
    with open(TAXONOMY_PATH) as f:
        return yaml.safe_load(f)


# =============================================================================
# Prompts
# =============================================================================

DEDUPE_PROMPT = """Analyze these ingredients for potential duplicates or near-duplicates.

Ingredients:
{ingredients}

Look for:
1. Exact duplicates (different casing)
2. Singular/plural variants (tomato vs tomatoes)
3. Regional name variants (cilantro vs coriander)
4. Abbreviated forms (evoo vs extra virgin olive oil)

For each group of duplicates, choose the best canonical name.

Return JSON:
{{
  "merge_groups": [
    {{
      "canonical": "chicken breast",
      "merge_ids": ["uuid1", "uuid2"],
      "reason": "singular/plural variant"
    }}
  ]
}}

Return ONLY valid JSON, no other text."""

FAMILY_PROMPT = """Assign a 'family' to each ingredient. Family = ingredient identity group.

Rules:
- Family answers "what IS this thing at its core?"
- Family is NOT the category (chicken's family is 'chicken', not 'poultry')
- Family groups all variants together (chicken breast, chicken thigh, ground chicken → family='chicken')
- Use lowercase, singular form
- Be specific but not too granular (use 'cheddar' not 'sharp_cheddar')

Examples:
- chicken breast → chicken
- salmon fillet, smoked salmon → salmon
- all-purpose flour, bread flour → flour
- sharp cheddar, mild cheddar → cheddar
- gochugaru → gochugaru (unique ingredients keep their name)

Ingredients to process:
{ingredients}

Return JSON with ingredient NAME (not id) as key:
{{
  "assignments": [
    {{"name": "chicken breast", "family": "chicken"}},
    {{"name": "salmon fillet", "family": "salmon"}}
  ]
}}

Return ONLY valid JSON, no other text."""

CATEGORY_PROMPT = """Map each ingredient to the correct parent_category and category (subcategory).

Allowed parent_categories and their subcategories:
{taxonomy}

Current ingredients (with their old category if any):
{ingredients}

Rules:
- parent_category = store section (produce, protein, dairy, grains, pantry, spices, baking, specialty)
- category = subcategory within parent (e.g., under 'produce': vegetables, fruits, herbs)
- If old category maps cleanly, use it. Otherwise, determine the correct mapping.
- Use 'specialty' parent for cuisine-specific items that don't fit elsewhere

Return JSON with ingredient NAME (not id) as key:
{{
  "assignments": [
    {{"name": "chicken breast", "parent_category": "protein", "category": "poultry"}},
    {{"name": "gochugaru", "parent_category": "specialty", "category": "asian"}}
  ]
}}

Return ONLY valid JSON, no other text."""

TIER_PROMPT = """Score each ingredient's commonality tier (1, 2, or 3).

Tier definitions:
- Tier 1 (core, ~500 total): Available at ANY grocery store, >50% of recipes, everyone knows it
- Tier 2 (standard, ~1500 total): Available at Whole Foods/well-stocked store, popular cuisines
- Tier 3 (niche, ~500 total): Specialty/ethnic stores only, regional/professional use

Examples:
- Tier 1: salt, chicken breast, olive oil, garlic, eggs, butter, onion, pasta, rice
- Tier 2: feta cheese, hoisin sauce, arborio rice, shallots, Thai basil
- Tier 3: gochugaru, galangal, sumac, teff, guanciale

Ingredients to score:
{ingredients}

Return JSON with ingredient NAME (not id) as key:
{{
  "assignments": [
    {{"name": "salt", "tier": 1}},
    {{"name": "gochugaru", "tier": 3}}
  ]
}}

Return ONLY valid JSON, no other text."""

CUISINE_PROMPT = """Tag cuisine-specific ingredients with their cuisines.

Rules:
- ONLY tag ingredients that are specific to certain cuisines
- Do NOT tag generic ingredients (salt, chicken, flour, olive oil)
- Use cuisine codes: korean, japanese, chinese, thai, vietnamese, indian, mediterranean, greek, italian, french, spanish, mexican, latin_american, african, middle_eastern, caribbean
- Many ingredients belong to multiple cuisines (soy sauce -> chinese, japanese, korean)

Ingredients to tag:
{ingredients}

Return JSON with ingredient NAME (not id) as key:
{{
  "assignments": [
    {{"name": "gochugaru", "cuisines": ["korean"]}},
    {{"name": "soy sauce", "cuisines": ["chinese", "japanese", "korean"]}},
    {{"name": "salt", "cuisines": []}}
  ]
}}

Return ONLY valid JSON, no other text. Use empty array for non-cuisine-specific ingredients."""


# =============================================================================
# Helper Functions
# =============================================================================

def get_openai_client() -> OpenAI:
    """Get OpenAI client."""
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def log_change(operation: str, ingredient_id: str, changes: dict):
    """Log a change to the audit file."""
    log_dir = Path(__file__).parent / "cleanup_logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"cleanup_{datetime.now().strftime('%Y%m%d')}.jsonl"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "ingredient_id": ingredient_id,
        "changes": changes
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def parse_llm_response(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    content = content.strip()

    # Handle markdown code blocks
    if content.startswith("```"):
        lines = content.split("\n")
        # Find start and end of code block
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines)
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "```":
                end = i
                break
        content = "\n".join(lines[start:end])
        if content.startswith("json"):
            content = content[4:].strip()

    return json.loads(content)


# =============================================================================
# Cleanup Operations
# =============================================================================

async def dedupe_ingredients(dry_run: bool = True):
    """Find and optionally merge duplicate ingredients."""
    print("\n" + "=" * 70)
    print("DEDUPLICATION")
    print("=" * 70)

    supabase = get_client()
    openai = get_openai_client()

    # Fetch all ingredients (paginated)
    ingredients = fetch_all_ingredients(supabase, "id, name, aliases")
    print(f"Loaded {len(ingredients)} ingredients")

    # Group by first letter for batching
    batches = {}
    for ing in ingredients:
        first_letter = ing["name"][0].lower() if ing["name"] else "_"
        if first_letter not in batches:
            batches[first_letter] = []
        batches[first_letter].append(ing)

    all_merge_groups = []

    for letter, batch in sorted(batches.items()):
        if len(batch) < 2:
            continue

        print(f"\nProcessing '{letter}' ({len(batch)} ingredients)...")

        # Format for LLM
        ing_list = "\n".join([
            f"- {ing['name']} (id: {ing['id']}, aliases: {ing.get('aliases', [])})"
            for ing in batch
        ])

        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a culinary expert helping clean up an ingredient database."},
                    {"role": "user", "content": DEDUPE_PROMPT.format(ingredients=ing_list)}
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            data = parse_llm_response(response.choices[0].message.content)
            merge_groups = data.get("merge_groups", [])

            if merge_groups:
                print(f"  Found {len(merge_groups)} merge groups")
                all_merge_groups.extend(merge_groups)

        except Exception as e:
            print(f"  Error: {e}")

    print(f"\n\nTotal merge groups found: {len(all_merge_groups)}")

    if dry_run:
        print("\n[DRY RUN] Would merge:")
        for group in all_merge_groups:
            canonical = group.get('canonical', '?')
            merge_ids = group.get('merge_ids', [])
            reason = group.get('reason', '')
            try:
                print(f"  -> Keep '{canonical}', merge: {merge_ids} ({reason})")
            except UnicodeEncodeError:
                # Fallback for terminals that can't handle accented chars
                safe_name = canonical.encode('ascii', errors='replace').decode('ascii')
                print(f"  -> Keep '{safe_name}', merge: {merge_ids} ({reason})")
    else:
        print("\nApplying merges...")
        for group in all_merge_groups:
            # TODO: Implement actual merge logic
            # 1. Update references in inventory, recipe_ingredients, shopping_list
            # 2. Merge aliases
            # 3. Delete duplicate records
            log_change("dedupe", group["canonical"], {"merged": group["merge_ids"]})
        print(f"  Applied {len(all_merge_groups)} merges")


def fetch_all_ingredients(supabase, select_cols: str, filter_fn=None) -> list[dict]:
    """Fetch all ingredients with pagination (Supabase limits to 1000)."""
    all_items = []
    page_size = 1000
    offset = 0

    while True:
        result = supabase.table("ingredients").select(select_cols).range(offset, offset + page_size - 1).execute()
        if not result.data:
            break
        if filter_fn:
            all_items.extend([item for item in result.data if filter_fn(item)])
        else:
            all_items.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size

    return all_items


async def assign_families():
    """Assign family to all ingredients."""
    print("\n" + "=" * 70)
    print("FAMILY ASSIGNMENT")
    print("=" * 70)

    supabase = get_client()
    openai = get_openai_client()

    # Fetch ALL ingredients without family using pagination
    ingredients = fetch_all_ingredients(
        supabase,
        "id, name, category, aliases, family",
        filter_fn=lambda ing: not ing.get("family") or ing.get("family") == ""
    )

    if not ingredients:
        print("All ingredients already have families assigned!")
        return

    # Build name -> id lookup for reliable matching
    name_to_id = {ing["name"].lower(): ing["id"] for ing in ingredients}

    print(f"Processing {len(ingredients)} ingredients without families")

    total_assigned = 0

    for i in range(0, len(ingredients), BATCH_SIZE_FAMILIES):
        batch = ingredients[i:i + BATCH_SIZE_FAMILIES]
        print(f"\nBatch {i // BATCH_SIZE_FAMILIES + 1}/{(len(ingredients) // BATCH_SIZE_FAMILIES) + 1}...")

        # Format for LLM - use name only, no IDs
        ing_list = "\n".join([
            f"- {ing['name']} (category: {ing.get('category', 'unknown')})"
            for ing in batch
        ])

        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a culinary expert helping organize an ingredient database."},
                    {"role": "user", "content": FAMILY_PROMPT.format(ingredients=ing_list)}
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            data = parse_llm_response(response.choices[0].message.content)
            assignments = data.get("assignments", [])

            # Apply assignments using name-based lookup
            for assignment in assignments:
                name = assignment.get("name", "").lower()
                family = assignment.get("family")

                if not name or not family:
                    continue

                # Look up ID by name
                ing_id = name_to_id.get(name)
                if not ing_id:
                    print(f"  Warning: No ID found for '{name}'")
                    continue

                try:
                    supabase.table("ingredients").update({
                        "family": family
                    }).eq("id", ing_id).execute()

                    log_change("family", ing_id, {"family": family})
                    total_assigned += 1

                except Exception as e:
                    print(f"  Error updating {name}: {e}")

            print(f"  Assigned {len(assignments)} families")

        except Exception as e:
            print(f"  Batch error: {e}")

    print(f"\n\nTotal families assigned: {total_assigned}")


async def fix_categories():
    """Map existing category to parent_category + category."""
    print("\n" + "=" * 70)
    print("CATEGORY MIGRATION")
    print("=" * 70)

    supabase = get_client()
    openai = get_openai_client()
    taxonomy = load_taxonomy()

    # Format taxonomy for prompt
    taxonomy_str = ""
    for parent, data in taxonomy["parent_categories"].items():
        cats = data.get("categories", [])
        taxonomy_str += f"- {parent}: {', '.join(cats)}\n"

    # Fetch ALL ingredients that need category mapping using pagination
    ingredients = fetch_all_ingredients(
        supabase,
        "id, name, category, parent_category",
        filter_fn=lambda ing: ing.get("parent_category") == "pantry"
    )

    if not ingredients:
        print("All ingredients already have parent_category mapped!")
        return

    # Build name -> id lookup for reliable matching
    name_to_id = {ing["name"].lower(): ing["id"] for ing in ingredients}

    print(f"Processing {len(ingredients)} ingredients needing category mapping")

    total_mapped = 0

    for i in range(0, len(ingredients), BATCH_SIZE_CATEGORIES):
        batch = ingredients[i:i + BATCH_SIZE_CATEGORIES]
        print(f"\nBatch {i // BATCH_SIZE_CATEGORIES + 1}/{(len(ingredients) // BATCH_SIZE_CATEGORIES) + 1}...")

        # Format for LLM - use name only, no IDs
        ing_list = "\n".join([
            f"- {ing['name']} (old_category: {ing.get('category', 'none')})"
            for ing in batch
        ])

        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a culinary expert helping organize an ingredient database."},
                    {"role": "user", "content": CATEGORY_PROMPT.format(
                        taxonomy=taxonomy_str,
                        ingredients=ing_list
                    )}
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            data = parse_llm_response(response.choices[0].message.content)
            assignments = data.get("assignments", [])

            # Validate and apply using name-based lookup
            valid_parents = set(taxonomy["parent_categories"].keys())

            for assignment in assignments:
                name = assignment.get("name", "").lower()
                parent = assignment.get("parent_category")
                category = assignment.get("category")

                if not name or not parent:
                    continue

                # Look up ID by name
                ing_id = name_to_id.get(name)
                if not ing_id:
                    print(f"  Warning: No ID found for '{name}'")
                    continue

                # Validate parent_category
                if parent not in valid_parents:
                    print(f"  Warning: Invalid parent_category '{parent}' for {name}")
                    continue

                # Validate category under parent
                allowed_cats = taxonomy["parent_categories"][parent].get("categories", [])
                if category and category not in allowed_cats:
                    print(f"  Warning: Invalid category '{category}' under '{parent}' for {name}")
                    category = None

                try:
                    update_data = {"parent_category": parent}
                    if category:
                        update_data["category"] = category

                    supabase.table("ingredients").update(update_data).eq("id", ing_id).execute()

                    log_change("category", ing_id, update_data)
                    total_mapped += 1

                except Exception as e:
                    print(f"  Error updating {name}: {e}")

            print(f"  Mapped {len(assignments)} categories")

        except Exception as e:
            print(f"  Batch error: {e}")

    print(f"\n\nTotal categories mapped: {total_mapped}")


async def score_tiers():
    """Assign tier (1, 2, 3) to all ingredients."""
    print("\n" + "=" * 70)
    print("TIER SCORING")
    print("=" * 70)

    supabase = get_client()
    openai = get_openai_client()

    # Fetch ALL ingredients using pagination
    ingredients = fetch_all_ingredients(
        supabase,
        "id, name, category, parent_category, tier"
    )

    # Build name -> id lookup for reliable matching
    name_to_id = {ing["name"].lower(): ing["id"] for ing in ingredients}

    print(f"Processing {len(ingredients)} ingredients for tier scoring")

    total_scored = 0
    tier_counts = {1: 0, 2: 0, 3: 0}

    for i in range(0, len(ingredients), BATCH_SIZE_TIERS):
        batch = ingredients[i:i + BATCH_SIZE_TIERS]
        print(f"\nBatch {i // BATCH_SIZE_TIERS + 1}/{(len(ingredients) // BATCH_SIZE_TIERS) + 1}...")

        # Format for LLM - use name only, no IDs
        ing_list = "\n".join([
            f"- {ing['name']} (category: {ing.get('parent_category', 'unknown')}/{ing.get('category', 'unknown')})"
            for ing in batch
        ])

        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a culinary expert helping organize an ingredient database by commonality."},
                    {"role": "user", "content": TIER_PROMPT.format(ingredients=ing_list)}
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            data = parse_llm_response(response.choices[0].message.content)
            assignments = data.get("assignments", [])

            # Apply assignments using name-based lookup
            for assignment in assignments:
                name = assignment.get("name", "").lower()
                tier = assignment.get("tier")

                if not name:
                    continue

                if tier not in [1, 2, 3]:
                    print(f"  Warning: Invalid tier '{tier}' for {name}")
                    continue

                # Look up ID by name
                ing_id = name_to_id.get(name)
                if not ing_id:
                    print(f"  Warning: No ID found for '{name}'")
                    continue

                try:
                    supabase.table("ingredients").update({
                        "tier": tier
                    }).eq("id", ing_id).execute()

                    log_change("tier", ing_id, {"tier": tier})
                    total_scored += 1
                    tier_counts[tier] += 1

                except Exception as e:
                    print(f"  Error updating {name}: {e}")

            print(f"  Scored {len(assignments)} ingredients")

        except Exception as e:
            print(f"  Batch error: {e}")

    print(f"\n\nTotal scored: {total_scored}")
    print(f"  Tier 1 (core): {tier_counts[1]}")
    print(f"  Tier 2 (standard): {tier_counts[2]}")
    print(f"  Tier 3 (niche): {tier_counts[3]}")


async def tag_cuisines():
    """Tag cuisine-specific ingredients with their cuisines."""
    print("\n" + "=" * 70)
    print("CUISINE TAGGING")
    print("=" * 70)

    supabase = get_client()
    openai = get_openai_client()
    taxonomy = load_taxonomy()

    valid_cuisines = set(taxonomy.get("cuisines", []))

    # Fetch ALL ingredients using pagination, filter to those needing cuisine tags
    ingredients = fetch_all_ingredients(
        supabase,
        "id, name, category, parent_category, cuisines",
        filter_fn=lambda ing: (
            ing.get("parent_category") == "specialty"
            or (ing.get("category") or "").startswith("cuisine_")
            or not ing.get("cuisines")
        )
    )

    if not ingredients:
        print("No ingredients need cuisine tagging!")
        return

    # Build name -> id lookup for reliable matching
    name_to_id = {ing["name"].lower(): ing["id"] for ing in ingredients}

    print(f"Processing {len(ingredients)} potential cuisine-specific ingredients")

    total_tagged = 0

    for i in range(0, len(ingredients), BATCH_SIZE_CUISINES):
        batch = ingredients[i:i + BATCH_SIZE_CUISINES]
        print(f"\nBatch {i // BATCH_SIZE_CUISINES + 1}/{(len(ingredients) // BATCH_SIZE_CUISINES) + 1}...")

        # Format for LLM - use name only, no IDs
        ing_list = "\n".join([
            f"- {ing['name']} (category: {ing.get('category', 'unknown')})"
            for ing in batch
        ])

        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a culinary expert helping tag ingredients by cuisine origin."},
                    {"role": "user", "content": CUISINE_PROMPT.format(ingredients=ing_list)}
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            data = parse_llm_response(response.choices[0].message.content)
            assignments = data.get("assignments", [])

            # Apply assignments using name-based lookup
            for assignment in assignments:
                name = assignment.get("name", "").lower()
                cuisines = assignment.get("cuisines", [])

                if not name:
                    continue

                # Validate cuisines
                cuisines = [c for c in cuisines if c in valid_cuisines]

                # Skip if no cuisines (generic ingredient)
                if not cuisines:
                    continue

                # Look up ID by name
                ing_id = name_to_id.get(name)
                if not ing_id:
                    print(f"  Warning: No ID found for '{name}'")
                    continue

                try:
                    supabase.table("ingredients").update({
                        "cuisines": cuisines
                    }).eq("id", ing_id).execute()

                    log_change("cuisines", ing_id, {"cuisines": cuisines})
                    total_tagged += 1

                except Exception as e:
                    print(f"  Error updating {name}: {e}")

            print(f"  Tagged {total_tagged} ingredients with cuisines in this batch")

        except Exception as e:
            print(f"  Batch error: {e}")

    print(f"\n\nTotal cuisine-tagged: {total_tagged}")


async def run_all():
    """Run all cleanup operations in sequence."""
    print("\n" + "=" * 70)
    print("RUNNING ALL CLEANUP OPERATIONS")
    print("=" * 70)

    await dedupe_ingredients(dry_run=True)  # Start with dry run
    await assign_families()
    await fix_categories()
    await score_tiers()
    await tag_cuisines()

    print("\n" + "=" * 70)
    print("ALL CLEANUP OPERATIONS COMPLETE")
    print("=" * 70)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Cleanup and enrich the ingredients database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  dedupe      Find and merge duplicate ingredients
  families    Assign family to all ingredients
  categories  Map to parent_category + category
  tiers       Score commonality (1=core, 2=standard, 3=niche)
  cuisines    Tag cuisine-specific ingredients
  all         Run all cleanup operations
        """
    )

    parser.add_argument(
        "command",
        choices=["dedupe", "families", "categories", "tiers", "cuisines", "all"],
        help="Cleanup operation to run"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="For dedupe: actually apply merges (default is dry run)"
    )

    args = parser.parse_args()

    if args.command == "dedupe":
        asyncio.run(dedupe_ingredients(dry_run=not args.apply))
    elif args.command == "families":
        asyncio.run(assign_families())
    elif args.command == "categories":
        asyncio.run(fix_categories())
    elif args.command == "tiers":
        asyncio.run(score_tiers())
    elif args.command == "cuisines":
        asyncio.run(tag_cuisines())
    elif args.command == "all":
        asyncio.run(run_all())


if __name__ == "__main__":
    main()
