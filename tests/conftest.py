"""
Pytest configuration and fixtures for Alfred V2 tests.
"""

import os
import pytest
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

# Set test environment before importing alfred modules
os.environ["ALFRED_ENV"] = "development"
os.environ["ALFRED_USE_ADVANCED_MODELS"] = "false"


@pytest.fixture
def mock_supabase():
    """Mock Supabase client for unit tests."""
    mock_client = MagicMock()
    
    # Mock table operations
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    
    mock_client.table.return_value = mock_table
    
    return mock_client


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for unit tests."""
    mock_client = MagicMock()
    
    # Mock chat completions
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content='{"action": "step_complete"}'))]
    mock_client.chat.completions.create.return_value = mock_completion
    
    return mock_client


@pytest.fixture
def sample_inventory_items():
    """Sample inventory items for testing."""
    return [
        {"id": "inv-1", "name": "milk", "quantity": 2, "unit": "gallons", "location": "fridge"},
        {"id": "inv-2", "name": "eggs", "quantity": 12, "unit": "count", "location": "fridge"},
        {"id": "inv-3", "name": "butter", "quantity": 1, "unit": "lb", "location": "fridge"},
        {"id": "inv-4", "name": "flour", "quantity": 5, "unit": "lb", "location": "pantry"},
        {"id": "inv-5", "name": "sugar", "quantity": 2, "unit": "lb", "location": "pantry"},
    ]


@pytest.fixture
def sample_recipe():
    """Sample recipe for testing."""
    return {
        "id": "recipe-1",
        "name": "Pancakes",
        "description": "Fluffy buttermilk pancakes",
        "cuisine": "american",
        "difficulty": "easy",
        "servings": 4,
        "prep_time_minutes": 10,
        "cook_time_minutes": 15,
        "instructions": [
            "Mix dry ingredients",
            "Whisk wet ingredients", 
            "Combine and let rest",
            "Cook on griddle",
        ],
        "tags": ["breakfast", "quick"],
    }


@pytest.fixture
def sample_recipe_ingredients():
    """Sample recipe ingredients for testing."""
    return [
        {"id": "ri-1", "recipe_id": "recipe-1", "name": "flour", "quantity": 2, "unit": "cups"},
        {"id": "ri-2", "recipe_id": "recipe-1", "name": "milk", "quantity": 1.5, "unit": "cups"},
        {"id": "ri-3", "recipe_id": "recipe-1", "name": "eggs", "quantity": 2, "unit": "count"},
        {"id": "ri-4", "recipe_id": "recipe-1", "name": "butter", "quantity": 2, "unit": "tbsp"},
        {"id": "ri-5", "recipe_id": "recipe-1", "name": "sugar", "quantity": 2, "unit": "tbsp"},
    ]


@pytest.fixture
def sample_user_preferences():
    """Sample user preferences for testing."""
    return {
        "id": "pref-1",
        "user_id": "user-1",
        "dietary_restrictions": ["vegetarian"],
        "allergies": ["peanuts"],
        "favorite_cuisines": ["italian", "mexican"],
        "cooking_skill_level": "intermediate",
        "household_size": 2,
        "available_equipment": ["instant-pot", "air-fryer"],
        "time_budget_minutes": 30,
        "nutrition_goals": ["high-protein"],
    }

