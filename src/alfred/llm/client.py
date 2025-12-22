"""
Alfred V2 - LLM Client.

Wraps OpenAI with Instructor for guaranteed structured outputs.
All LLM calls go through here for consistency and observability.
"""

from typing import TypeVar

import instructor
from openai import OpenAI
from pydantic import BaseModel

from alfred.config import settings
from alfred.llm.model_router import get_model_config

# Type variable for generic structured output
T = TypeVar("T", bound=BaseModel)

# Singleton client instance
_client: instructor.Instructor | None = None


def get_client() -> instructor.Instructor:
    """
    Get the Instructor-wrapped OpenAI client.

    Uses singleton pattern to reuse connection.
    """
    global _client

    if _client is None:
        openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        _client = instructor.from_openai(openai_client)

    return _client


async def call_llm(
    *,
    response_model: type[T],
    system_prompt: str,
    user_prompt: str,
    complexity: str = "medium",
    max_retries: int = 2,
) -> T:
    """
    Make a structured LLM call with guaranteed schema compliance.

    Args:
        response_model: Pydantic model class for the response
        system_prompt: System message setting context
        user_prompt: User message with the actual request
        complexity: Task complexity for model selection ("low", "medium", "high")
        max_retries: Number of retries if response doesn't match schema

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
    config = get_model_config(complexity)

    # Build messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Make the call with Instructor
    # Instructor handles retries and validation automatically
    response = client.chat.completions.create(
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
        **config,
    )

    return response


async def call_llm_with_context(
    *,
    response_model: type[T],
    system_prompt: str,
    user_prompt: str,
    context: dict,
    complexity: str = "medium",
    max_retries: int = 2,
) -> T:
    """
    Make a structured LLM call with retrieved context injected.

    Same as call_llm but formats context into the prompt.

    Args:
        context: Dictionary of context data to inject (inventory, preferences, etc.)
    """
    # Format context into the prompt
    context_str = _format_context(context)

    enhanced_user_prompt = f"""## Context
{context_str}

## User Request
{user_prompt}"""

    return await call_llm(
        response_model=response_model,
        system_prompt=system_prompt,
        user_prompt=enhanced_user_prompt,
        complexity=complexity,
        max_retries=max_retries,
    )


def _format_context(context: dict) -> str:
    """Format context dictionary into readable string for LLM."""
    parts = []

    if "inventory" in context and context["inventory"]:
        parts.append("### Current Inventory")
        for item in context["inventory"]:
            parts.append(f"- {item.get('name', 'Unknown')}: {item.get('quantity', '?')} {item.get('unit', '')}")

    if "preferences" in context and context["preferences"]:
        prefs = context["preferences"]
        parts.append("\n### User Preferences")
        if prefs.get("dietary_restrictions"):
            parts.append(f"- Dietary: {', '.join(prefs['dietary_restrictions'])}")
        if prefs.get("allergies"):
            parts.append(f"- Allergies: {', '.join(prefs['allergies'])}")
        if prefs.get("favorite_cuisines"):
            parts.append(f"- Favorite cuisines: {', '.join(prefs['favorite_cuisines'])}")

    if "recipes" in context and context["recipes"]:
        parts.append("\n### Relevant Recipes")
        for recipe in context["recipes"][:5]:  # Limit to 5
            parts.append(f"- {recipe.get('name', 'Unknown')} ({recipe.get('cuisine', 'Unknown cuisine')})")

    if not parts:
        return "No context available."

    return "\n".join(parts)

