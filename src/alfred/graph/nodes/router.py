"""
Alfred V2 - Router Node.

The Router classifies user intent and determines:
- Which agent handles the request
- The goal in natural language
- Task complexity for model selection
- What context data is needed
"""

from pathlib import Path

from alfred.graph.state import AlfredState, RouterOutput
from alfred.llm.client import call_llm


# Load prompt once at module level
_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "router.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    """Load the router system prompt."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


async def router_node(state: AlfredState) -> dict:
    """
    Router node - first step in the graph.

    Analyzes the user message and outputs routing decision.

    Args:
        state: Current graph state with user_message

    Returns:
        State update with router_output
    """
    user_message = state["user_message"]

    # Call LLM for routing decision
    # Router uses low complexity - it's a classification task
    result = await call_llm(
        response_model=RouterOutput,
        system_prompt=_get_system_prompt(),
        user_prompt=user_message,
        complexity="low",
    )

    return {"router_output": result}

