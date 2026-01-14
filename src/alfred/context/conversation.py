"""
Alfred Context API - Layer 2: Conversation History.

Provides structured access to conversation turns and summaries.

Components:
- Recent turns: Full detail (last 2 turns)
- History summary: Compressed older turns
- Engagement summary: Overall session theme
- Pending state: Awaiting user response
"""

from dataclasses import dataclass, field


@dataclass
class ConversationTurn:
    """A single conversation exchange."""
    
    user: str                    # User's message
    assistant_summary: str       # Condensed assistant response
    turn_num: int = 0            # Which turn this was
    routing: dict | None = None  # Router decision (agent, goal, complexity)


@dataclass
class PendingState:
    """Tracks pending user response."""
    
    type: str                    # "propose" | "clarify" | "ask_user"
    context: str                 # What was proposed/asked
    questions: list[str] = field(default_factory=list)  # Specific questions


@dataclass
class ConversationHistory:
    """
    Structured conversation history for prompt injection.
    
    Provides:
    - recent_turns: Full detail for last N turns
    - history_summary: Compressed older turns
    - engagement_summary: Overall session theme
    - pending: What we're waiting for user to respond to
    """
    
    recent_turns: list[ConversationTurn] = field(default_factory=list)
    history_summary: str = ""
    engagement_summary: str = ""
    pending: PendingState | None = None
    current_turn: int = 0


def get_conversation_history(conversation: dict) -> ConversationHistory:
    """
    Build conversation history from stored conversation context.
    
    Args:
        conversation: ConversationContext dict from state
    
    Returns:
        ConversationHistory with structured data
    """
    history = ConversationHistory(
        current_turn=conversation.get("current_turn", 0),
        history_summary=conversation.get("history_summary", ""),
        engagement_summary=conversation.get("engagement_summary", ""),
    )
    
    # Build recent turns
    recent_turns_raw = conversation.get("recent_turns", [])
    for i, turn in enumerate(recent_turns_raw):
        history.recent_turns.append(ConversationTurn(
            user=turn.get("user", ""),
            assistant_summary=turn.get("assistant_summary") or turn.get("assistant", "")[:200],
            turn_num=history.current_turn - len(recent_turns_raw) + i + 1,
            routing=turn.get("routing"),
        ))
    
    # Build pending state
    pending_raw = conversation.get("pending_clarification")
    if pending_raw:
        history.pending = PendingState(
            type=pending_raw.get("type", ""),
            context=pending_raw.get("goal", "") or pending_raw.get("proposal_message", ""),
            questions=pending_raw.get("questions") or [],
        )
    
    return history


def format_conversation(
    history: ConversationHistory,
    depth: int = 2,
    include_pending: bool = True,
) -> str:
    """
    Format conversation history for prompt injection.
    
    Args:
        history: ConversationHistory to format
        depth: How many recent turns to include (2 = last 2)
        include_pending: Whether to show pending state
    
    Returns:
        Formatted string for prompt injection
    """
    lines = []
    
    # Engagement summary (if any)
    if history.engagement_summary:
        lines.append(f"**Session:** {history.engagement_summary}")
        lines.append("")
    
    # History summary (compressed older turns)
    if history.history_summary:
        lines.append(f"**Earlier:** {history.history_summary}")
        lines.append("")
    
    # Recent turns
    turns_to_show = history.recent_turns[-depth:] if depth > 0 else history.recent_turns
    if turns_to_show:
        lines.append("### Recent Conversation")
        for turn in turns_to_show:
            lines.append(f"**User:** {turn.user}")
            lines.append(f"**Assistant:** {turn.assistant_summary}")
            lines.append("")
    
    # Pending state
    if include_pending and history.pending:
        lines.append("### Awaiting Response")
        lines.append(f"- **Type:** {history.pending.type}")
        if history.pending.context:
            lines.append(f"- **Context:** {history.pending.context}")
        if history.pending.questions:
            lines.append(f"- **Questions:** {', '.join(history.pending.questions)}")
        lines.append("")
    
    # Turn counter
    if history.current_turn > 0:
        lines.append(f"*Current turn: {history.current_turn}*")
    
    if not lines:
        return "New conversation."
    
    return "\n".join(lines).strip()


def format_conversation_brief(history: ConversationHistory) -> str:
    """
    Format brief conversation context (for Act).
    
    Shows only last exchange, no history summary.
    """
    lines = []
    
    if history.recent_turns:
        last = history.recent_turns[-1]
        lines.append(f"**Last exchange:**")
        lines.append(f"User: {last.user[:150]}...")
        lines.append(f"Assistant: {last.assistant_summary[:150]}...")
    
    return "\n".join(lines) if lines else "First turn."
