"""
Alfred V3 - Graph State Definition.

The AlfredState is the shared state passed through all nodes.

V3 Architecture:
- ThinkStep uses V3 step types: read, analyze, generate, write
- Group-based parallelization (same group = can run in parallel)
- UnderstandOutput for entity state management
- EntityRegistry integration for lifecycle tracking
- ModeContext for complexity adaptation
"""

from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, model_validator

from alfred.core.modes import Mode, ModeContext


# =============================================================================
# Context Token Thresholds
# =============================================================================

# Router and Think get condensed context (fast routing/planning)
ROUTER_CONTEXT_THRESHOLD = 8_000  # tokens

# Act gets full recent context (needs details for execution)
ACT_CONTEXT_THRESHOLD = 25_000  # tokens (we have 400K window)

# How many turns/steps to keep in full detail
FULL_DETAIL_TURNS = 3  # Last 3 conversation turns
FULL_DETAIL_STEPS = 3  # Last 3 step results (important for multi-step flows)


# =============================================================================
# Entity Reference Pattern
# =============================================================================


class EntityRef(BaseModel):
    """
    Safe object reference used throughout the system.

    Rules:
    - Tools always return EntityRefs
    - Tools accept IDs, not raw strings
    - LLMs never fabricate IDs
    """

    type: str  # "ingredient", "recipe", "meal_plan", "inventory_item"
    id: str  # UUID
    label: str  # Human-readable for LLM context
    source: str  # "db_lookup", "user_input", "generated"
    step_index: int | None = None  # Which step this came from (for retrieval)


# =============================================================================
# Core Contracts
# =============================================================================


class RouterOutput(BaseModel):
    """Output from the Router node."""

    agent: Literal["pantry", "coach", "cellar"]
    goal: str  # Natural language
    complexity: Literal["low", "medium", "high"]
    # NOTE: No context_needs - Act handles ALL data access via CRUD


# =============================================================================
# V3 Step Types
# =============================================================================


class ThinkStep(BaseModel):
    """
    Step definition with group-based parallelization.
    
    Steps in the same group have no dependencies and can run in parallel.
    Groups execute in order: 0 → 1 → 2 → ...
    
    Simplified in V4.1: Removed unused fields (data_requirements, referenced_entities,
    input_from_steps). Entity tracking is handled by SessionIdRegistry.
    """
    
    description: str  # Natural language step description
    step_type: Literal["read", "analyze", "generate", "write"]
    subdomain: str  # "inventory", "recipes", "shopping", "meal_plans", "preferences"
    group: int = 0  # Execution group (same group = can run in parallel)
    
    @property
    def complexity(self) -> str:
        """Map step_type to complexity for model selection."""
        if self.step_type in ("read", "write"):
            return "low"
        elif self.step_type == "analyze":
            return "medium"
        else:  # generate
            return "high"


# =============================================================================
# V3 Node Outputs
# =============================================================================


# =============================================================================
# V4 Understand Models
# =============================================================================


class EntityMention(BaseModel):
    """
    V4: A structured entity mention from user input.
    
    Represents a user's reference to an entity with resolution info.
    """
    
    text: str  # Raw text from user ("that recipe", "the cod dish")
    entity_type: str | None = None  # Inferred type (recipe, meal_plan, etc.)
    
    # Resolution result
    resolution: Literal["exact", "inferred", "ambiguous", "unknown"] = "unknown"
    resolved_id: str | None = None  # Resolved entity ID if successful
    confidence: float = 0.0  # 0.0-1.0
    
    # For ambiguous cases
    candidates: list[str] = Field(default_factory=list)  # Candidate entity IDs
    disambiguation_reason: str | None = None  # Why it's ambiguous


class TurnConstraintSnapshot(BaseModel):
    """
    V4: Constraints detected in this turn's input.
    
    These get merged into SessionConstraints deterministically.
    """
    
    # New constraints detected this turn
    new_constraints: list[str] = Field(default_factory=list)  # ["use cod", "no dairy"]
    
    # Constraints that override previous values
    overrides: dict[str, str] = Field(default_factory=dict)  # {"protein": "cod" overrides "salmon"}
    
    # Reset signals
    reset_all: bool = False  # "never mind", "start over"
    reset_subdomain: str | None = None  # Subdomain change resets that domain's constraints


class RetentionDecision(BaseModel):
    """
    V5: Decision to retain an older entity as active.
    
    Used when Understand decides an entity beyond the automatic 2-turn window
    should remain active because it's still relevant to the user's goal.
    """
    ref: str  # Entity ref (e.g., "gen_meal_plan_1")
    reason: str  # Why it's still relevant (e.g., "User's ongoing weekly meal plan goal")


