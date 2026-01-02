"""
Alfred V2 - Model Router.

Selects the appropriate OpenAI model based on task complexity.
Uses different models for different complexity levels:
- low: gpt-4.1-mini (fast, cheap)
- medium: gpt-4.1 (capable, good latency)
- high: gpt-5.1 (full reasoning model)

Set ALFRED_USE_ADVANCED_MODELS=false to use gpt-4.1-mini for all levels (dev mode).
"""

import os
from typing import Literal, TypedDict


class ModelConfig(TypedDict, total=False):
    """Configuration for model calls."""

    model: str
    temperature: float
    reasoning_effort: str  # "minimal", "low", "medium", "high" (for o1 models)
    verbosity: str  # "low", "medium", "high"


# Check if advanced models are enabled (default: True for production)
USE_ADVANCED_MODELS = os.environ.get("ALFRED_USE_ADVANCED_MODELS", "true").lower() == "true"


# Model configurations by complexity
# When USE_ADVANCED_MODELS is False, all use gpt-4.1-mini for testing
if USE_ADVANCED_MODELS:
    MODEL_CONFIGS: dict[str, ModelConfig] = {
        "low": {
            "model": "gpt-4.1-mini",
            "temperature": 0.2,  # Very deterministic for simple CRUD
            "verbosity": "low",  # Terse output
        },
        "medium": {
            "model": "gpt-4.1",  # Capable with good latency
            "temperature": 0.5,  # Balanced reasoning
            "verbosity": "medium",  # Default detail level
        },
        "high": {
            "model": "gpt-5.1",  # Full reasoning model
            "temperature": 0.7,  # Higher creativity for complex tasks
            "verbosity": "high",  # Detailed output
        },
    }
else:
    # Dev mode: all use gpt-4.1-mini
    MODEL_CONFIGS: dict[str, ModelConfig] = {
        "low": {
            "model": "gpt-4.1-mini",
            "temperature": 0.2,
            "verbosity": "low",
        },
        "medium": {
            "model": "gpt-4.1-mini",
            "temperature": 0.5,
            "verbosity": "medium",
        },
        "high": {
            "model": "gpt-4.1-mini",
            "temperature": 0.7,
            "verbosity": "high",
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
#
# V3 Node Complexity Recommendations:
#   router    → low    (simple classification)
#   understand→ medium (context inference needs smarter model)
#   think     → medium (planning with parallelization)
#   act       → varies (read/write=low, analyze/generate=medium-high)
#   reply     → low    (synthesis from structured data)
#   summarize → low    (deterministic context updates)
#
NODE_VERBOSITY: dict[str, str] = {
    "router": "low",  # Just classification
    "understand": "low",  # Structured JSON output
    "think": "medium",  # Plans need some detail
    "act": "low",  # Tool calls should be terse
    "reply": "medium",  # User-facing needs balance
}

# Node-specific temperature overrides
# Lower = more deterministic, higher = more creative
NODE_TEMPERATURE: dict[str, float] = {
    "router": 0.15,  # Classification should be consistent
    "understand": 0.2,  # Context inference but still deterministic
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
