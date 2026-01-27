"""
Alfred V2 - Database Entity Models.

These models map to the Supabase tables defined in migrations/001_core_tables.sql.
They are used for:
- Type-safe database operations
- Structured LLM outputs via Instructor
- API request/response validation
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Core Entities
# =============================================================================


class User(BaseModel):
    """User account."""

    id: UUID
    email: str | None = None
    created_at: datetime | None = None


class Ingredient(BaseModel):
    """
    Master ingredient from the ingredients table.

    This is the canonical ingredient list - seeded from public APIs
    and enriched over time. User inventory links to these.
    """

    id: UUID
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: str | None = None
    parent_category: str = "pantry"
    family: str = ""
    cuisines: list[str] = Field(default_factory=list)
    tier: int = 2
    default_unit: str | None = None
    nutrition_per_100g: dict | None = None
    flavor_compounds: list[str] = Field(default_factory=list)
    is_system: bool = True
    created_at: datetime | None = None


class Inventory(BaseModel):
    """
    Item in user's pantry/fridge/freezer.

    Links to a master Ingredient for matching, but also stores
    the name as entered for display purposes.
    """

    id: UUID
    user_id: UUID
    ingredient_id: UUID | None = None  # Link to master ingredient
    name: str  # As entered by user
    quantity: float
    unit: str
    location: str | None = None  # "pantry", "fridge", "freezer"
    expiry_date: date | None = None
    purchase_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Recipe(BaseModel):
    """
    A recipe - either system-provided or user-created.
    """

    id: UUID
    user_id: UUID | None = None  # None for system recipes
    name: str
    description: str | None = None
    cuisine: str | None = None
    difficulty: str | None = None  # "easy", "medium", "hard"
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    instructions: list[str]
    tags: list[str] = Field(default_factory=list)
    source_url: str | None = None
    is_system: bool = False
    created_at: datetime | None = None


class RecipeIngredient(BaseModel):
    """
    Junction table: ingredients needed for a recipe.

    Stores the quantity/unit specific to this recipe.
    """

    id: UUID
    recipe_id: UUID
    ingredient_id: UUID | None = None  # Link to master ingredient
    name: str  # Display name for this recipe
    quantity: float | None = None
    unit: str | None = None
    notes: str | None = None  # "or substitute X"
    is_optional: bool = False


class MealPlan(BaseModel):
    """
    A planned meal for a specific date.
    """

    id: UUID
    user_id: UUID
    date: date
    meal_type: str  # "breakfast", "lunch", "dinner", "snack"
    recipe_id: UUID | None = None
    notes: str | None = None
    servings: int = 1
    created_at: datetime | None = None


class ShoppingListItem(BaseModel):
    """
    Item on the user's shopping list.
    """

    id: UUID
    user_id: UUID
    ingredient_id: UUID | None = None
    name: str
    quantity: float | None = None
    unit: str | None = None
    category: str | None = None  # For grouping in store
    is_purchased: bool = False
    source: str | None = None  # "meal_plan", "manual", "low_stock"
    created_at: datetime | None = None


# =============================================================================
# User Preferences
# =============================================================================


class Preferences(BaseModel):
    """
    User's dietary preferences and settings.
    
    Includes:
    - Profile: allergies, dietary restrictions, household size
    - Overall: cuisines, current vibes, planning rhythm
    - Subdomain guidance: per-subdomain narrative preferences for context injection
    """

    id: UUID
    user_id: UUID
    
    # Profile (hard constraints)
    dietary_restrictions: list[str] = Field(default_factory=list)  # "vegetarian", "gluten-free"
    allergies: list[str] = Field(default_factory=list)  # "peanuts", "shellfish"
    household_size: int = 1
    cooking_skill_level: str = "intermediate"  # "beginner", "intermediate", "advanced"
    
    # Overall preferences (soft guidance)
    favorite_cuisines: list[str] = Field(default_factory=list)  # "italian", "thai"
    disliked_ingredients: list[str] = Field(default_factory=list)
    planning_rhythm: list[str] = Field(default_factory=list)  # "weekends only", "30min weeknights"
    current_vibes: list[str] = Field(default_factory=list)  # "more vegetables", "comfort food"
    
    # Subdomain guidance (narrative modules for context injection)
    # Keys: inventory, recipes, meal_plans, shopping, tasks
    # Values: ~200 token narrative strings
    subdomain_guidance: dict[str, str] = Field(default_factory=dict)

    # Assumed staples - ingredients user always keeps stocked
    # Set during onboarding, used to skip "do you have X?" questions
    assumed_staples: list[UUID] = Field(default_factory=list)

    updated_at: datetime | None = None


class FlavorPreference(BaseModel):
    """
    Learned preference score for specific ingredients.

    Updated as user cooks recipes and provides feedback.
    """

    id: UUID
    user_id: UUID
    ingredient_id: UUID
    preference_score: float = 0  # -1 to 1, negative = dislike
    times_used: int = 0
    last_used_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Memory
# =============================================================================


class ConversationMemory(BaseModel):
    """
    Stored memory from conversations.

    Used for long-term context retrieval via vector search.
    """

    id: UUID
    user_id: UUID
    content: str
    memory_type: str | None = None  # "preference", "context", "instruction"
    metadata: dict = Field(default_factory=dict)
    expires_at: datetime | None = None
    created_at: datetime | None = None


# =============================================================================
# Create/Update Models (for input validation)
# =============================================================================


class InventoryCreate(BaseModel):
    """Input for creating an inventory item."""

    name: str
    quantity: float
    unit: str
    ingredient_id: UUID | None = None
    location: str | None = None
    expiry_date: date | None = None
    purchase_date: date | None = None


class InventoryUpdate(BaseModel):
    """Input for updating an inventory item."""

    name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    location: str | None = None
    expiry_date: date | None = None


class RecipeCreate(BaseModel):
    """Input for creating a recipe."""

    name: str
    description: str | None = None
    cuisine: str | None = None
    difficulty: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    instructions: list[str]
    tags: list[str] = Field(default_factory=list)
    source_url: str | None = None
    ingredients: list["RecipeIngredientCreate"] = Field(default_factory=list)


class RecipeIngredientCreate(BaseModel):
    """Input for a recipe ingredient."""

    name: str
    quantity: float | None = None
    unit: str | None = None
    notes: str | None = None
    is_optional: bool = False


class MealPlanCreate(BaseModel):
    """Input for creating a meal plan entry."""

    date: date
    meal_type: str
    recipe_id: UUID | None = None
    notes: str | None = None
    servings: int = 1


class ShoppingListItemCreate(BaseModel):
    """Input for adding to shopping list."""

    name: str
    quantity: float | None = None
    unit: str | None = None
    category: str | None = None
    source: str | None = None


class TaskCreate(BaseModel):
    """Input for creating a task."""

    title: str
    due_date: date | None = None
    category: str | None = None
    completed: bool = False
    recipe_id: UUID | None = None
    meal_plan_id: UUID | None = None

