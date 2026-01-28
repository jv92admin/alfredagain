"""
Onboarding State Management.

Tracks progress through onboarding phases and accumulates data for the final payload.
State is persisted to onboarding_sessions table to survive interruptions.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any
import json


class OnboardingPhase(Enum):
    """Onboarding flow phases."""
    CONSTRAINTS = "constraints"          # Phase 1: Hard constraints form
    DISCOVERY = "discovery"              # Phase 2: (Legacy) - now routes to STAPLES
    STAPLES = "staples"                  # Phase 2b: Staples selection (NEW)
    STYLE_RECIPES = "style_recipes"      # Phase 3a: Recipe style discovery
    STYLE_MEAL_PLANS = "style_meal_plans"# Phase 3b: Meal plan style discovery
    STYLE_TASKS = "style_tasks"          # Phase 3c: Task style discovery
    HABITS = "habits"                    # Phase 4: Habits extraction
    PREVIEW = "preview"                  # Phase 5: Final preview
    COMPLETE = "complete"                # Done


@dataclass
class DiscoveryRound:
    """One round of ingredient discovery."""
    round_num: int
    options: list[dict] = field(default_factory=list)  # Ingredients shown
    selections: list[str] = field(default_factory=list)  # User's picks (ingredient IDs)


@dataclass
class IngredientDiscoveryState:
    """State for ingredient discovery flow."""
    rounds: list[DiscoveryRound] = field(default_factory=list)
    completed: bool = False
    preference_scores: list[dict] = field(default_factory=list)  # Computed at end


@dataclass
class StyleDiscoveryState:
    """State for a single style discovery domain (recipes, meal_plans, tasks)."""
    domain: str = ""
    samples_shown: list[dict] = field(default_factory=list)
    user_selection: str | None = None
    user_feedback: str = ""
    completed: bool = False


@dataclass
class OnboardingState:
    """
    Main onboarding session state.
    
    Persisted to onboarding_sessions table as JSONB.
    Incrementally builds toward OnboardingPayload.
    """
    user_id: str = ""
    current_phase: OnboardingPhase = OnboardingPhase.CONSTRAINTS
    
    # Phase 1: Constraints
    constraints: dict = field(default_factory=dict)
    # Expected keys: household_size, allergies, dietary_restrictions, 
    #                cooking_skill_level, available_equipment
    
    # Phase 2: Discovery & Seeding
    pantry_items: list[dict] = field(default_factory=list)
    ingredient_discovery: IngredientDiscoveryState = field(
        default_factory=IngredientDiscoveryState
    )
    cuisine_selections: list[str] = field(default_factory=list)

    # Phase 2b: Staples selection (ingredient UUIDs user always keeps stocked)
    staple_selections: list[str] = field(default_factory=list)
    
    # Phase 3: Style Discovery (one per domain)
    style_recipes: StyleDiscoveryState = field(
        default_factory=lambda: StyleDiscoveryState(domain="recipes")
    )
    style_meal_plans: StyleDiscoveryState = field(
        default_factory=lambda: StyleDiscoveryState(domain="meal_plans")
    )
    style_tasks: StyleDiscoveryState = field(
        default_factory=lambda: StyleDiscoveryState(domain="tasks")
    )
    habits_response: str = ""
    habits_extraction: dict = field(default_factory=dict)
    
    # Phase 4: Preview
    preview_recipes: list[dict] = field(default_factory=list)
    preview_feedback: list[dict] = field(default_factory=list)
    
    # Accumulated payload draft (built incrementally)
    payload_draft: dict = field(default_factory=dict)
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        """Set timestamps if not provided."""
        now = datetime.utcnow().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def to_dict(self) -> dict:
        """Serialize state to dict for JSON storage."""
        data = asdict(self)
        # Convert enum to string
        data["current_phase"] = self.current_phase.value
        # Convert nested dataclasses
        data["ingredient_discovery"] = asdict(self.ingredient_discovery)
        data["style_recipes"] = asdict(self.style_recipes)
        data["style_meal_plans"] = asdict(self.style_meal_plans)
        data["style_tasks"] = asdict(self.style_tasks)
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "OnboardingState":
        """Deserialize state from dict."""
        # Convert phase string back to enum
        if "current_phase" in data:
            data["current_phase"] = OnboardingPhase(data["current_phase"])
        
        # Convert nested dicts back to dataclasses
        if "ingredient_discovery" in data and isinstance(data["ingredient_discovery"], dict):
            ing_data = data["ingredient_discovery"]
            # Convert rounds
            rounds = [
                DiscoveryRound(**r) if isinstance(r, dict) else r 
                for r in ing_data.get("rounds", [])
            ]
            ing_data["rounds"] = rounds
            data["ingredient_discovery"] = IngredientDiscoveryState(**ing_data)
        
        for style_key in ["style_recipes", "style_meal_plans", "style_tasks"]:
            if style_key in data and isinstance(data[style_key], dict):
                data[style_key] = StyleDiscoveryState(**data[style_key])
        
        return cls(**data)
    
    def to_json(self) -> str:
        """Serialize state to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "OnboardingState":
        """Deserialize state from JSON string."""
        return cls.from_dict(json.loads(json_str))


def get_next_phase(state: OnboardingState) -> OnboardingPhase:
    """
    Determine the next phase based on current state.
    
    Returns the next phase to transition to, or current phase if not ready.
    """
    phase = state.current_phase
    
    if phase == OnboardingPhase.CONSTRAINTS:
        if state.constraints:
            return OnboardingPhase.DISCOVERY
    
    elif phase == OnboardingPhase.DISCOVERY:
        # Legacy: Users stuck in DISCOVERY phase → route to STAPLES
        # (Discovery is now skipped, cuisines go directly to staples)
        return OnboardingPhase.STAPLES

    elif phase == OnboardingPhase.STAPLES:
        # Staples is complete, move to style interview
        return OnboardingPhase.STYLE_RECIPES
    
    elif phase == OnboardingPhase.STYLE_RECIPES:
        if state.style_recipes.completed:
            return OnboardingPhase.STYLE_MEAL_PLANS
    
    elif phase == OnboardingPhase.STYLE_MEAL_PLANS:
        if state.style_meal_plans.completed:
            return OnboardingPhase.STYLE_TASKS
    
    elif phase == OnboardingPhase.STYLE_TASKS:
        if state.style_tasks.completed:
            return OnboardingPhase.HABITS
    
    elif phase == OnboardingPhase.HABITS:
        if state.habits_extraction:
            return OnboardingPhase.PREVIEW
    
    elif phase == OnboardingPhase.PREVIEW:
        # Preview feedback is optional
        return OnboardingPhase.COMPLETE
    
    return phase  # Stay in current phase


def can_skip_phase(phase: OnboardingPhase) -> bool:
    """Check if a phase can be skipped."""
    skippable = {
        OnboardingPhase.DISCOVERY,
        OnboardingPhase.STAPLES,
        OnboardingPhase.STYLE_RECIPES,
        OnboardingPhase.STYLE_MEAL_PLANS,
        OnboardingPhase.STYLE_TASKS,
        OnboardingPhase.HABITS,
        OnboardingPhase.PREVIEW,
    }
    return phase in skippable
