"""
Alfred V2 - Model Router.

Selects the appropriate OpenAI model based on task complexity.

Complexity levels:
- low: Simple lookups, confirmations, basic CRUD → gpt-4o-mini (fast, cheap)
- medium: Multi-step reasoning, recipe suggestions → gpt-4o (balanced)
- high: Complex planning, novel problem solving → o1 (reasoning model)
"""

from typing import Literal

# Model mapping - easy to adjust based on performance/cost needs
MODEL_MAP: dict[str, str] = {
    "low": "gpt-4o-mini",
    "medium": "gpt-4o",
    "high": "o1",  # o1 for complex reasoning
}

# Fallback if complexity not recognized
DEFAULT_MODEL = "gpt-4o"


def get_model(complexity: Literal["low", "medium", "high"] | str) -> str:
    """
    Get the appropriate model for a given complexity level.

    Args:
        complexity: Task complexity level

    Returns:
        OpenAI model name string
    """
    return MODEL_MAP.get(complexity, DEFAULT_MODEL)


def get_model_config(complexity: Literal["low", "medium", "high"] | str) -> dict:
    """
    Get full model configuration for a complexity level.

    Returns model name and appropriate parameters.
    """
    model = get_model(complexity)

    # o1 models have different parameter support
    if model.startswith("o1"):
        return {
            "model": model,
            # o1 doesn't support temperature or max_tokens in the same way
            # It uses max_completion_tokens instead
        }

    # Standard models
    return {
        "model": model,
        "temperature": 0.7 if complexity == "medium" else 0.3,
    }

