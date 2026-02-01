"""
Cook mode — guided cooking session with frozen recipe context.

Bypasses the LangGraph graph entirely. 1 LLM call per turn.
On exit, generates a narrative handoff summary for Plan mode.
"""

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from alfred.background.profile_builder import format_profile_for_prompt, get_cached_profile
from alfred.llm.client import call_llm_chat_stream
from alfred.modes.handoff import generate_session_handoff
from alfred.tools.crud import db_read, DbReadParams, FilterClause

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "prompts" / "cook.md"

# History cap: 20 messages = 10 user/assistant exchanges
_MAX_HISTORY = 20


def _load_cook_prompt(cook_context: str, user_profile: str = "") -> str:
    """Load cook.md and inject frozen recipe context + user profile."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{cook_context}", cook_context).replace("{user_profile}", user_profile)


def _format_recipe_context(recipe: dict, notes: str = "") -> str:
    """Format a recipe dict into a readable context string for the LLM."""
    parts = [f"# {recipe.get('name', 'Unknown Recipe')}"]

    if recipe.get("description"):
        parts.append(f"\n{recipe['description']}")

    if recipe.get("cuisine"):
        parts.append(f"\nCuisine: {recipe['cuisine']}")

    if recipe.get("servings"):
        parts.append(f"Servings: {recipe['servings']}")

    times = []
    if recipe.get("prep_time_minutes"):
        times.append(f"Prep: {recipe['prep_time_minutes']} min")
    if recipe.get("cook_time_minutes"):
        times.append(f"Cook: {recipe['cook_time_minutes']} min")
    if times:
        parts.append(" | ".join(times))

    # Ingredients (from auto-joined recipe_ingredients)
    ingredients = recipe.get("recipe_ingredients", [])
    if ingredients:
        parts.append("\n## Ingredients")
        for ing in ingredients:
            name = ing.get("name", "Unknown")
            parts.append(f"- {name}")

    # Instructions (TEXT[] — array of steps)
    instructions = recipe.get("instructions", [])
    if instructions:
        parts.append("\n## Instructions")
        for i, step in enumerate(instructions, 1):
            parts.append(f"{i}. {step}")

    if notes:
        parts.append(f"\n## Your Notes\n{notes}")

    return "\n".join(parts)


async def _init_cook_session(
    conversation: dict,
    cook_init: dict,
    user_id: str,
) -> str | None:
    """Fetch recipe and initialize cook session state. Returns error message or None."""
    recipe_id = cook_init.get("recipe_id")
    notes = cook_init.get("notes", "")

    if not recipe_id:
        return "No recipe selected. Pick a recipe to start cooking."

    try:
        results = await db_read(
            DbReadParams(
                table="recipes",
                filters=[FilterClause(field="id", op="=", value=recipe_id)],
            ),
            user_id,
        )
    except Exception as e:
        logger.error(f"Failed to fetch recipe {recipe_id}: {e}")
        return f"Couldn't load that recipe — try again or pick a different one."

    if not results:
        return "Recipe not found. It may have been deleted."

    recipe = results[0]
    cook_context = _format_recipe_context(recipe, notes)

    # Fetch user profile for dietary restrictions / preferences
    user_profile_text = ""
    try:
        profile = await get_cached_profile(user_id)
        user_profile_text = format_profile_for_prompt(profile)
    except Exception as e:
        logger.warning(f"Failed to fetch profile for cook mode: {e}")

    conversation["active_mode"] = "cook"
    conversation["cook_context"] = cook_context
    conversation["cook_profile"] = user_profile_text
    conversation["cook_history"] = []
    conversation["cook_recipe_name"] = recipe.get("name", "Unknown Recipe")

    return None


async def run_cook_session(
    user_message: str,
    user_id: str,
    conversation: dict,
    cook_init: dict | None = None,
    access_token: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Cook mode runtime. Yields SSE-compatible events.

    First turn: pass cook_init to fetch recipe and initialize.
    Subsequent turns: pass user_message with existing cook state.
    Exit: pass user_message="__cook_exit__" to generate handoff and close.
    """
    # --- Init on first turn ---
    if cook_init:
        error = await _init_cook_session(conversation, cook_init, user_id)
        if error:
            yield {"type": "error", "error": error}
            return

    # --- Exit ---
    if user_message == "__cook_exit__":
        cook_history = conversation.get("cook_history", [])
        recipe_name = conversation.get("cook_recipe_name", "a recipe")

        if cook_history:
            handoff = await generate_session_handoff("cook", cook_history)
            # Auto-inject if save/update
            if handoff.action in ("save", "update"):
                recent_turns = conversation.setdefault("recent_turns", [])
                # Include recipe_content in the turn so Plan/Think can act on it
                assistant_text = handoff.summary
                if handoff.recipe_content:
                    assistant_text += f"\n\n---\n\n{handoff.recipe_content}"
                recent_turns.append({
                    "user": f"[Cook session: {recipe_name}]",
                    "assistant": assistant_text,
                    # Pre-set assistant_summary to bypass conversation.py's
                    # summarizer, which detects recipe patterns and replaces
                    # with "[Content archived]". Think only sees
                    # assistant_summary, so it must contain the full recipe.
                    "assistant_summary": assistant_text,
                })
            yield {
                "type": "handoff",
                "summary": handoff.summary,
                "action": handoff.action,
                "action_detail": handoff.action_detail,
                "recipe_content": handoff.recipe_content,
            }
        else:
            yield {
                "type": "handoff",
                "summary": f"Started cook mode for {recipe_name} but didn't cook.",
                "action": "close",
                "action_detail": "No cooking activity.",
            }

        # Clear cook state
        conversation.pop("cook_context", None)
        conversation.pop("cook_profile", None)
        conversation.pop("cook_history", None)
        conversation.pop("cook_recipe_name", None)
        conversation["active_mode"] = "plan"

        yield {"type": "done", "response": "", "conversation": conversation}
        return

    # --- Chat turn ---
    cook_context = conversation.get("cook_context", "")
    cook_profile = conversation.get("cook_profile", "")
    cook_history = conversation.get("cook_history", [])

    if not cook_context:
        yield {"type": "error", "error": "Not in cook mode. Start a cook session first."}
        return

    system_prompt = _load_cook_prompt(cook_context, cook_profile)
    messages = [
        {"role": "system", "content": system_prompt},
        *cook_history,
        {"role": "user", "content": user_message},
    ]

    full_response = ""
    try:
        async for token in call_llm_chat_stream(
            messages=messages,
            complexity="low",
            node_name="cook",
        ):
            full_response += token
            yield {"type": "chunk", "content": token}
    except Exception as e:
        logger.error(f"Cook LLM call failed: {e}")
        yield {"type": "error", "error": "Something went wrong. Try again or exit cook mode."}
        return

    # Update history
    cook_history.append({"role": "user", "content": user_message})
    cook_history.append({"role": "assistant", "content": full_response})

    # Cap history
    if len(cook_history) > _MAX_HISTORY:
        cook_history[:] = cook_history[-_MAX_HISTORY:]

    conversation["cook_history"] = cook_history

    yield {"type": "done", "response": full_response, "conversation": conversation}
