"""
Alfred V2 - Model Router.

Selects the appropriate OpenAI model based on task complexity.
Currently using GPT-4.1-mini for testing (faster than GPT-5 reasoning models).

Complexity levels:
- low: Simple lookups, confirmations, basic CRUD → gpt-4.1-mini
- medium: Multi-step reasoning, recipe suggestions → gpt-4.1-mini
- high: Complex planning, novel problem solving → gpt-4.1-mini (upgrade to gpt-5 later)
"""

from typing import Literal, TypedDict


class ModelConfig(TypedDict, total=False):
    """Configuration for model calls."""

    model: str
    temperature: float
    reasoning_effort: str  # "minimal", "low", "medium", "high"
    verbosity: str  # "low", "medium", "high"


# Model configurations by complexity
# GPT-4.1-mini for testing (faster, non-reasoning)
# TODO: Switch to GPT-5 series with reasoning_effort when ready
MODEL_CONFIGS: dict[str, ModelConfig] = {
    "low": {
        "model": "gpt-4.1-mini",
        "temperature": 0.2,  # Very deterministic for simple CRUD
        "verbosity": "low",  # Terse output
    },
    "medium": {
        "model": "gpt-4.1-mini",
        "temperature": 0.5,  # Some flexibility for reasoning
        "verbosity": "medium",  # Default detail level
    },
    "high": {
        "model": "gpt-4.1-mini",  # TODO: gpt-5 for complex tasks
        "temperature": 0.7,  # More creative for generation
        "verbosity": "high",  # Detailed output
    },
}

# Default config if complexity not recognized
DEFAULT_CONFIG: ModelConfig = {
    "model": "gpt-4.1-mini",
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

# Node-specific temperature overrides
# Lower = more deterministic, higher = more creative
NODE_TEMPERATURE: dict[str, float] = {
    "router": 0.15,  # Classification should be consistent
    "act": 0.25,  # CRUD needs precision but also context awareness
    "think": 0.35,  # Planning needs flexibility to merge steps
    "reply": 0.6,  # User-facing can be warmer
    "summarize": 0.3,  # Summarization should be consistent
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

    # Apply node-specific temperature (always - determinism is important)
    if node in NODE_TEMPERATURE:
        config["temperature"] = NODE_TEMPERATURE[node]

    return config
