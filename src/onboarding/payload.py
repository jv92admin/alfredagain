"""
Onboarding Payload Definition.

The OnboardingPayload is the contract between onboarding and Alfred.
It defines what data is collected and how it maps to Alfred's data model.
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Any
import json


@dataclass
class StyleSample:
    """A sample shown to user during style selection."""
    id: str
    style_name: str
    text: str  # The actual content shown
    style_tags: list[str] = field(default_factory=list)
    why_this_style: str = ""  # LLM explanation


@dataclass
class PreferenceInteraction:
    """
    Full record of a style selection interaction.
    
    Stored for:
    - Future reference ("You preferred X...")
    - Style clustering / personalization research
    - Potential re-onboarding or preference evolution
    
    NOTE: Only `llm_summary` gets wired into Alfred's prompts.
    The rest is stored but NOT actively used yet.
    """
    domain: Literal["recipes", "meal_plans", "tasks"]
    
    # What LLM proposed
    samples_shown: list[StyleSample] = field(default_factory=list)
    llm_justification: str = ""  # Why LLM proposed these options
    
    # User's response
    user_selection: str | None = None  # ID of selected sample (if picked)
    user_feedback: str = ""  # Natural language feedback
    
    # LLM synthesis
    llm_summary: str = ""  # → Goes to subdomain_guidance[domain]
    
    # The chosen example (for future few-shot use)
    stylistic_example: dict | None = None
    
    def to_dict(self) -> dict:
        """Serialize to dict."""
        data = asdict(self)
        # Convert StyleSample objects to dicts
        data["samples_shown"] = [
            asdict(s) if isinstance(s, StyleSample) else s 
            for s in self.samples_shown
        ]
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "PreferenceInteraction":
        """Deserialize from dict."""
        if "samples_shown" in data:
            data["samples_shown"] = [
                StyleSample(**s) if isinstance(s, dict) else s
                for s in data["samples_shown"]
            ]
        return cls(**data)


@dataclass
class OnboardingPayload:
    """
    Complete output from onboarding flow.
    
    This is the contract between onboarding and Alfred.
    All data linked by user_id at application time.
    
    WHAT GETS WIRED TO ALFRED (now):
    - preferences → preferences table
    - subdomain_guidance → preferences.subdomain_guidance
    - initial_inventory → inventory table
    
    WHAT GETS WIRED LATER:
    - stylistic_examples → preferences.stylistic_examples (needs migration)
    - cuisine_preferences → preferences or separate table
    
    WHAT GETS STORED BUT NOT WIRED (yet):
    - preference_interactions → Full interaction history for future use
    - ingredient_preferences → For future ingredient-aware features
    """
    
    # =========================================================================
    # WIRED TO ALFRED
    # =========================================================================
    
    # Phase 1: Hard constraints
    preferences: dict = field(default_factory=lambda: {
        "household_size": 2,
        "allergies": [],
        "dietary_restrictions": [],
        "cooking_skill_level": "intermediate",
        "available_equipment": [],
    })
    
    # Phase 2-3: Narrative guidance per subdomain
    # Maps to existing preferences.subdomain_guidance in Alfred
    subdomain_guidance: dict = field(default_factory=lambda: {
        "recipes": "",
        "meal_plans": "",
        "shopping": "",
        "inventory": "",
        "tasks": "",
    })
    
    # Phase 2: Initial pantry seed
    initial_inventory: list[dict] = field(default_factory=list)
    # Each: {"name": str, "category": str | None}
    
    # =========================================================================
    # WIRED LATER (needs schema additions)
    # =========================================================================
    
    # Phase 3: Stylistic examples per subdomain
    stylistic_examples: dict = field(default_factory=lambda: {
        "recipes": None,
        "meal_plans": None,
        "tasks": None,
    })
    
    # Phase 2: Selected cuisines
    cuisine_preferences: list[str] = field(default_factory=list)

    # Phase 2b: User-confirmed staples (ingredient UUIDs)
    assumed_staples: list[str] = field(default_factory=list)
    
    # =========================================================================
    # STORED BUT NOT WIRED YET
    # =========================================================================
    
    # Full interaction history (for future use)
    preference_interactions: dict = field(default_factory=dict)
    # Keys: "recipes", "meal_plans", "tasks" → PreferenceInteraction
    
    # Phase 2: Discovered ingredient preferences
    ingredient_preferences: list[dict] = field(default_factory=list)
    # Each: {"ingredient_id": str, "preference_score": float}
    
    # Interview answers (for audit/debugging synthesis)
    interview_answers: list[dict] = field(default_factory=list)
    # Each: {"page": int, "question_id": str, "question": str, "answer": str}
    
    # =========================================================================
    # METADATA
    # =========================================================================
    
    onboarding_completed: bool = False
    onboarding_version: str = "1.0"
    
    def to_dict(self) -> dict:
        """Serialize for storage/transfer."""
        return {
            # Wired now
            "preferences": self.preferences,
            "subdomain_guidance": self.subdomain_guidance,
            "initial_inventory": self.initial_inventory,
            # Wired later
            "stylistic_examples": self.stylistic_examples,
            "cuisine_preferences": self.cuisine_preferences,
            "assumed_staples": self.assumed_staples,
            # Stored (not wired)
            "preference_interactions": {
                k: v.to_dict() if isinstance(v, PreferenceInteraction) else v
                for k, v in self.preference_interactions.items()
            },
            "ingredient_preferences": self.ingredient_preferences,
            "interview_answers": self.interview_answers,
            # Metadata
            "onboarding_completed": self.onboarding_completed,
            "onboarding_version": self.onboarding_version,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "OnboardingPayload":
        """Deserialize from dict."""
        # Convert preference_interactions back to dataclass
        if "preference_interactions" in data:
            data["preference_interactions"] = {
                k: PreferenceInteraction.from_dict(v) if isinstance(v, dict) else v
                for k, v in data["preference_interactions"].items()
            }
        return cls(**data)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "OnboardingPayload":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


def build_payload_from_state(state: "OnboardingState") -> OnboardingPayload:
    """
    Build final OnboardingPayload from accumulated OnboardingState.
    
    Called at end of onboarding to assemble all collected data.
    """
    # Import here to avoid circular dependency
    from .state import OnboardingState
    
    payload = OnboardingPayload()
    
    # Phase 1: Constraints → preferences
    if state.constraints:
        payload.preferences = {
            "household_size": state.constraints.get("household_size", 2),
            "allergies": state.constraints.get("allergies", []),
            "dietary_restrictions": state.constraints.get("dietary_restrictions", []),
            "cooking_skill_level": state.constraints.get("cooking_skill_level", "intermediate"),
            "available_equipment": state.constraints.get("available_equipment", []),
        }
    
    # Phase 2: Pantry → initial_inventory
    payload.initial_inventory = state.pantry_items
    
    # Phase 2: Cuisines
    payload.cuisine_preferences = state.cuisine_selections

    # Phase 2b: Staples
    payload.assumed_staples = state.staple_selections
    
    # Phase 2: Ingredient discovery → ingredient_preferences
    if state.ingredient_discovery.preference_scores:
        payload.ingredient_preferences = state.ingredient_discovery.preference_scores
    
    # Phase 3: Style selections → subdomain_guidance + stylistic_examples + interactions
    for style_state, domain in [
        (state.style_recipes, "recipes"),
        (state.style_meal_plans, "meal_plans"),
        (state.style_tasks, "tasks"),
    ]:
        if style_state.completed:
            # Build PreferenceInteraction record
            interaction = PreferenceInteraction(
                domain=domain,
                samples_shown=[
                    StyleSample(**s) if isinstance(s, dict) else s
                    for s in style_state.samples_shown
                ],
                user_selection=style_state.user_selection,
                user_feedback=style_state.user_feedback,
            )
            payload.preference_interactions[domain] = interaction
    
    # Phase 3: Habits → shopping, inventory, meal_plans guidance
    if state.habits_extraction:
        # Apply extracted summaries to subdomain_guidance
        if state.habits_extraction.get("meal_plans_summary"):
            payload.subdomain_guidance["meal_plans"] = state.habits_extraction["meal_plans_summary"]
        if state.habits_extraction.get("shopping_summary"):
            payload.subdomain_guidance["shopping"] = state.habits_extraction["shopping_summary"]
        if state.habits_extraction.get("inventory_summary"):
            payload.subdomain_guidance["inventory"] = state.habits_extraction["inventory_summary"]
    
    # Copy any guidance already in payload_draft (from style synthesis)
    if state.payload_draft.get("subdomain_guidance"):
        for domain, guidance in state.payload_draft["subdomain_guidance"].items():
            if guidance and not payload.subdomain_guidance.get(domain):
                payload.subdomain_guidance[domain] = guidance
    
    if state.payload_draft.get("stylistic_examples"):
        payload.stylistic_examples = state.payload_draft["stylistic_examples"]
    
    # Copy interview answers for audit/debugging
    if state.payload_draft.get("interview_answers"):
        payload.interview_answers = state.payload_draft["interview_answers"]
    
    payload.onboarding_completed = True
    
    return payload
