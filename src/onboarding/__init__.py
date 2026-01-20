"""
Alfred Onboarding System.

Isolated module for new user setup. Collects preferences through a progressive flow
and outputs a structured payload for Alfred integration.

Phases:
1. Deterministic Forms - Hard constraints (allergies, dietary, skill, equipment)
2. Discovery & Seeding - Pantry seeding, ingredient discovery, cuisine selection
3. Style Selection - LLM-generated samples for recipes/meal plans/tasks
4. Final Preview - Sample recipes, feedback logging

See docs/onboarding-spec.md for full specification.
"""

from .state import OnboardingState, OnboardingPhase
from .payload import OnboardingPayload, PreferenceInteraction

__all__ = [
    "OnboardingState",
    "OnboardingPhase", 
    "OnboardingPayload",
    "PreferenceInteraction",
]