class EntityCurationDecision(BaseModel):
    """
    V5: Understand's decision about entity context curation.
    
    Understand is the memory manager. It decides based on user intent
    what entities should be retained, demoted, or dropped.
    
    V5 Changes:
    - Added `retain_active` with reasons (replaces promote_to_active)
    - Reasons are stored for future Understand agents to read
    """
    
    # V5: Entities to retain as active WITH reasons (beyond automatic 2-turn window)
    # These are older entities that Understand decides are still relevant
    retain_active: list[RetentionDecision] = Field(default_factory=list)
    
    # Entities to demote from active (no longer relevant, but keep in registry)
    demote: list[str] = Field(default_factory=list)
    
    # Entities to drop entirely (user said "forget that", starting fresh)
    drop: list[str] = Field(default_factory=list)
    
    # Clear all context (user said "never mind", "start fresh")
    clear_all: bool = False
    
    # Summary reason for this turn's curation decisions (for decision log)
    curation_summary: str | None = None


class UnderstandOutput(BaseModel):
    """
    Output from the Understand node (V5).
    
    Understand is Alfred's MEMORY MANAGER. It ensures the system remembers
    what matters and forgets what doesn't across multi-turn conversations.
    
    Understand handles:
    - Entity reference resolution ("that recipe" → specific ref)
    - Entity context CURATION (what stays active beyond automatic 2-turn window)
    - Disambiguation detection
    - Quick mode detection (for simple READs)
    
    V5 Changes:
    - REMOVED processed_message (redundant - Think has raw message)
    - EntityCurationDecision now includes retention reasons
    - Retention reasons stored for future Understand agents
    
    Understand does NOT plan steps or rewrite messages.
    """
    
    # Entity state updates (legacy - still supported)
    entity_updates: list[dict] = Field(default_factory=list)  # [{"id": "x", "new_state": "active"}]
    referenced_entities: list[str] = Field(default_factory=list)  # Simple refs user is referring to
    
    # V4: Structured entity mentions
    entity_mentions: list[EntityMention] = Field(default_factory=list)
    
    # V5: ENTITY CURATION - Understand decides what's relevant
    entity_curation: EntityCurationDecision | None = None
    
    # V4: Disambiguation support
    needs_disambiguation: bool = False
    disambiguation_options: list[dict] = Field(default_factory=list)  # [{ref, label, reason}]
    disambiguation_question: str | None = None
    
    # V4: Constraint snapshot (for constraints like "use cod", "no dairy")
    constraint_snapshot: TurnConstraintSnapshot | None = None
    
    # Clarification (when truly ambiguous)
    needs_clarification: bool = False
    clarification_questions: list[str] | None = None
    clarification_reason: str | None = None  # "ambiguous_reference", "missing_info"
    
    # Quick mode detection (for simple single-domain READs)
    quick_mode: bool = False  # True if this is a simple 1-step query
    quick_mode_confidence: float = 0.0  # Confidence gating
    quick_intent: str | None = None  # Plaintext intent: "Show user their inventory"
    quick_subdomain: str | None = None  # Target subdomain: "inventory", "shopping", etc.


class ThinkOutput(BaseModel):
    """
    Output from the Think node.
    
    Simplified in V4.1: Removed unused fields (data_requirements, success_criteria).
    Entity tracking handled by SessionIdRegistry, not Think declarations.
    
    Think decides to:
    - plan_direct: Execute immediately (simple, unambiguous requests)
    - propose: Show plan for confirmation (complex/exploratory)
    - clarify: Ask questions (rare - Understand handles most)
    """

    # Always present
    goal: str
    
    # Steps to execute (with group field for parallelization)
    steps: list[ThinkStep] = Field(default_factory=list)
    
    # Decision type
    decision: Literal["plan_direct", "propose", "clarify"] = "plan_direct"
    
    # For propose
    proposal_message: str | None = None
    
    # For clarify
    clarification_questions: list[str] | None = None
    
    @model_validator(mode="after")
    def validate_decision_consistency(self) -> "ThinkOutput":
        """
        Ensure output is consistent with the decision type.
        
        Fix common LLM errors:
        - plan_direct with empty steps → convert to propose if proposal_message exists
        - plan_direct with proposal fields → convert to propose
        """
        if self.decision == "plan_direct":
            # If LLM said plan_direct but gave empty steps + proposal_message,
            # it actually meant propose
            if not self.steps and self.proposal_message:
                self.decision = "propose"
            # If empty steps and no proposal, this is an error - but we can't
            # fix it here without more context. At least log it.
            elif not self.steps and not self.proposal_message:
                import logging
                logging.getLogger("alfred.state").warning(
                    "ThinkOutput: plan_direct with empty steps and no proposal - "
                    "this will result in no action taken"
                )
        return self


