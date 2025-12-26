"""
Tests for profile builder functionality.
"""

import pytest
from alfred.background.profile_builder import (
    UserProfile,
    format_profile_for_prompt,
)


class TestUserProfile:
    """Tests for UserProfile dataclass."""
    
    def test_default_values(self):
        """UserProfile should have sensible defaults."""
        profile = UserProfile()
        assert profile.household_size == 1
        assert profile.cooking_skill_level == "intermediate"
        assert profile.time_budget_minutes == 30
        assert profile.dietary_restrictions == []
        assert profile.allergies == []
    
    def test_custom_values(self):
        """UserProfile should accept custom values."""
        profile = UserProfile(
            household_size=4,
            dietary_restrictions=["vegetarian", "gluten-free"],
            allergies=["peanuts"],
            cooking_skill_level="advanced",
            available_equipment=["instant-pot", "sous-vide"],
        )
        assert profile.household_size == 4
        assert "vegetarian" in profile.dietary_restrictions
        assert "peanuts" in profile.allergies
        assert profile.cooking_skill_level == "advanced"


class TestFormatProfileForPrompt:
    """Tests for profile prompt formatting."""
    
    def test_empty_profile_returns_minimal_output(self):
        """Empty profile should return minimal or empty output."""
        profile = UserProfile()
        result = format_profile_for_prompt(profile)
        # Should at least have the header or be empty
        assert result == "" or result.startswith("## USER PROFILE")
    
    def test_includes_household_size(self):
        """Profile with household > 1 should include it."""
        profile = UserProfile(household_size=4)
        result = format_profile_for_prompt(profile)
        assert "Household: 4" in result
    
    def test_includes_dietary_restrictions(self):
        """Profile with diet restrictions should include them."""
        profile = UserProfile(dietary_restrictions=["vegetarian", "low-sodium"])
        result = format_profile_for_prompt(profile)
        assert "Diet:" in result
        assert "vegetarian" in result
    
    def test_includes_allergies(self):
        """Profile with allergies should include them."""
        profile = UserProfile(allergies=["peanuts", "shellfish"])
        result = format_profile_for_prompt(profile)
        assert "Allergies:" in result
        assert "peanuts" in result
    
    def test_includes_equipment(self):
        """Profile with equipment should include it."""
        profile = UserProfile(available_equipment=["instant-pot", "air-fryer"])
        result = format_profile_for_prompt(profile)
        assert "Equipment:" in result
        assert "instant-pot" in result
    
    def test_includes_time_budget_if_not_default(self):
        """Profile with non-default time budget should include it."""
        profile = UserProfile(time_budget_minutes=45)
        result = format_profile_for_prompt(profile)
        assert "Time: 45" in result
    
    def test_does_not_include_default_time_budget(self):
        """Default time budget (30 min) should not be explicitly shown."""
        profile = UserProfile(time_budget_minutes=30)
        result = format_profile_for_prompt(profile)
        assert "Time: 30" not in result
    
    def test_includes_nutrition_goals(self):
        """Profile with nutrition goals should include them."""
        profile = UserProfile(nutrition_goals=["high-protein", "low-carb"])
        result = format_profile_for_prompt(profile)
        assert "Goals:" in result
        assert "high-protein" in result
    
    def test_includes_top_ingredients(self):
        """Profile with top ingredients should include them."""
        profile = UserProfile(top_ingredients=["garlic", "onion", "olive oil"])
        result = format_profile_for_prompt(profile)
        assert "Frequently used:" in result
        assert "garlic" in result
    
    def test_includes_recent_meals(self):
        """Profile with recent meals should include them."""
        profile = UserProfile(recent_meals=[
            {"name": "Butter Chicken", "date": "2024-12-25", "rating": 5},
            {"name": "Pasta", "date": "2024-12-24", "rating": None},
        ])
        result = format_profile_for_prompt(profile)
        assert "Recent:" in result
        assert "Butter Chicken" in result
        assert "★5" in result
    
    def test_full_profile(self):
        """Full profile should format nicely."""
        profile = UserProfile(
            household_size=2,
            dietary_restrictions=["vegetarian"],
            allergies=["peanuts"],
            cooking_skill_level="intermediate",
            favorite_cuisines=["italian", "indian"],
            available_equipment=["instant-pot"],
            time_budget_minutes=30,
            nutrition_goals=["high-protein"],
            top_ingredients=["garlic", "tomatoes"],
            recent_meals=[{"name": "Tikka Masala", "date": "2024-12-25", "rating": 5}],
        )
        result = format_profile_for_prompt(profile)
        
        assert "## USER PROFILE" in result
        assert "Household: 2" in result
        assert "vegetarian" in result
        assert "peanuts" in result
        assert "italian" in result or "indian" in result
        assert "high-protein" in result

