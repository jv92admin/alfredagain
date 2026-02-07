"""
Alfred V2 - Router Node.

The Router classifies user intent and determines:
- Which agent handles the request
- The goal in natural language
- Task complexity for model selection

Now includes conversation context for multi-turn awareness.
"""

from pathlib import Path

from alfred.graph.state import AlfredState, RouterOutput
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_condensed_context


# Load prompt once at module level
_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "router.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    """Load the router system prompt, injecting domain-specific content."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        from alfred.domain import get_current_domain
        raw = _PROMPT_PATH.read_text(encoding="utf-8")
        domain = get_current_domain()
        router_content = domain.get_router_prompt_injection()
        _SYSTEM_PROMPT = raw.replace("{domain_router_content}", router_content)
    return _SYSTEM_PROMPT


async def router_node(state: AlfredState) -> dict:
    """
    Router node - first step in the graph.

    Analyzes the user message and outputs routing decision.
    Now includes condensed conversation context for multi-turn awareness.

    Args:
        state: Current graph state with user_message

    Returns:
        State update with router_output
    """
    user_message = state["user_message"]
    conversation = state.get("conversation", {})

    # Set node name for prompt logging
    set_current_node("router")

    # Build user prompt with conversation context
    context_section = format_condensed_context(conversation)
    
    if context_section and context_section != "*No conversation context yet.*":
        user_prompt = f"""## Conversation Context
{context_section}

---

## Current Message
{user_message}"""
    else:
        user_prompt = user_message

    # Call LLM for routing decision
    # Router uses low complexity - it's a classification task
    result = await call_llm(
        response_model=RouterOutput,
        system_prompt=_get_system_prompt(),
        user_prompt=user_prompt,
        complexity="low",
    )

    return {"router_output": result}

