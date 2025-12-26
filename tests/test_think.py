"""
Tests for Think node complexity adjustment.
"""

import pytest
from alfred.graph.state import PlannedStep
from alfred.graph.nodes.think import adjust_step_complexity


class TestComplexityAdjustment:
    """Tests for automatic complexity escalation."""
    
    def test_recipe_creation_escalates_to_high(self):
        """Creating a recipe should escalate to high complexity."""
        step = PlannedStep(
            description="Create the new recipe with ingredients",
            step_type="crud",
            subdomain="recipes",
            complexity="low",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "high"
    
    def test_recipe_save_escalates_to_high(self):
        """Saving a recipe should escalate to high complexity."""
        step = PlannedStep(
            description="Save the generated recipe",
            step_type="crud",
            subdomain="recipes",
            complexity="medium",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "high"
    
    def test_recipe_read_does_not_escalate(self):
        """Reading recipes should not change complexity."""
        step = PlannedStep(
            description="Read all user recipes",  # Avoid "saved" which contains mutation verb
            step_type="crud",
            subdomain="recipes",
            complexity="low",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "low"
    
    def test_meal_plan_creation_escalates_to_medium(self):
        """Creating a meal plan should escalate to medium complexity."""
        step = PlannedStep(
            description="Add prep work to meal plan",
            step_type="crud",
            subdomain="meal_plan",
            complexity="low",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "medium"
    
    def test_inventory_does_not_escalate(self):
        """Inventory operations should not escalate."""
        step = PlannedStep(
            description="Add items to inventory",
            step_type="crud",
            subdomain="inventory",
            complexity="low",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "low"
    
    def test_already_high_stays_high(self):
        """If already high complexity, it should stay high."""
        step = PlannedStep(
            description="Generate complex recipe",
            step_type="generate",
            subdomain="recipes",
            complexity="high",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "high"
    
    def test_does_not_downgrade(self):
        """Escalation should not downgrade complexity."""
        step = PlannedStep(
            description="Read meal plans",
            step_type="crud",
            subdomain="meal_plan",
            complexity="high",  # Already high, shouldn't go down
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "high"
    
    def test_generate_step_with_mutation_verb(self):
        """Generate step with 'generate' in description should escalate."""
        step = PlannedStep(
            description="Generate a spicy version of the recipe",
            step_type="generate",
            subdomain="recipes",
            complexity="low",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "high"
    
    def test_analyze_step_does_not_escalate(self):
        """Analyze steps should not escalate (they're not mutations)."""
        step = PlannedStep(
            description="Compare recipe ingredients with inventory",
            step_type="analyze",
            subdomain="recipes",
            complexity="low",
        )
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "low"

