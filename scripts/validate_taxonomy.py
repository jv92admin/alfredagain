#!/usr/bin/env python3
"""
Ingredient Taxonomy Validation Script.

Validates all ingredients against taxonomy rules:
- parent_category is in allowed enum
- category is allowed under its parent_category
- family is not empty
- tier is 1, 2, or 3
- cuisines only contains valid cuisine codes

Usage:
    python scripts/validate_taxonomy.py           # Validate all
    python scripts/validate_taxonomy.py --fix     # Attempt auto-fixes for simple issues
    python scripts/validate_taxonomy.py --summary # Show summary only

Exit codes:
    0 - All validations passed
    1 - Validation errors found
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

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


TAXONOMY_PATH = Path(__file__).parent.parent / "config" / "taxonomy.yaml"


def load_taxonomy() -> dict:
    """Load taxonomy configuration."""
    if not TAXONOMY_PATH.exists():
        print(f"ERROR: Taxonomy file not found at {TAXONOMY_PATH}")
        sys.exit(1)

    with open(TAXONOMY_PATH) as f:
        return yaml.safe_load(f)


def validate_ingredients(summary_only: bool = False) -> tuple[list, list]:
    """
    Validate all ingredients against taxonomy rules.

    Returns:
        Tuple of (errors, warnings)
    """
    supabase = get_client()
    taxonomy = load_taxonomy()

    # Extract valid values from taxonomy
    valid_parents = set(taxonomy["parent_categories"].keys())
    valid_tiers = {1, 2, 3}
    valid_cuisines = set(taxonomy.get("cuisines", []))

    # Build parent -> categories mapping
    parent_to_categories = {}
    for parent, data in taxonomy["parent_categories"].items():
        parent_to_categories[parent] = set(data.get("categories", []))

    # Fetch all ingredients
    result = supabase.table("ingredients").select(
        "id, name, parent_category, category, family, tier, cuisines"
    ).execute()

    ingredients = result.data
    print(f"Validating {len(ingredients)} ingredients...\n")

    errors = []
    warnings = []

    for ing in ingredients:
        ing_id = ing["id"]
        name = ing["name"]

        # Check parent_category
        parent = ing.get("parent_category")
        if not parent:
            errors.append(f"[{name}] Missing parent_category")
        elif parent not in valid_parents:
            errors.append(f"[{name}] Invalid parent_category: '{parent}' (allowed: {sorted(valid_parents)})")

        # Check category under parent
        category = ing.get("category")
        if category and parent and parent in parent_to_categories:
            allowed_cats = parent_to_categories[parent]
            if category not in allowed_cats:
                # Could be old category format, warning not error
                warnings.append(f"[{name}] Category '{category}' not in allowed list for '{parent}': {sorted(allowed_cats)}")

        # Check family
        family = ing.get("family")
        if not family or family.strip() == "":
            errors.append(f"[{name}] Missing or empty family")

        # Check tier
        tier = ing.get("tier")
        if tier is None:
            warnings.append(f"[{name}] Missing tier (will default to 2)")
        elif tier not in valid_tiers:
            errors.append(f"[{name}] Invalid tier: {tier} (allowed: 1, 2, 3)")

        # Check cuisines
        cuisines = ing.get("cuisines") or []
        if cuisines:
            invalid_cuisines = [c for c in cuisines if c not in valid_cuisines]
            if invalid_cuisines:
                warnings.append(f"[{name}] Invalid cuisines: {invalid_cuisines}")

    return errors, warnings


def print_results(errors: list, warnings: list, summary_only: bool = False):
    """Print validation results."""

    if not summary_only:
        if errors:
            print("=" * 70)
            print("ERRORS (must fix)")
            print("=" * 70)
            for err in errors[:50]:  # Limit output
                print(f"  - {err}")
            if len(errors) > 50:
                print(f"  ... and {len(errors) - 50} more errors")
            print()

        if warnings:
            print("=" * 70)
            print("WARNINGS (should review)")
            print("=" * 70)
            for warn in warnings[:50]:  # Limit output
                print(f"  - {warn}")
            if len(warnings) > 50:
                print(f"  ... and {len(warnings) - 50} more warnings")
            print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Errors:   {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print()

    if errors:
        print("STATUS: FAILED - Fix errors before proceeding")
        return 1
    elif warnings:
        print("STATUS: PASSED with warnings")
        return 0
    else:
        print("STATUS: PASSED - All validations passed!")
        return 0


def attempt_fixes():
    """Attempt to auto-fix simple validation issues."""
    supabase = get_client()
    taxonomy = load_taxonomy()

    # Build old category -> (parent, new_category) mapping
    # This handles common migrations like "vegetables" -> ("produce", "vegetables")
    category_migration = {
        # Old category mappings
        "vegetables": ("produce", "vegetables"),
        "fruits": ("produce", "fruits"),
        "herbs": ("produce", "herbs"),
        "poultry": ("protein", "poultry"),
        "beef": ("protein", "beef"),
        "pork": ("protein", "pork"),
        "lamb": ("protein", "lamb"),
        "seafood": ("protein", "seafood"),
        "fish": ("protein", "seafood"),
        "shellfish": ("protein", "seafood"),
        "eggs": ("protein", "eggs"),
        "dairy": ("dairy", "milk"),
        "cheese": ("dairy", "cheese"),
        "rice": ("grains", "rice"),
        "pasta": ("grains", "pasta"),
        "noodles": ("grains", "noodles"),
        "bread": ("grains", "bread"),
        "flour": ("grains", "flour"),
        "grains": ("grains", "whole_grains"),
        "legumes": ("pantry", "canned"),
        "nuts": ("pantry", "canned"),
        "seeds": ("pantry", "canned"),
        "oils": ("pantry", "oils"),
        "vinegars": ("pantry", "vinegars"),
        "condiments": ("pantry", "condiments"),
        "spices": ("spices", "ground"),
        "baking": ("baking", "sweeteners"),
    }

    # Also handle cuisine_ prefixed categories
    for cuisine in taxonomy.get("cuisines", []):
        category_migration[f"cuisine_{cuisine}"] = ("specialty", cuisine[:5] if len(cuisine) > 5 else cuisine)

    # Fetch ingredients with default parent_category
    result = supabase.table("ingredients").select("id, name, category, parent_category").execute()
    ingredients = [ing for ing in result.data if ing.get("parent_category") == "pantry"]

    fixed = 0
    for ing in ingredients:
        old_cat = ing.get("category", "").lower()
        if old_cat in category_migration:
            new_parent, new_cat = category_migration[old_cat]

            try:
                supabase.table("ingredients").update({
                    "parent_category": new_parent,
                    "category": new_cat
                }).eq("id", ing["id"]).execute()

                fixed += 1
                print(f"  Fixed: {ing['name']} -> {new_parent}/{new_cat}")

            except Exception as e:
                print(f"  Error fixing {ing['name']}: {e}")

    print(f"\nAuto-fixed {fixed} ingredients")


def main():
    parser = argparse.ArgumentParser(
        description="Validate ingredients against taxonomy rules"
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to auto-fix simple issues"
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary only, not individual errors"
    )

    args = parser.parse_args()

    if args.fix:
        print("Attempting auto-fixes...\n")
        attempt_fixes()
        print()

    errors, warnings = validate_ingredients(summary_only=args.summary)
    exit_code = print_results(errors, warnings, summary_only=args.summary)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
