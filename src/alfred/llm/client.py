"""
Alfred V2 - LLM Client.

Wraps OpenAI with Instructor for guaranteed structured outputs.
All LLM calls go through here for consistency and observability.

Supports GPT-5 series with:
- reasoning_effort: Controls thinking depth (minimal, low, medium, high)
- verbosity: Controls output length (low, medium, high)
"""

from typing import TypeVar

import instructor
from openai import OpenAI
from pydantic import BaseModel

from alfred.config import settings
from alfred.llm.model_router import get_node_config
from alfred.llm.prompt_logger import log_prompt

# Type variable for generic structured output
T = TypeVar("T", bound=BaseModel)

# Singleton client instance
_client: instructor.Instructor | None = None

# Track current node for logging and config
_current_node: str = "unknown"


def set_current_node(node: str) -> None:
    """Set the current node name for prompt logging and config."""
    global _current_node
    _current_node = node


def get_client() -> instructor.Instructor:
    """
    Get the Instructor-wrapped OpenAI client.

    Uses singleton pattern to reuse connection.
    """
    global _client

    if _client is None:
        openai_client = OpenAI(api_key=settings.openai_api_key)
        _client = instructor.from_openai(openai_client)

    return _client


async def call_llm(
    *,
    response_model: type[T],
    system_prompt: str,
    user_prompt: str,
    complexity: str = "medium",
    max_retries: int = 2,
    verbosity_override: str | None = None,
) -> T:
    """
    Make a structured LLM call with guaranteed schema compliance.

    Args:
        response_model: Pydantic model class for the response
        system_prompt: System message setting context
        user_prompt: User message with the actual request
        complexity: Task complexity for model selection ("low", "medium", "high")
        max_retries: Number of retries if response doesn't match schema
        verbosity_override: Override verbosity (e.g., "high" for recipe generation)

    Returns:
        Instance of response_model with validated data

    Example:
        result = await call_llm(
            response_model=RouterOutput,
            system_prompt="You are a routing assistant...",
            user_prompt="Add milk to my pantry",
            complexity="low",
        )
        print(result.agent)  # "pantry"
    """
    client = get_client()

    # Get node-specific config
    config = get_node_config(_current_node, complexity)

    # Apply verbosity override if provided
    if verbosity_override:
        config["verbosity"] = verbosity_override

    # Extract model name for the API call
    model = config.pop("model", "gpt-5-mini")

    # Build messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Build API kwargs
    api_kwargs = {
        "model": model,
        "messages": messages,
        "response_model": response_model,
        "max_retries": max_retries,
        "store": False,  # Explicitly disable conversation storage
    }

    # Note: GPT-5 series models don't support temperature parameter
    # They use reasoning_effort instead for controlling thinking depth
    # Only add temperature for non-GPT-5 models
    if not model.startswith("gpt-5"):
        reasoning_effort = config.get("reasoning_effort", "medium")
        if reasoning_effort in ("minimal", "low"):
            api_kwargs["temperature"] = 0.3
        elif reasoning_effort == "medium":
            api_kwargs["temperature"] = 0.7

    # Note: The actual reasoning and verbosity params depend on the OpenAI API version
    # Instructor may not support them directly yet, so we log them for now
    # and apply what we can

    try:
        # Make the call with Instructor
        response = client.chat.completions.create(**api_kwargs)

        # Log the prompt + response
        log_prompt(
            node=_current_node,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model.__name__,
            response=response,
            config=config,  # Include reasoning/verbosity for debugging
        )

        return response

    except Exception as e:
        # Log the error case
        log_prompt(
            node=_current_node,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model.__name__,
            error=str(e),
            config=config,
        )
        raise
