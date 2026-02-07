"""
Session handoff — generates narrative summary + action recommendation on mode exit.

Used by bypass modes (cook, brainstorm, etc.). The handoff is the ONE place these
lightweight modes use structured output, because the frontend needs to branch
on the recommended action.

The HandoffResult model and system prompts are domain-specific, sourced via
DomainConfig.get_handoff_result_model() and get_handoff_system_prompts().
"""

from pydantic import BaseModel

from alfred.llm.client import call_llm, set_current_node


async def generate_session_handoff(
    mode: str,
    session_history: list[dict[str, str]],
) -> BaseModel:
    """
    Generate a narrative handoff summary from a bypass mode session.

    Makes 1 structured LLM call using Instructor. Returns a domain-specific
    HandoffResult with summary text and recommended action.

    Args:
        mode: Bypass mode name (e.g., "cook", "brainstorm")
        session_history: Messages array from the session [{"role": "user", ...}, ...]

    Returns:
        Domain-specific HandoffResult (BaseModel subclass).
    """
    from alfred.domain import get_current_domain
    domain = get_current_domain()

    result_model = domain.get_handoff_result_model()
    system_prompts = domain.get_handoff_system_prompts()
    system_prompt = system_prompts.get(mode, "Summarize this session.")

    # Build user prompt from session history
    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in session_history
    )

    set_current_node("handoff")
    return await call_llm(
        response_model=result_model,
        system_prompt=system_prompt,
        user_prompt=history_text,
        complexity="low",
    )
