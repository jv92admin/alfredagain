"""
Onboarding Forms - Phase 1: Deterministic Constraints.

Collects hard constraints that:
- Must be machine-readable (for filtering)
- Have clear, finite options (no interpretation needed)
- Are critical for safety (allergies, restrictions)
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Valid Options (User-Specific, Not Global Constants)
# =============================================================================
# These lists define VALID options for validation purposes.
# Users can have any subset of these - we're not limiting to a shared list.

VALID_DIETARY_RESTRICTIONS = {
    "vegetarian",
    "vegan", 
    "pescatarian",
    "halal",
    "kosher",
    "gluten-free",
    "dairy-free",
    "low-carb",
    "keto",
    "paleo",
    "whole30",
    "fodmap",
}

# Common allergens (FDA Big 9 + sesame)
# Users can add custom allergens - these are just for validation hints
COMMON_ALLERGENS = [
    "peanuts",
    "tree nuts",
    "milk",
    "eggs", 
    "wheat",
    "soy",
    "fish",
    "shellfish",
    "sesame",
]

# Equipment options with display metadata
EQUIPMENT_OPTIONS = [
    {"id": "instant-pot", "label": "Instant Pot", "icon": "🍲"},
    {"id": "air-fryer", "label": "Air Fryer", "icon": "🍟"},
    {"id": "slow-cooker", "label": "Slow Cooker", "icon": "🥘"},
    {"id": "sous-vide", "label": "Sous Vide", "icon": "🌡️"},
    {"id": "grill", "label": "Grill/BBQ", "icon": "🔥"},
    {"id": "blender", "label": "Blender", "icon": "🥤"},
    {"id": "food-processor", "label": "Food Processor", "icon": "🔪"},
    {"id": "dutch-oven", "label": "Dutch Oven", "icon": "🫕"},
    {"id": "wok", "label": "Wok", "icon": "🥡"},
    {"id": "stand-mixer", "label": "Stand Mixer", "icon": "🎂"},
    {"id": "cast-iron", "label": "Cast Iron Skillet", "icon": "🍳"},
    {"id": "smoker", "label": "Smoker", "icon": "💨"},
    {"id": "pizza-stone", "label": "Pizza Stone", "icon": "🍕"},
    {"id": "pressure-cooker", "label": "Pressure Cooker", "icon": "♨️"},
    {"id": "rice-cooker", "label": "Rice Cooker", "icon": "🍚"},
]

VALID_EQUIPMENT_IDS = {e["id"] for e in EQUIPMENT_OPTIONS}

SKILL_LEVELS = ["beginner", "intermediate", "advanced"]


# =============================================================================
# Form Model
# =============================================================================

class ConstraintsForm(BaseModel):
    """
    Phase 1: Hard constraints form data.
    
    These constraints filter ALL subsequent suggestions:
    - Allergies exclude ingredients from discovery + recipes
    - Dietary restrictions exclude incompatible foods
    - Skill level affects recipe complexity defaults
    - Equipment affects recipe suggestions
    """
    
    household_size: int = Field(
        ge=1, 
        le=12, 
        default=2,
        description="Number of people being cooked for"
    )
    
    allergies: list[str] = Field(
        default_factory=list,
        description="Food allergies (safety-critical)"
    )
    
    dietary_restrictions: list[str] = Field(
        default_factory=list,
        description="Dietary restrictions (vegetarian, vegan, etc.)"
    )
    
    cooking_skill_level: Literal["beginner", "intermediate", "advanced"] = Field(
        default="intermediate",
        description="Self-assessed cooking skill"
    )
    
    available_equipment: list[str] = Field(
        default_factory=list,
        description="Special cooking equipment available"
    )
    
    @field_validator("allergies", mode="before")
    @classmethod
    def normalize_allergies(cls, v: list[str]) -> list[str]:
        """Normalize allergy names to lowercase."""
        if not v:
            return []
        return [a.lower().strip() for a in v if a and a.strip()]
    
    @field_validator("dietary_restrictions", mode="before")
    @classmethod
    def validate_dietary_restrictions(cls, v: list[str]) -> list[str]:
        """Validate and normalize dietary restrictions."""
        if not v:
            return []
        
        normalized = []
        for r in v:
            if not r or not r.strip():
                continue
            r_lower = r.lower().strip()
            if r_lower in VALID_DIETARY_RESTRICTIONS:
                normalized.append(r_lower)
            else:
                # Log unknown restriction but don't reject
                logger.info(f"Unknown dietary restriction (accepted): {r}")
                normalized.append(r_lower)
        
        return normalized
    
    @field_validator("available_equipment", mode="before")
    @classmethod
    def validate_equipment(cls, v: list[str]) -> list[str]:
        """Validate equipment IDs."""
        if not v:
            return []
        
        validated = []
        for e in v:
            if not e or not e.strip():
                continue
            e_lower = e.lower().strip()
            if e_lower in VALID_EQUIPMENT_IDS:
                validated.append(e_lower)
            else:
                logger.info(f"Unknown equipment (ignored): {e}")
        
        return validated


def validate_constraints(form: ConstraintsForm) -> tuple[bool, list[str]]:
    """
    Validate constraints form with specific error messages.
    
    Returns:
        (is_valid, error_messages)
    """
    errors = []
    
    # Household size (already validated by Pydantic, but double-check)
    if not 1 <= form.household_size <= 12:
        errors.append("Household size must be between 1 and 12")
    
    # Skill level (already validated by Literal type)
    if form.cooking_skill_level not in SKILL_LEVELS:
        errors.append("Please select a valid skill level")
    
    # Allergies: warn on unknown but don't block
    unknown_allergens = set(form.allergies) - set(a.lower() for a in COMMON_ALLERGENS)
    if unknown_allergens:
        # Log for review, but accept (user might have niche allergy)
        logger.info(f"Custom allergens submitted: {unknown_allergens}")
    
    # Dietary restrictions: warn on unknown
    invalid_restrictions = set(form.dietary_restrictions) - VALID_DIETARY_RESTRICTIONS
    if invalid_restrictions:
        logger.info(f"Custom dietary restrictions: {invalid_restrictions}")
    
    return (len(errors) == 0, errors)


# =============================================================================
# API Response Helpers
# =============================================================================

def get_form_options() -> dict:
    """
    Get all form options for frontend rendering.
    
    Returns dict with:
    - allergens: Common allergen suggestions
    - dietary_restrictions: Valid restriction options
    - equipment: Equipment options with icons
    - skill_levels: Skill level options
    """
    return {
        "allergens": COMMON_ALLERGENS,
        "dietary_restrictions": list(VALID_DIETARY_RESTRICTIONS),
        "equipment": EQUIPMENT_OPTIONS,
        "skill_levels": [
            {"id": "beginner", "label": "Beginner", "description": "Learning the basics"},
            {"id": "intermediate", "label": "Intermediate", "description": "Comfortable improvising"},
            {"id": "advanced", "label": "Advanced", "description": "Techniques come naturally"},
        ],
    }
