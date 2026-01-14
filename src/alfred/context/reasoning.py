"""
Alfred Context API - Layer 3: Reasoning Trace.

Provides structured access to LLM decisions and execution history.

This is the NEW layer that captures:
- What Think decided (goal, decision type)
- What steps executed (outcomes, notes)
- What Understand curated (retained, demoted)
- Conversation flow (phase, user expressed)

Built by Summarize at end of each turn, stored in conversation["turn_summaries"].
"""

from dataclasses import dataclass, field


@dataclass
class StepSummary:
    """Summary of a single step execution."""
    
    step_num: int
    step_type: str               # "read" | "analyze" | "generate" | "write"
    subdomain: str
    description: str             # From plan
    outcome: str                 # "Found 5 recipes" | "Generated 3 options"
    entities_involved: list[str] = field(default_factory=list)  # Refs touched
    note: str | None = None      # Act's note_for_next_step


@dataclass
class CurationSummary:
    """Summary of Understand's entity curation decisions."""
    
    retained: list[str] = field(default_factory=list)   # Refs explicitly kept
    demoted: list[str] = field(default_factory=list)    # Refs no longer active
    reasons: dict[str, str] = field(default_factory=dict)  # ref -> reason


@dataclass
class TurnSummary:
    """
    Summary of what happened in a single turn.
    
    Built by Summarize from:
    - think_output (goal, decision)
    - step_results (outcomes)
    - understand_output (curation)
    - Inferred conversation flow
    """
    
    turn_num: int
    
    # What Think decided
    think_decision: str = ""     # "plan_direct" | "propose" | "clarify"
    think_goal: str = ""         # "Find vegetarian recipes"
    
    # What steps executed
    steps: list[StepSummary] = field(default_factory=list)
    
    # Understand's curation this turn
    entity_curation: CurationSummary = field(default_factory=CurationSummary)
    
    # Conversation flow metadata
    conversation_phase: str = ""  # "exploring" | "narrowing" | "confirming" | "executing"
    user_expressed: str = ""      # "wants variety" | "prefers quick meals"


@dataclass
class ReasoningTrace:
    """
    Structured reasoning trace for prompt injection.
    
    Provides:
    - recent_summaries: Last 2 turns of execution detail
    - reasoning_summary: Compressed older reasoning
    """
    
    recent_summaries: list[TurnSummary] = field(default_factory=list)
    reasoning_summary: str = ""


def get_reasoning_trace(conversation: dict) -> ReasoningTrace:
    """
    Build reasoning trace from stored turn summaries.
    
    Args:
        conversation: ConversationContext dict from state
    
    Returns:
        ReasoningTrace with structured data
    """
    trace = ReasoningTrace(
        reasoning_summary=conversation.get("reasoning_summary", ""),
    )
    
    # Build from turn_summaries (populated by Summarize in Phase 3)
    turn_summaries_raw = conversation.get("turn_summaries", [])
    for ts in turn_summaries_raw:
        summary = TurnSummary(
            turn_num=ts.get("turn_num", 0),
            think_decision=ts.get("think_decision", ""),
            think_goal=ts.get("think_goal", ""),
            conversation_phase=ts.get("conversation_phase", ""),
            user_expressed=ts.get("user_expressed", ""),
        )
        
        # Build steps
        for step_raw in ts.get("steps", []):
            summary.steps.append(StepSummary(
                step_num=step_raw.get("step_num", 0),
                step_type=step_raw.get("step_type", ""),
                subdomain=step_raw.get("subdomain", ""),
                description=step_raw.get("description", ""),
                outcome=step_raw.get("outcome", ""),
                entities_involved=step_raw.get("entities_involved", []),
                note=step_raw.get("note"),
            ))
        
        # Build curation
        curation_raw = ts.get("entity_curation", {})
        summary.entity_curation = CurationSummary(
            retained=curation_raw.get("retained", []),
            demoted=curation_raw.get("demoted", []),
            reasons=curation_raw.get("reasons", {}),
        )
        
        trace.recent_summaries.append(summary)
    
    return trace