# =============================================================================
# Act Loop Actions
# =============================================================================


# =============================================================================
# V4 Batch Tracking
# =============================================================================


class BatchItem(BaseModel):
    """A single item in a batch operation."""
    
    ref: str  # Reference ID (gen_recipe_1, recipe_1, etc.)
    label: str  # Human-readable label
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    result_id: str | None = None  # DB ID when created
    error: str | None = None  # Error message if failed


class BatchManifest(BaseModel):
    """
    V4: Explicit batch manifest for multi-item operations.
    
    Enforces completion tracking - cannot call step_complete while items are pending.
    """
    
    total: int  # Total items in batch
    items: list[BatchItem]  # Per-item tracking
    
    @property
    def completed_count(self) -> int:
        return sum(1 for item in self.items if item.status == "completed")
    
    @property
    def failed_count(self) -> int:
        return sum(1 for item in self.items if item.status == "failed")
    
    @property
    def pending_count(self) -> int:
        return sum(1 for item in self.items if item.status == "pending")
    
    @property
    def all_done(self) -> bool:
        """Returns True if no items are pending (all completed or failed)."""
        return self.pending_count == 0
    
    def mark_completed(self, ref: str, result_id: str) -> None:
        """Mark an item as completed with its DB ID."""
        for item in self.items:
            if item.ref == ref:
                item.status = "completed"
                item.result_id = result_id
                return
    
    def mark_failed(self, ref: str, error: str) -> None:
        """Mark an item as failed with error message."""
        for item in self.items:
            if item.ref == ref:
                item.status = "failed"
                item.error = error
                return
    
    def to_prompt_table(self) -> str:
        """Format batch manifest as markdown table for Act prompt."""
        lines = [
            "## Batch Manifest",
            "",
            "| Ref | Label | Status | DB ID |",
            "|-----|-------|--------|-------|",
        ]
        for item in self.items:
            status_icon = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅",
                "failed": "❌",
            }.get(item.status, "?")
            # V4: result_id is now a simple ref, show in full
            db_id = item.result_id if item.result_id else "—"
            lines.append(f"| {item.ref} | {item.label} | {status_icon} {item.status} | {db_id} |")
        
        # Add progress summary
        lines.append("")
        lines.append(f"**Progress:** {self.completed_count}/{self.total} completed")
        if self.failed_count:
            lines.append(f"**Failed:** {self.failed_count} items")
        if self.pending_count:
            lines.append(f"**Remaining:** {self.pending_count} items")
        
        return "\n".join(lines)


class BatchProgress(BaseModel):
    """V4: Batch progress tracking in ActOutput."""
    
    completed: int
    total: int
    completed_items: list[str]  # refs of completed items
    failed_items: list[dict]  # [{ref, error}]
    pending_items: list[str]  # refs still pending


class ToolCallAction(BaseModel):
    """Request to call a CRUD tool."""

    action: Literal["tool_call"] = "tool_call"
    tool: Literal["db_read", "db_create", "db_update", "db_delete"]
    params: dict[str, Any]  # Tool-specific params


class StepCompleteAction(BaseModel):
    """Indicates a step was completed successfully."""

    action: Literal["step_complete"] = "step_complete"
    result_summary: str  # Brief description of outcome
    data: Any = None  # Full result for caching
    note_for_next_step: str | None = None  # Short note for next step (IDs, counts, etc.)
    
    # V4: Artifacts from generate steps (preserved in full, not summarized)
    artifacts: list[dict] | None = None  # Full generated content for downstream write steps
    
    # V4: Batch progress tracking
    batch_progress: BatchProgress | None = None  # For multi-item operations


class RequestSchemaAction(BaseModel):
    """Request additional subdomain schema."""

    action: Literal["request_schema"] = "request_schema"
    subdomain: str  # Request schema for this subdomain


class RetrieveStepAction(BaseModel):
    """Request to retrieve full data from an older step."""

    action: Literal["retrieve_step"] = "retrieve_step"
    step_index: int  # 0-based index of step to retrieve


class AskUserAction(BaseModel):
    """Request clarification from the user."""

    action: Literal["ask_user"] = "ask_user"
    question: str  # Clear, single question
    context: str  # Why we need this info


