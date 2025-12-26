"""
Tests for schema module.
"""

import pytest
from alfred.tools.schema import (
    SUBDOMAIN_REGISTRY,
    get_subdomain_tables,
    get_complexity_rules,
    FALLBACK_SCHEMAS,
    FIELD_ENUMS,
)


class TestSubdomainRegistry:
    """Tests for SUBDOMAIN_REGISTRY structure and helpers."""
    
    def test_all_subdomains_have_tables(self):
        """Every subdomain should have a tables list."""
        for subdomain, config in SUBDOMAIN_REGISTRY.items():
            tables = get_subdomain_tables(subdomain)
            assert isinstance(tables, list), f"{subdomain} should have a tables list"
            assert len(tables) > 0, f"{subdomain} should have at least one table"
    
    def test_get_subdomain_tables_inventory(self):
        """Inventory subdomain should have inventory and ingredients tables."""
        tables = get_subdomain_tables("inventory")
        assert "inventory" in tables
        assert "ingredients" in tables
    
    def test_get_subdomain_tables_recipes(self):
        """Recipes subdomain should have recipes, recipe_ingredients, and ingredients."""
        tables = get_subdomain_tables("recipes")
        assert "recipes" in tables
        assert "recipe_ingredients" in tables
        assert "ingredients" in tables
    
    def test_get_subdomain_tables_meal_plan(self):
        """Meal plan subdomain should include meal_plans and recipes."""
        tables = get_subdomain_tables("meal_plan")
        assert "meal_plans" in tables
        assert "recipes" in tables
    
    def test_get_subdomain_tables_tasks(self):
        """Tasks subdomain should exist and include tasks table."""
        tables = get_subdomain_tables("tasks")
        assert "tasks" in tables
    
    def test_get_subdomain_tables_unknown(self):
        """Unknown subdomain should return empty list."""
        tables = get_subdomain_tables("nonexistent")
        assert tables == []
    
    def test_recipes_has_high_mutation_complexity(self):
        """Recipes subdomain should escalate to high complexity for mutations."""
        rules = get_complexity_rules("recipes")
        assert rules is not None
        assert rules.get("mutation") == "high"
    
    def test_meal_plan_has_medium_mutation_complexity(self):
        """Meal plan subdomain should escalate to medium complexity for mutations."""
        rules = get_complexity_rules("meal_plan")
        assert rules is not None
        assert rules.get("mutation") == "medium"
    
    def test_inventory_has_no_complexity_rules(self):
        """Inventory subdomain should not have complexity rules."""
        rules = get_complexity_rules("inventory")
        assert rules is None
    
    def test_history_subdomain_exists(self):
        """History subdomain should exist with cooking_log table."""
        tables = get_subdomain_tables("history")
        assert "cooking_log" in tables


class TestFallbackSchemas:
    """Tests for FALLBACK_SCHEMAS completeness."""
    
    def test_all_subdomains_have_fallback_schema(self):
        """Every subdomain should have a fallback schema."""
        for subdomain in SUBDOMAIN_REGISTRY:
            assert subdomain in FALLBACK_SCHEMAS, f"Missing fallback schema for {subdomain}"
            assert len(FALLBACK_SCHEMAS[subdomain]) > 100, f"Schema for {subdomain} seems too short"
    
    def test_recipes_schema_mentions_parent_recipe_id(self):
        """Recipes schema should document parent_recipe_id for variations."""
        schema = FALLBACK_SCHEMAS["recipes"]
        assert "parent_recipe_id" in schema
    
    def test_meal_plan_schema_mentions_other(self):
        """Meal plan schema should mention 'other' as a meal_type option for experiments/stocks."""
        schema = FALLBACK_SCHEMAS["meal_plan"]
        assert "other" in schema
    
    def test_tasks_schema_exists(self):
        """Tasks schema should exist as its own subdomain."""
        assert "tasks" in FALLBACK_SCHEMAS
        schema = FALLBACK_SCHEMAS["tasks"]
        assert "title" in schema
        assert "due_date" in schema
        assert "category" in schema
    
    def test_preferences_schema_has_expanded_fields(self):
        """Preferences schema should have expanded fields."""
        schema = FALLBACK_SCHEMAS["preferences"]
        assert "nutrition_goals" in schema
        assert "available_equipment" in schema
        assert "time_budget_minutes" in schema
    
    def test_preferences_schema_includes_flavor_preferences(self):
        """Preferences schema should include flavor_preferences table."""
        schema = FALLBACK_SCHEMAS["preferences"]
        assert "flavor_preferences" in schema


class TestFieldEnums:
    """Tests for FIELD_ENUMS values."""
    
    def test_meal_type_includes_other(self):
        """Meal type enum should include 'other' for experiments/stocks."""
        meal_types = FIELD_ENUMS.get("meal_plan", {}).get("meal_type", [])
        assert "other" in meal_types
    
    def test_task_category_values(self):
        """Task categories should be defined."""
        categories = FIELD_ENUMS.get("tasks", {}).get("category", [])
        assert "prep" in categories
        assert "shopping" in categories
    
    def test_cooking_frequency_values(self):
        """Preferences should have cooking_frequency values."""
        frequencies = FIELD_ENUMS.get("preferences", {}).get("cooking_frequency", [])
        assert "daily" in frequencies
        assert "weekends-only" in frequencies

