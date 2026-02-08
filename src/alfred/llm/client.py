"""
Alfred V2 - LLM Client.

Wraps OpenAI with Instructor for guaranteed structured outputs.
All LLM calls go through here for consistency and observability.

Also provides raw chat functions (call_llm_chat, call_llm_chat_stream)
for bypass modes that skip the graph and don't need structured output.

Model support:
- GPT-4.1-mini: Fast, non-reasoning (current default)
- GPT-5 series: Reasoning models with reasoning_effort/verbosity (future)
"""

from collections.abc import AsyncGenerator
from typing import TypeVar

import instructor
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from alfred.config import core_settings as settings
from alfred.llm.model_router import get_node_config
from alfred.llm.prompt_logger import log_prompt
from alfred.observability.langsmith import get_session_tracker

# Type variable for generic structured output
T = TypeVar("T", bound=BaseModel)


def _sanitize_text(text: str) -> str:
    """Remove surrogate characters that break UTF-8 encoding."""
    return text.encode("utf-8", errors="replace").decode("utf-8")

# Singleton client instances
_client: instructor.Instructor | None = None
_raw_async_client: AsyncOpenAI | None = None

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


def get_raw_async_client() -> AsyncOpenAI:
    """
    Get a raw async OpenAI client (no Instructor wrapping).

    Used by bypass modes for unstructured chat completions
    and streaming. Singleton pattern.
    """
    global _raw_async_client

    if _raw_async_client is None:
        _raw_async_client = AsyncOpenAI(api_key=settings.openai_api_key)

    return _raw_async_client


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
        print(result.agent)  # "main"
    """
    client = get_client()

    # Get node-specific config
    config = get_node_config(_current_node, complexity)

    # Apply verbosity override if provided
    if verbosity_override:
        config["verbosity"] = verbosity_override

    # Extract model name for the API call
    model = config.pop("model", "gpt-4.1-mini")

    # Sanitize prompts to prevent surrogate encoding errors
    system_prompt = _sanitize_text(system_prompt)
    user_prompt = _sanitize_text(user_prompt)

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

    # Handle model-specific parameters
    if model.startswith("o1"):
        # o1 models require temperature=1 and use reasoning_effort
        api_kwargs["temperature"] = 1.0
        if "reasoning_effort" in config:
            api_kwargs["reasoning_effort"] = config["reasoning_effort"]
    elif not model.startswith("gpt-5"):
        # Standard models use temperature
        temperature = config.get("temperature", 0.5)
        api_kwargs["temperature"] = temperature
    # GPT-5 models use reasoning_effort without temperature

    try:
        # Make the call with Instructor (get raw completion for token tracking)
        response, completion = client.chat.completions.create_with_completion(**api_kwargs)

        # Track token usage and costs
        usage = getattr(completion, "usage", None)
        if usage:
            tracker = get_session_tracker()
            tracker.add(
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                node=_current_node,
            )

        # Log the prompt + response
        log_prompt(
            node=_current_node,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model.__name__,
            response=response,
            config=config,  # Include reasoning/verbosity for debugging
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
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


def _build_chat_kwargs(
    messages: list[dict[str, str]],
    config: dict,
    model: str,
    *,
    stream: bool = False,
) -> dict:
    """Build API kwargs for raw chat completions (shared by chat/chat_stream)."""
    # Sanitize all message content to prevent surrogate encoding errors
    safe_messages = [
        {**m, "content": _sanitize_text(m["content"])} if "content" in m else m
        for m in messages
    ]
    api_kwargs: dict = {
        "model": model,
        "messages": safe_messages,
        "stream": stream,
        "store": False,
    }

    # Handle model-specific parameters (same logic as call_llm)
    if model.startswith("o1"):
        api_kwargs["temperature"] = 1.0
        if "reasoning_effort" in config:
            api_kwargs["reasoning_effort"] = config["reasoning_effort"]
    elif not model.startswith("gpt-5"):
        api_kwargs["temperature"] = config.get("temperature", 0.5)

    return api_kwargs


async def call_llm_chat(
    *,
    messages: list[dict[str, str]],
    complexity: str = "low",
    node_name: str = "bypass",
) -> str:
    """
    Multi-turn chat completion without structured output.

    Used by bypass modes for conversational responses
    and by the handoff summarizer.

    Args:
        messages: Full messages array [{"role": "system", ...}, ...]
        complexity: Model selection ("low" = gpt-4.1-mini)
        node_name: Node identifier for config/logging

    Returns:
        Raw text response.
    """
    client = get_raw_async_client()
    config = get_node_config(node_name, complexity)
    model = config.pop("model", "gpt-4.1-mini")

    api_kwargs = _build_chat_kwargs(messages, config, model)
    system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_prompt = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    try:
        response = await client.chat.completions.create(**api_kwargs)
        text = response.choices[0].message.content or ""

        # Log for observability
        log_prompt(
            node=node_name,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model="chat",
            response=text,
            config=config,
        )

        return text

    except Exception as e:
        log_prompt(
            node=node_name,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model="chat",
            error=str(e),
            config=config,
        )
        raise


async def call_llm_chat_stream(
    *,
    messages: list[dict[str, str]],
    complexity: str = "low",
    node_name: str = "bypass",
) -> AsyncGenerator[str, None]:
    """
    Streaming multi-turn chat completion. Yields token chunks.

    Used by bypass modes for real-time streaming responses.

    Args:
        messages: Full messages array [{"role": "system", ...}, ...]
        complexity: Model selection ("low" = gpt-4.1-mini)
        node_name: Node identifier for config/logging

    Yields:
        Token strings as they arrive from the model.
    """
    client = get_raw_async_client()
    config = get_node_config(node_name, complexity)
    model = config.pop("model", "gpt-4.1-mini")

    api_kwargs = _build_chat_kwargs(messages, config, model, stream=True)
    system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_prompt = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    full_response = ""
    try:
        stream = await client.chat.completions.create(**api_kwargs)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield token

        # Log after stream completes
        log_prompt(
            node=node_name,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model="chat_stream",
            response=full_response,
            config=config,
        )

    except Exception as e:
        log_prompt(
            node=node_name,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model="chat_stream",
            error=str(e),
            config=config,
        )
        raise