def get_current_turn_curation(state: dict) -> CurationSummary | None:
    """
    Get Understand's curation decisions from current turn.
    
    This is for SAME-TURN context (before Summarize runs).
    Reads from understand_output if available.
    """
    understand_output = state.get("understand_output")
    if not understand_output:
        return None
    
    # Handle both Pydantic model and dict
    if hasattr(understand_output, "entity_curation"):
        curation = understand_output.entity_curation
        if curation:
            return CurationSummary(
                retained=[r.ref for r in getattr(curation, "retain_active", [])],
                demoted=getattr(curation, "demote", []),
                reasons={r.ref: r.reason for r in getattr(curation, "retain_active", [])},
            )
    elif isinstance(understand_output, dict):
        curation = understand_output.get("entity_curation", {})
        if curation:
            retain_active = curation.get("retain_active", [])
            return CurationSummary(
                retained=[r.get("ref", "") for r in retain_active],
                demoted=curation.get("demote", []),
                reasons={r.get("ref", ""): r.get("reason", "") for r in retain_active},
            )
    
    return None


def format_reasoning(trace: ReasoningTrace, node: str = "think") -> str:
    """
    Format reasoning trace for prompt injection.
    
    Args:
        trace: ReasoningTrace to format
        node: Which node is consuming this
            - "think": Full detail on last turn, step summaries
            - "act": Current turn steps only (handled separately)
            - "reply": Outcomes only, conversation phase
    
    Returns:
        Formatted string for prompt injection
    """
    lines = []
    
    # Compressed older reasoning
    if trace.reasoning_summary:
        lines.append(f"**Earlier context:** {trace.reasoning_summary}")
        lines.append("")
    
    if not trace.recent_summaries:
        if not lines:
            return "No prior reasoning context."
        return "\n".join(lines).strip()
    
    # Format based on consuming node
    if node == "think":
        lines.append("### Last Turn Summary")
        for ts in trace.recent_summaries[-2:]:  # Last 2 turns
            lines.append(f"**Turn {ts.turn_num}:** {ts.think_goal}")
            lines.append(f"- Decision: {ts.think_decision}")
            if ts.conversation_phase:
                lines.append(f"- Phase: {ts.conversation_phase}")
            if ts.user_expressed:
                lines.append(f"- User expressed: {ts.user_expressed}")
            
            # Step outcomes
            if ts.steps:
                lines.append("- Steps executed:")
                for step in ts.steps:
                    lines.append(f"  - {step.step_type}: {step.outcome}")
                    if step.entities_involved:
                        lines.append(f"    Entities: {', '.join(step.entities_involved)}")
            
            # Curation
            if ts.entity_curation.demoted:
                lines.append(f"- Demoted: {', '.join(ts.entity_curation.demoted)}")
            
            lines.append("")
    
    elif node == "reply":
        # Just outcomes and phase for Reply
        for ts in trace.recent_summaries[-1:]:  # Last turn only
            if ts.conversation_phase:
                lines.append(f"**Phase:** {ts.conversation_phase}")
            if ts.user_expressed:
                lines.append(f"**User expressed:** {ts.user_expressed}")
            
            # What was accomplished
            if ts.steps:
                outcomes = [f"{s.step_type}: {s.outcome}" for s in ts.steps]
                lines.append(f"**Accomplished:** {'; '.join(outcomes)}")
    
    return "\n".join(lines).strip() if lines else "No prior reasoning context."


def format_curation_for_think(curation: CurationSummary | None) -> str:
    """
    Format current turn's curation decisions for Think prompt.
    
    Shows what Understand decided this turn (before Think runs).
    """
    if not curation:
        return ""
    
    lines = []
    
    if curation.retained:
        lines.append("### Understand's Decisions (This Turn)")
        lines.append("**Retained (still relevant):**")
        for ref in curation.retained:
            reason = curation.reasons.get(ref, "")
            lines.append(f"- `{ref}`: {reason}" if reason else f"- `{ref}`")
    
    if curation.demoted:
        lines.append("**Demoted (no longer active):**")
        for ref in curation.demoted:
            lines.append(f"- `{ref}`")
    
    return "\n".join(lines) if lines else ""