class BlockedAction(BaseModel):
    """Indicates the agent is stuck and needs orchestrator intervention."""

    action: Literal["blocked"] = "blocked"
    reason_code: Literal[
        "INSUFFICIENT_INFO",  # Need user input
        "PLAN_INVALID",  # Current plan won't work
        "TOOL_FAILURE",  # Tool returned error
    ]
    details: str  # Human-readable explanation
    suggested_next: Literal["ask_user", "replan", "fail"]


class FailAction(BaseModel):
    """Indicates unrecoverable failure."""

    action: Literal["fail"] = "fail"
    reason: str  # Why we can't proceed
    user_message: str  # What to tell the user


# Union type for all actions
ActAction = (
    ToolCallAction
    | StepCompleteAction
    | RequestSchemaAction
    | RetrieveStepAction
    | AskUserAction
    | BlockedAction
    | FailAction
)


# =============================================================================
# Conversation Context (Phase 5)
# =============================================================================


class ConversationTurn(BaseModel):
    """A single turn in the conversation."""
    
    user: str  # User's message
    assistant: str  # Alfred's full response (for Reply/display)
    assistant_summary: str | None = None  # LLM-condensed version (for context in Act/Think)
    timestamp: str  # ISO format
    routing: dict[str, Any] | None = None  # Router decision for this turn
    entities_mentioned: list[str] = Field(default_factory=list)  # Entity IDs touched


class StepSummary(BaseModel):
    """Compressed summary of an older step (beyond FULL_DETAIL_STEPS)."""
    
    step_index: int
    description: str  # From the plan
    subdomain: str
    outcome: str  # One-line summary
    entity_ids: list[str] = Field(default_factory=list)  # IDs for retrieval
    record_count: int = 0  # How many records were involved


# =============================================================================
# V6: Turn Execution Summary (Layer 3 - Reasoning Trace)
# =============================================================================


class StepExecutionSummary(BaseModel):
    """
    Summary of a single step execution for the reasoning trace.
    
    Built by Summarize from step_results and step_metadata.
    """
    
    step_num: int
    step_type: str  # "read" | "analyze" | "generate" | "write"
    subdomain: str
    description: str  # From the plan
    outcome: str  # "Found 5 recipes" | "Generated 3 options"
    entities_involved: list[str] = Field(default_factory=list)  # Refs touched
    note: str | None = None  # Act's note_for_next_step


class CurationSummary(BaseModel):
    """
    Summary of Understand's entity curation decisions for a turn.
    """
    
    retained: list[str] = Field(default_factory=list)  # Refs explicitly kept
    demoted: list[str] = Field(default_factory=list)  # Refs no longer active
    reasons: dict[str, str] = Field(default_factory=dict)  # ref -> reason


class TurnExecutionSummary(BaseModel):
    """
    V6: Complete summary of what happened in a turn.
    
    Built by Summarize at end of turn, stored in conversation["turn_summaries"].
    Consumed by Think (to avoid re-planning), Reply (for continuity).
    
    This is the core of Layer 3 (Reasoning Trace).
    """
    
    turn_num: int
    
    # What Think decided
    think_decision: str = ""  # "plan_direct" | "propose" | "clarify"
    think_goal: str = ""  # "Find vegetarian recipes"
    
    # What steps executed
    steps: list[StepExecutionSummary] = Field(default_factory=list)
    
    # Understand's curation this turn
    entity_curation: CurationSummary = Field(default_factory=CurationSummary)
    
    # Conversation flow metadata (for Reply continuity)
    conversation_phase: str = ""  # "exploring" | "narrowing" | "confirming" | "executing"
    user_expressed: str = ""  # "wants variety" | "prefers quick meals"


