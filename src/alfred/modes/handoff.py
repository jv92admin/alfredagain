"""
Session handoff — generates narrative summary + action recommendation on mode exit.

Used by both Cook and Brainstorm modes. The handoff is the ONE place these
lightweight modes use structured output, because the frontend needs to branch
on the recommended action.
"""

from typing import Literal

from pydantic import BaseModel, Field

from alfred.llm.client import call_llm, set_current_node


class HandoffResult(BaseModel):
    """Structured result from session handoff LLM call."""

    summary: str = Field(
        description=(
            "2-4 sentence narrative summary of the session — what was discussed, "
            "key decisions, and outcome. Keep this concise; full recipe details "
            "go in recipe_content instead."
        )
    )
    action: Literal["save", "update", "close"] = Field(
        description=(
            "'save' if new content worth persisting (recipe idea, modifications). "
            "'update' if changes to existing entities were discussed. "
            "'close' if purely conversational, nothing to persist."
        )
    )
    action_detail: str = Field(
        description="What specifically to save/update, or why closing."
    )
    recipe_content: str | None = Field(
        default=None,
        description=(
            "If a complete recipe was developed or significantly modified during "
            "the session, include it here VERBATIM — name, ingredients with "
            "quantities, full method/steps. This gets passed to Plan mode for "
            "saving. Include multiple recipes separated by '---' if several were "
            "developed. null if no recipe content to preserve."
        ),
    )


_HANDOFF_SYSTEM_PROMPTS = {
    "cook": (
        "Summarize this cooking session.\n\n"
        "summary: 2-4 sentences — recipe cooked, any modifications the user made "
        "(substitutions, timing changes, technique adjustments), and observations "
        "worth remembering. Write in the user's voice.\n\n"
        "recipe_content: If the user developed a significant variant or new recipe "
        "during cooking, include it here with name, ingredients, and method. "
        "If they just followed the existing recipe with minor tweaks, leave null.\n\n"
        "Recommend an action:\n"
        "- 'save' if the user developed a variant worth saving as a new recipe\n"
        "- 'update' if they noted changes to the existing recipe\n"
        "- 'close' if it was a normal cook-through with no notable changes"
    ),
    "brainstorm": (
        "Summarize the ideas developed in this brainstorm session.\n\n"
        "summary: 2-4 sentences covering what was explored and key decisions. "
        "Keep this concise — recipe details go in recipe_content.\n\n"
        "recipe_content: If recipe concepts were developed, include them here "
        "IN FULL — name, ingredients with quantities, method/steps, and why it "
        "works for the user. Do NOT compress or summarize recipes. If multiple "
        "recipes were developed, include all of them separated by '---'. "
        "Write in the user's language — if they used casual descriptions, keep "
        "that tone. null if no concrete recipes emerged.\n\n"
        "For non-recipe ideas (technique notes, meal planning decisions, "
        "ingredient discoveries), capture specifics in the summary.\n\n"
        "Recommend an action:\n"
        "- 'save' if concrete recipe ideas or menu concepts emerged\n"
        "- 'update' if the user wants to modify existing recipes\n"
        "- 'close' if purely exploratory, nothing specific to persist"
    ),
}


async def generate_session_handoff(
    mode: str,
    session_history: list[dict[str, str]],
) -> HandoffResult:
    """
    Generate a narrative handoff summary from a Cook or Brainstorm session.

    Makes 1 structured LLM call using Instructor. Returns a HandoffResult
    with summary text and recommended action.

    Args:
        mode: "cook" or "brainstorm"
        session_history: Messages array from the session [{"role": "user", ...}, ...]

    Returns:
        HandoffResult with summary, action, and action_detail.
    """
    system_prompt = _HANDOFF_SYSTEM_PROMPTS[mode]

    # Build user prompt from session history
    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in session_history
    )

    set_current_node("handoff")
    return await call_llm(
        response_model=HandoffResult,
        system_prompt=system_prompt,
        user_prompt=history_text,
        complexity="low",
    )
