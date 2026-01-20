"""
Constraint Utilities for Onboarding.

Simple utilities for working with user constraints.
Alfred handles dietary/allergy logic when generating - we don't need
to maintain hardcoded exclusion lists.

The constraints are stored and passed to Alfred, which reasons about them naturally.
"""


def format_constraints_for_prompt(
    dietary_restrictions: list[str],
    allergies: list[str],
    skill_level: str,
) -> str:
    """
    Format user constraints as a prompt section for LLM calls.
    
    Used when generating style samples, preview recipes, etc.
    Alfred understands these naturally - no hardcoded rules needed.
    """
    parts = []
    
    if dietary_restrictions:
        parts.append(f"Dietary: {', '.join(dietary_restrictions)}")
    
    if allergies:
        parts.append(f"Allergies: {', '.join(allergies)}")
    
    if skill_level:
        parts.append(f"Skill level: {skill_level}")
    
    return "\n".join(parts) if parts else "No restrictions"


def get_constraints_summary(constraints: dict) -> str:
    """
    Get a human-readable summary of constraints.
    
    For display in UI or logging.
    """
    parts = []
    
    if constraints.get("dietary_restrictions"):
        parts.append(f"{len(constraints['dietary_restrictions'])} dietary restrictions")
    
    if constraints.get("allergies"):
        parts.append(f"{len(constraints['allergies'])} allergies")
    
    if constraints.get("available_equipment"):
        parts.append(f"{len(constraints['available_equipment'])} equipment items")
    
    skill = constraints.get("cooking_skill_level", "intermediate")
    parts.append(f"{skill} cook")
    
    household = constraints.get("household_size", 2)
    parts.append(f"household of {household}")
    
    return ", ".join(parts)