class ConversationContext(TypedDict, total=False):
    """
    Conversation history and context tracking.
    
    Design:
    - Last FULL_DETAIL_TURNS turns: full text
    - Older turns: compressed to history_summary
    - Last FULL_DETAIL_STEPS step results: full data in step_results
    - Older steps: compressed to step_summaries (Act can retrieve via tool)
    - active_entities: EntityRefs for "that recipe" resolution
    """

    # High-level summary of current engagement
    engagement_summary: str  # "Helping with meal planning, saved 2 recipes..."

    # Last N exchanges - full text (N = FULL_DETAIL_TURNS)
    recent_turns: list[dict]  # ConversationTurn as dict

    # Older exchanges - compressed
    history_summary: str  # "Earlier discussed pasta, added milk to pantry..."
    
    # Older step summaries (for reference, Act can retrieve full data)
    step_summaries: list[dict]  # StepSummary as dict

    # Content archive for generated content (persists across turns)
    # Allows "save those recipes we discussed" to work in later turns
    # Keys: "generated_recipes", "generated_meal_plan", "analysis_result", etc.
    content_archive: dict[str, Any]
    
    # Tracked entities for "that recipe" resolution
    # Key is entity type ("recipe", "inventory_item", etc.)
    # Value is the most recent entity of that type
    active_entities: dict[str, dict]  # EntityRef as dict
    
    # All entities from this conversation (for retrieval)
    # Key is entity ID, value is EntityRef
    all_entities: dict[str, dict]  # EntityRef as dict
    
    # Pending clarification/proposal from Think (for context threading)
    # When Think returns propose/clarify, this tracks what was asked
    # Next turn's Think can see user's response in context
    pending_clarification: dict[str, Any] | None  # {type, message, assumptions/questions}
    
    # V6: Turn execution summaries (Layer 3 - Reasoning Trace)
    # Last 2 turns of TurnExecutionSummary for Think/Reply context
    turn_summaries: list[dict]  # TurnExecutionSummary as dict
    
    # V6: Compressed older reasoning (when turn_summaries exceeds 2)
    reasoning_summary: str  # "Earlier: explored recipes, narrowed to fish options..."


# =============================================================================
# Graph State
# =============================================================================


class AlfredState(TypedDict, total=False):
    """
    Shared state passed through all LangGraph nodes.

    This is a TypedDict so LangGraph can properly type-check
    and merge state updates from each node.
    
    V4 CONSOLIDATION:
    - id_registry: SessionIdRegistry - SINGLE source of truth for entity tracking
    - mode_context: ModeContext for complexity adaptation
    - understand_output: UnderstandOutput from Understand node
    - current_turn: Turn counter
    
    Deprecated (removed): entity_registry, turn_entities, entity_context, 
                          working_set, id_mapper, session_constraints
    """

    # User context
    user_id: str
    conversation_id: str | None

    # Input
    user_message: str

    # V3: Mode context (from CLI/UI)
    mode_context: dict[str, Any]  # ModeContext serialized

    # V4 CONSOLIDATION: Turn number (for entity tracking)
    current_turn: int

    # Router output
    router_output: RouterOutput | None
    
    # V3: Understand output (entity state updates)
    understand_output: UnderstandOutput | None

    # Think output
    think_output: ThinkOutput | None

    # NOTE: Context is NOT pre-fetched. Act uses CRUD for all data access.
    # This field exists only for conversation context (Phase 5).
    context: dict[str, Any]

    # Act loop state
    current_step_index: int
    step_results: dict[int, Any]  # Cache of tool outputs by step index
    # V4: Step metadata for artifact preservation
    # Keys: step index, Values: {step_type, subdomain, artifacts, data}
    step_metadata: dict[int, dict]
    current_step_tool_results: list[Any]  # Tool results within current step (multi-tool pattern)
    
    # V4: Batch tracking for multi-item operations
    # Set by Think when planning batch operations, tracked by Act
    current_batch_manifest: dict | None  # BatchManifest.model_dump()
    
    # V4 CONSOLIDATION: Session ID Registry - SINGLE SOURCE OF TRUTH
    # PERSISTS ACROSS TURNS. LLMs only see simple refs (recipe_1, inv_5).
    # Populated by CRUD layer on db_read/db_create. Used for all ID translation.
    # Also stores temporal tracking (turn_created, turn_last_ref) and pending artifacts.
    id_registry: dict | None  # SessionIdRegistry.to_dict()
    
    # V4: Summarize output - structured audit ledger
    summarize_output: dict | None  # SummarizeOutput.model_dump()
    current_subdomain: str | None  # Active subdomain for schema
    schema_requests: int  # Count of schema requests (for safeguard)
    pending_action: ActAction | None
    
    # V3: Group-based results (for parallelization)
    # Keys: group number (0, 1, 2, ...)
    # Values: list of step results from that group
    group_results: dict[int, list[dict]]

    # Content archive (persists across turns for generate/analyze step results)
    # Keys: "turn_{turn_num}_step_{step_num}" or descriptive like "recipes_generated"
    # Allows Act to retrieve generated content from previous turns
    content_archive: dict[str, Any]

    # Step notes (CRUD steps leave notes for next step)
    prev_step_note: str | None  # Note from previous step for context
    
    # V4 CONSOLIDATION: turn_entities removed - use id_registry instead
    
    # Conversation context (Phase 5)
    conversation: ConversationContext

    # Final output
    final_response: str | None

    # Error state
    error: str | None
