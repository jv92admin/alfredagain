"""
Alfred V2 - Model Router.

Selects the appropriate OpenAI model based on task complexity.
Uses GPT-5 series with reasoning effort and verbosity controls.

Complexity levels:
- low: Simple lookups, confirmations, basic CRUD → gpt-5-mini (minimal reasoning)
- medium: Multi-step reasoning, recipe suggestions → gpt-5-mini (medium reasoning)
- high: Complex planning, novel problem solving → gpt-5 (high reasoning)
"""

from typing import Literal, TypedDict


class ModelConfig(TypedDict, total=False):
    """Configuration for model calls."""

    model: str
    temperature: float
    reasoning_effort: str  # "minimal", "low", "medium", "high"
    verbosity: str  # "low", "medium", "high"


# Model configurations by complexity
# GPT-5 series supports reasoning_effort and verbosity parameters
MODEL_CONFIGS: dict[str, ModelConfig] = {
    "low": {
        "model": "gpt-5-mini",
        "reasoning_effort": "minimal",  # Fast, few reasoning tokens
        "verbosity": "low",  # Terse output
    },
    "medium": {
        "model": "gpt-5-mini",
        "reasoning_effort": "medium",  # Balanced thinking
        "verbosity": "medium",  # Default detail level
    },
    "high": {
        "model": "gpt-5",
        "reasoning_effort": "high",  # Deep reasoning
        "verbosity": "high",  # Detailed output
    },
}

# Default config if complexity not recognized
DEFAULT_CONFIG: ModelConfig = {
    "model": "gpt-5-mini",
    "reasoning_effort": "medium",
    "verbosity": "medium",
}


def get_model(complexity: Literal["low", "medium", "high"] | str) -> str:
    """
    Get the appropriate model for a given complexity level.

    Args:
        complexity: Task complexity level

    Returns:
        OpenAI model name string
    """
    config = MODEL_CONFIGS.get(complexity, DEFAULT_CONFIG)
    return config["model"]


def get_model_config(
    complexity: Literal["low", "medium", "high"] | str,
    *,
    verbosity_override: str | None = None,
) -> ModelConfig:
    """
    Get full model configuration for a complexity level.

    Args:
        complexity: Task complexity level
        verbosity_override: Optional override for verbosity (e.g., "high" for recipe generation)

    Returns:
        Model configuration with reasoning effort and verbosity
    """
    config = MODEL_CONFIGS.get(complexity, DEFAULT_CONFIG).copy()

    # Apply verbosity override if provided
    if verbosity_override:
        config["verbosity"] = verbosity_override

    return config


# Node-specific defaults
# Different nodes may want different verbosity even at same complexity
NODE_VERBOSITY: dict[str, str] = {
    "router": "low",  # Just classification
    "think": "medium",  # Plans need some detail
    "act": "low",  # Tool calls should be terse
    "reply": "medium",  # User-facing needs balance
}


def get_node_config(
    node: str,
    complexity: Literal["low", "medium", "high"] | str,
) -> ModelConfig:
    """
    Get model configuration optimized for a specific node.

    Args:
        node: Node name ("router", "think", "act", "reply")
        complexity: Task complexity level

    Returns:
        Model configuration tuned for the node
    """
    config = get_model_config(complexity)

    # Apply node-specific verbosity unless it's a high-complexity task
    # (high complexity overrides node defaults)
    if complexity != "high" and node in NODE_VERBOSITY:
        config["verbosity"] = NODE_VERBOSITY[node]

    return config
