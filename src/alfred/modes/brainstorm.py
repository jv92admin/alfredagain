"""
Brainstorm mode — creative exploration with pre-loaded kitchen context.

Bypasses the LangGraph graph entirely. 1 LLM call per turn, no tool calls.
Context comes from cached dashboard + profile at entry, plus inventory items,
upcoming meal plans, and @-mentioned entity data resolved by the frontend.

On exit, generates a narrative handoff summary for Plan mode.
"""

import logging
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from alfred.background.profile_builder import (
    format_dashboard_for_prompt,
    format_profile_for_prompt,
    get_cached_dashboard,
    get_cached_profile,
)
from alfred.db.client import get_client
from alfred.llm.client import call_llm_chat_stream
from alfred.modes.handoff import generate_session_handoff

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "prompts" / "brainstorm.md"

# History cap: 40 messages = 20 user/assistant exchanges
_MAX_HISTORY = 40


def _load_brainstorm_prompt(brainstorm_context: str) -> str:
    """Load brainstorm.md and inject kitchen context."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{brainstorm_context}", brainstorm_context)


def _format_inventory_for_prompt(inventory_items: list[dict]) -> str:
    """Format inventory items grouped by location for the brainstorm prompt."""
    if not inventory_items:
        return ""

    by_location: dict[str, list[str]] = {}
    for item in inventory_items:
        loc = item.get("location") or "other"
        name = item.get("name", "Unknown")
        qty = item.get("quantity")
        unit = item.get("unit", "")
        entry = name
        if qty and unit:
            entry = f"{name} ({qty} {unit})"
        by_location.setdefault(loc, []).append(entry)

    lines = ["## CURRENT INVENTORY"]
    for loc in ["fridge", "pantry", "freezer", "counter", "cabinet", "other"]:
        items = by_location.get(loc)
        if items:
            lines.append(f"**{loc.title()}:** {', '.join(items)}")

    return "\n".join(lines)


def _format_meal_plan_for_prompt(meal_plan_rows: list[dict]) -> str:
    """Format upcoming meal plan entries for the brainstorm prompt."""
    if not meal_plan_rows:
        return "## UPCOMING MEAL PLAN\nNothing planned for the next 7 days."

    lines = ["## UPCOMING MEAL PLAN"]
    # Group by date
    by_date: dict[str, list[str]] = {}
    for row in meal_plan_rows:
        d = row.get("date", "")
        meal_type = row.get("meal_type", "meal")
        recipe_name = None
        # Handle joined recipe data
        recipe = row.get("recipes")
        if isinstance(recipe, dict):
            recipe_name = recipe.get("name")
        notes = row.get("notes", "")
        entry = f"{meal_type}: {recipe_name}" if recipe_name else f"{meal_type}: {notes or 'unspecified'}"
        by_date.setdefault(d, []).append(entry)

    for d in sorted(by_date.keys()):
        meals = ", ".join(by_date[d])
        lines.append(f"- **{d}:** {meals}")

    return "\n".join(lines)


async def _init_brainstorm_session(
    conversation: dict,
    user_id: str,
) -> None:
    """Fetch dashboard + profile + inventory + meal plans and initialize brainstorm state."""
    profile = await get_cached_profile(user_id)
    dashboard = await get_cached_dashboard(user_id)

    profile_text = format_profile_for_prompt(profile)
    dashboard_text = format_dashboard_for_prompt(dashboard)

    # Fetch inventory items (names, quantities, locations)
    inventory_text = ""
    try:
        client = get_client()
        inv_result = (
            client.table("inventory")
            .select("name, quantity, unit, location, category")
            .eq("user_id", user_id)
            .execute()
        )
        if inv_result.data:
            inventory_text = _format_inventory_for_prompt(inv_result.data)
    except Exception as e:
        logger.warning(f"Failed to fetch inventory for brainstorm: {e}")

    # Fetch upcoming meal plans (next 7 days, with recipe names)
    meal_plan_text = ""
    try:
        client = get_client()
        today = date.today().isoformat()
        week_later = (date.today() + timedelta(days=7)).isoformat()
        meal_result = (
            client.table("meal_plans")
            .select("date, meal_type, notes, recipes(name)")
            .eq("user_id", user_id)
            .gte("date", today)
            .lte("date", week_later)
            .order("date")
            .execute()
        )
        if meal_result.data:
            meal_plan_text = _format_meal_plan_for_prompt(meal_result.data)
        else:
            meal_plan_text = "## UPCOMING MEAL PLAN\nNothing planned for the next 7 days."
    except Exception as e:
        logger.warning(f"Failed to fetch meal plans for brainstorm: {e}")

    # Assemble full context
    parts = [p for p in [profile_text, dashboard_text, inventory_text, meal_plan_text] if p]
    brainstorm_context = "\n\n".join(parts)

    conversation["active_mode"] = "brainstorm"
    conversation["brainstorm_context"] = brainstorm_context
    conversation["brainstorm_history"] = []


async def run_brainstorm(
    user_message: str,
    user_id: str,
    conversation: dict,
    brainstorm_init: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Brainstorm mode runtime. Yields SSE-compatible events.

    First turn: pass brainstorm_init=True to load dashboard + profile.
    Subsequent turns: pass user_message with existing brainstorm state.
    Exit: pass user_message="__brainstorm_exit__" to generate handoff and close.
    """
    # --- Init on first turn ---
    if brainstorm_init:
        try:
            await _init_brainstorm_session(conversation, user_id)
        except Exception as e:
            logger.error(f"Failed to init brainstorm: {e}")
            yield {"type": "error", "error": "Couldn't start brainstorm. Try again."}
            return

    # --- Exit ---
    if user_message == "__brainstorm_exit__":
        brainstorm_history = conversation.get("brainstorm_history", [])

        if brainstorm_history:
            handoff = await generate_session_handoff("brainstorm", brainstorm_history)
            # Auto-inject if save/update
            if handoff.action in ("save", "update"):
                recent_turns = conversation.setdefault("recent_turns", [])
                # Include recipe_content in the turn so Plan/Think can act on it
                assistant_text = handoff.summary
                if handoff.recipe_content:
                    assistant_text += f"\n\n---\n\n{handoff.recipe_content}"
                recent_turns.append({
                    "user": "[Brainstorm session]",
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
                "summary": "Started brainstorm but didn't explore any ideas.",
                "action": "close",
                "action_detail": "No brainstorm activity.",
            }

        # Clear brainstorm state
        conversation.pop("brainstorm_context", None)
        conversation.pop("brainstorm_history", None)
        conversation["active_mode"] = "plan"

        yield {"type": "done", "response": "", "conversation": conversation}
        return

    # --- Chat turn ---
    brainstorm_context = conversation.get("brainstorm_context", "")
    brainstorm_history = conversation.get("brainstorm_history", [])

    if not brainstorm_context:
        yield {"type": "error", "error": "Not in brainstorm mode. Start a session first."}
        return

    system_prompt = _load_brainstorm_prompt(brainstorm_context)
    messages = [
        {"role": "system", "content": system_prompt},
        *brainstorm_history,
        {"role": "user", "content": user_message},
    ]

    full_response = ""
    try:
        async for token in call_llm_chat_stream(
            messages=messages,
            complexity="low",
            node_name="brainstorm",
        ):
            full_response += token
            yield {"type": "chunk", "content": token}
    except Exception as e:
        logger.error(f"Brainstorm LLM call failed: {e}")
        yield {"type": "error", "error": "Something went wrong. Try again or exit brainstorm."}
        return

    # Update history
    brainstorm_history.append({"role": "user", "content": user_message})
    brainstorm_history.append({"role": "assistant", "content": full_response})

    # Cap history
    if len(brainstorm_history) > _MAX_HISTORY:
        brainstorm_history[:] = brainstorm_history[-_MAX_HISTORY:]

    conversation["brainstorm_history"] = brainstorm_history

    yield {"type": "done", "response": full_response, "conversation": conversation}
