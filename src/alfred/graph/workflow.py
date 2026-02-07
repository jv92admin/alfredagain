"""
Alfred V3 - Graph Workflow Definition.

This module constructs the LangGraph workflow:
Understand → Think → [Act Loop | Reply] → Summarize

V3 Changes:
- Router skipped for single-agent mode (Quick Mode Phase 0)
- Understand node handles entity state updates before Think
- Think outputs steps with group field for parallelization
- Group-based execution (same group = parallel, groups execute in order)
- Mode context passed through the graph

Flow:
    START → understand ──┬─(needs_clarification)─→ reply → summarize → END
                         │
                         └─(continue)─→ think ──┬─(plan_direct)─→ act ⟲ → reply → summarize → END
                                                │
                                                └─(propose)─→ reply → summarize → END

Summarize maintains conversation memory and entity lifecycle after each exchange.
"""

import logging
import re
from typing import Any

from langgraph.graph import END, StateGraph

from alfred.core.id_registry import SessionIdRegistry

logger = logging.getLogger(__name__)

# =============================================================================
# Domain Configuration (Phase 2: Use DomainConfig instead of hardcoded mappings)
# =============================================================================

from alfred.domain import get_current_domain


def _get_type_to_table() -> dict[str, str]:
    """Get entity type → table mapping from domain config."""
    return get_current_domain().type_to_table


from alfred.core.modes import Mode, ModeContext
from alfred.graph.nodes import (
    act_node,
    act_quick_node,
    reply_node,
    router_node,
    should_continue_act,
    summarize_node,
    think_node,
)
from alfred.graph.nodes.understand import understand_node
from alfred.graph.state import AlfredState, RouterOutput, ThinkOutput
from alfred.observability.session_logger import get_session_logger


def _create_default_router_output(user_message: str) -> RouterOutput:
    """
    Create default router output for single-agent mode.

    Phase 2: Uses domain.default_agent instead of hardcoded agent name.
    Goal is set to user message - Think will refine it.
    """
    domain = get_current_domain()
    return RouterOutput(
        agent=domain.default_agent,
        goal=user_message,  # Think will use this as starting point
        complexity="medium",  # Safe default
    )


def _extract_tool_calls(step_result: Any) -> list[dict] | None:
    """
    Extract tool call summaries from a step result for frontend display.

    Returns list like [{"tool": "db_read", "table": "inventory", "count": 12}, ...]
    """
    if step_result is None:
        return None

    tool_calls: list[dict] = []

    if isinstance(step_result, list):
        for item in step_result:
            if isinstance(item, tuple) and len(item) >= 2:
                if len(item) == 3:
                    tool_name, table, result = item
                else:
                    tool_name, result = item
                    table = "unknown"

                # Count results
                count = 0
                if isinstance(result, list):
                    count = len(result)
                elif isinstance(result, dict):
                    if "id" in result:
                        count = 1
                    else:
                        # Count nested entities
                        for v in result.values():
                            if isinstance(v, list):
                                count += len(v)

                # Simplify tool name for display (db_read -> read)
                display_tool = tool_name.replace("db_", "") if tool_name else "unknown"

                tool_calls.append({
                    "tool": display_tool,
                    "table": table,
                    "count": count,
                })

    return tool_calls if tool_calls else None


def _extract_step_data(step_result: Any) -> dict[str, list[dict]] | None:
    """
    Extract entity data from a step result for frontend entity cards.
    
    Step results can be:
    - A list of (tool_name, result) tuples (multi-tool pattern)
    - A dict with table data
    - None
    
    Returns dict like {"inventory": [{"id": "...", "name": "..."}], ...}
    """
    if step_result is None:
        return None
    
    entities: dict[str, list[dict]] = {}
    
    def add_entity(table: str, record: dict) -> None:
        """Add an entity record to the collection."""
        if "id" not in record:
            return
        if table not in entities:
            entities[table] = []
        
        # Build entity with common fields + table-specific fields
        entity = {
            "id": record.get("id"),
            "name": record.get("name", record.get("title")),
        }
        
        # Include fields needed for display by table type
        if table == "meal_plans":
            entity["date"] = record.get("date")
            entity["meal_type"] = record.get("meal_type")
        elif table == "tasks":
            entity["description"] = record.get("description")
        
        entities[table].append(entity)
    
    def extract_from_result(result: Any, table_hint: str | None = None) -> None:
        """Extract entities from a result."""
        if isinstance(result, dict):
            # Check if this dict IS an entity (has id field)
            if "id" in result:
                # Try to determine table from the data
                table = table_hint or "unknown"
                add_entity(table, result)
            else:
                # Check nested values for entity lists
                for key, value in result.items():
                    if isinstance(value, list) and len(value) > 0:
                        if isinstance(value[0], dict) and "id" in value[0]:
                            for item in value:
                                add_entity(key, item)
                    elif isinstance(value, dict) and "id" in value:
                        add_entity(key, value)
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and "id" in item:
                    table = table_hint or "unknown"
                    add_entity(table, item)
                else:
                    extract_from_result(item, table_hint)
    
    # Handle multi-tool pattern: list of (tool_name, table, result) tuples
    if isinstance(step_result, list):
        for item in step_result:
            if isinstance(item, tuple) and len(item) == 3:
                # New format: (tool_name, table, result)
                _tool_name, table, result = item
                extract_from_result(result, table)
            elif isinstance(item, tuple) and len(item) == 2:
                # Old format: (tool_name, result) - for backwards compat
                _tool_name, result = item
                extract_from_result(result, None)
            else:
                extract_from_result(item)
    else:
        extract_from_result(step_result)
    
    return entities if entities else None


# =============================================================================
# Shared Initialization Helpers (Phase 0 DRY extraction)
# =============================================================================


def _load_id_registry(
    id_registry_data: SessionIdRegistry | dict | None,
) -> SessionIdRegistry | None:
    """
    Load and deserialize id_registry from conversation context.

    Handles three cases:
    - None: No registry yet
    - SessionIdRegistry: Already an object (in-memory session)
    - dict: Needs deserialization (web sessions store as JSON)

    Args:
        id_registry_data: Raw registry data from conversation context

    Returns:
        SessionIdRegistry object or None
    """
    if id_registry_data is None:
        return None
    if isinstance(id_registry_data, SessionIdRegistry):
        return id_registry_data
    # Deserialize from dict
    return SessionIdRegistry.from_dict(id_registry_data)


def _process_ui_changes(
    ui_changes: list[dict],
    id_registry: SessionIdRegistry,
    conv_context: dict,
    current_turn: int,
) -> None:
    """
    Process UI changes and inject fresh data into turn_step_results cache.

    This registers entities created/updated/deleted via the UI into the registry
    and ensures the AI sees the updated data, not stale cached values.

    Args:
        ui_changes: List of UI change dicts with id, entity_type, label, action, data
        id_registry: SessionIdRegistry to register entities in
        conv_context: Conversation context to update with turn_step_results
        current_turn: Current turn number

    Side effects:
        - Modifies id_registry in place
        - Modifies conv_context["turn_step_results"] in place
    """
    id_registry.set_turn(current_turn)

    # First pass: register all entities
    for change in ui_changes:
        ref = id_registry.register_from_ui(
            uuid=change["id"],
            entity_type=change["entity_type"],
            label=change["label"],
            action=change["action"],
        )
        logger.info(f"Workflow: Processed UI change {ref} [{change['action']}]")

    # Second pass: inject data for creates/updates
    turn_step_results = conv_context.get("turn_step_results", {})
    current_turn_key = str(current_turn)

    for change in ui_changes:
        if change.get("data") and change["action"] in ("created:user", "updated:user"):
            ref = id_registry.uuid_to_ref.get(change["id"])
            if not ref:
                logger.warning(f"Workflow: No ref for {change['id'][:8]}, skipping injection")
                continue

            # Replace UUID with ref
            change["data"]["id"] = ref

            if current_turn_key not in turn_step_results:
                turn_step_results[current_turn_key] = {}

            table_name = _get_type_to_table().get(change["entity_type"], change["entity_type"])
            ui_step_key = f"ui_{change['entity_type']}_{change['id'][:8]}"
            turn_step_results[current_turn_key][ui_step_key] = {
                "table": table_name,
                "data": [change["data"]],
                "meta": {
                    "source": "ui_change",
                    "action": change["action"],
                    "turn": current_turn,
                },
            }
            logger.info(f"Workflow: Injected fresh data for {ref} [{change['action']}]")

    conv_context["turn_step_results"] = turn_step_results


async def _resolve_mentions(
    user_message: str,
    user_id: str,
    id_registry: SessionIdRegistry,
    conv_context: dict,
    current_turn: int,
) -> None:
    """
    Extract @-mentions from user message, register refs, and inject entity data.

    Format: @[Label](type:uuid) -> register ref, fetch data, inject into cache

    Args:
        user_message: User's message to parse for @-mentions
        user_id: User ID for database access
        id_registry: SessionIdRegistry to register mentions in
        conv_context: Conversation context to update
        current_turn: Current turn number

    Side effects:
        - Modifies id_registry in place
        - Modifies conv_context["turn_step_results"] in place
    """
    mention_pattern = r'@\[([^\]]+)\]\((\w+):([a-zA-Z0-9_-]+)\)'
    mentions = re.findall(mention_pattern, user_message)

    if not mentions:
        return

    id_registry.set_turn(current_turn)
    turn_step_results = conv_context.get("turn_step_results", {})
    current_turn_key = str(current_turn)

    from alfred.tools.crud import db_read, DbReadParams, FilterClause

    for label, entity_type, uuid in mentions:
        # 1. Register and get ref
        ref = id_registry.register_from_ui(uuid, entity_type, label, "mentioned:user")
        logger.info(f"Workflow: Registered @-mention {ref} [{entity_type}]")

        # 2. Fetch full entity data
        table_name = _get_type_to_table().get(entity_type, entity_type)
        try:
            read_params = DbReadParams(
                table=table_name,
                filters=[FilterClause(field="id", op="=", value=uuid)],
            )
            result = await db_read(read_params, user_id)

            if result:
                # 3. Replace UUID with ref and inject into cache
                entity_data = result[0]
                entity_data["id"] = ref

                if current_turn_key not in turn_step_results:
                    turn_step_results[current_turn_key] = {}

                mention_step_key = f"mention_{entity_type}_{uuid[:8]}"
                turn_step_results[current_turn_key][mention_step_key] = {
                    "table": table_name,
                    "data": [entity_data],
                    "meta": {
                        "source": "mention",
                        "action": "mentioned:user",
                        "turn": current_turn,
                    },
                }
                logger.info(f"Workflow: Injected @-mention data for {ref}")
        except Exception as e:
            logger.warning(f"Workflow: Failed to fetch @-mention data for {uuid[:8]}: {e}")

    conv_context["turn_step_results"] = turn_step_results


def route_after_understand(state: AlfredState) -> str:
    """
    Route based on Understand's output.
    
    - needs_clarification: Skip to Reply to ask clarifying questions
    - quick_mode: Skip Think, go directly to Act Quick (Phase 2)
    - otherwise: Continue to Think
    
    Returns:
        "think", "act_quick", or "reply"
    """
    understand_output = state.get("understand_output")
    
    if not understand_output:
        return "think"  # No output, continue normally
    
    if hasattr(understand_output, "needs_clarification") and understand_output.needs_clarification:
        return "reply"
    
    # Phase 2: Quick mode detection - skip Think, go directly to Act Quick
    if hasattr(understand_output, "quick_mode") and understand_output.quick_mode:
        return "act_quick"
    
    return "think"


def route_after_think(state: AlfredState) -> str:
    """
    Route based on Think's decision.
    
    - plan_direct: Proceed to Act with steps
    - plan_direct: Execute the plan
    - propose: Skip to Reply to present proposal for confirmation
    - clarify: Skip to Reply to ask clarifying questions
    
    Returns:
        "act" or "reply"
    """
    think_output = state.get("think_output")
    
    if not think_output:
        return "reply"  # Error case, let reply handle it
    
    # Route based on decision type
    match getattr(think_output, "decision", "plan_direct"):
        case "plan_direct":
            return "act"
        case "propose" | "clarify":
            return "reply"
        case _:
            return "act"  # Default fallback


def create_alfred_graph() -> StateGraph:
    """
    Create the Alfred LangGraph workflow (V3).
    
    Flow (Phase 0 - Router skipped):
        START → understand ──┬─(needs_clarification)─→ reply → summarize → END
                             │
                             └─(continue)─→ think ──┬─(plan_direct)─→ act ⟲ → reply → summarize → END
                                                    │
                                                    └─(propose)─→ reply → summarize → END
    
    V3 Changes:
    - Router skipped (single-agent mode, hardcode pantry)
    - Understand node handles entity state updates
    - Mode-aware routing (Quick mode may skip Think)
    
    Returns:
        Compiled StateGraph ready for execution
    """
    # Create the graph with our state schema
    graph = StateGraph(AlfredState)
    
    # ==========================================================================
    # Add Nodes
    # ==========================================================================
    
    # NOTE: Router node kept for future multi-agent support, but not in current flow
    # graph.add_node("router", router_node)
    graph.add_node("understand", understand_node)
    graph.add_node("think", think_node)
    graph.add_node("act", act_node)
    graph.add_node("act_quick", act_quick_node)  # Phase 3: Quick mode execution
    graph.add_node("reply", reply_node)
    graph.add_node("summarize", summarize_node)
    
    # ==========================================================================
    # Add Edges
    # ==========================================================================
    
    # Entry point - Skip router, go directly to understand (Phase 0)
    graph.set_entry_point("understand")
    
    # Understand → conditional routing
    graph.add_conditional_edges(
        "understand",
        route_after_understand,
        {
            "think": "think",       # Continue to planning
            "act_quick": "act_quick",  # Phase 2: Quick mode, skip Think
            "reply": "reply",       # Needs clarification, ask user
        },
    )
    
    # Think → conditional routing based on decision
    graph.add_conditional_edges(
        "think",
        route_after_think,
        {
            "act": "act",       # plan_direct: proceed with execution
            "reply": "reply",   # propose/clarify: ask user before acting
        },
    )
    
    # Act → conditional routing based on action result
    graph.add_conditional_edges(
        "act",
        should_continue_act,
        {
            "continue": "act",      # Loop back for next step
            "reply": "reply",       # All steps done, generate response
            "ask_user": "reply",    # Need user input, reply with question
            "fail": "reply",        # Failed, reply with error message
        },
    )
    
    # Act Quick → Reply (Phase 3: no looping, single call)
    graph.add_edge("act_quick", "reply")
    
    # Reply → Summarize (always, maintains conversation memory)
    graph.add_edge("reply", "summarize")
    
    # Summarize → END
    graph.add_edge("summarize", END)
    
    return graph


def compile_alfred_graph():
    """
    Compile the Alfred graph for execution.
    
    Returns:
        Compiled graph that can be invoked with state
    """
    graph = create_alfred_graph()
    return graph.compile()


# =============================================================================
# Convenience Functions
# =============================================================================


async def run_alfred(
    user_message: str,
    user_id: str,
    conversation_id: str | None = None,
    conversation: dict | None = None,
    mode: str = "plan",  # V3: Accept mode from UI/CLI
    ui_changes: list[dict] | None = None,  # Phase 3: UI CRUD tracking
) -> tuple[str, dict]:
    """
    Run Alfred on a user message.

    This is the main entry point for processing user requests.

    Args:
        user_message: The user's input message
        user_id: The user's ID for context retrieval
        conversation_id: Optional conversation ID for continuity
        conversation: Optional existing conversation context (for multi-turn)
        mode: The interaction mode ("quick" | "plan")
        ui_changes: Optional list of UI changes (create/update/delete) from frontend

    Returns:
        Tuple of (response string, updated conversation context)

    Example:
        # First turn
        response, conv = await run_alfred(
            user_message="What can I make for dinner?",
            user_id="user_123",
        )
        print(response)

        # Second turn (with context)
        response, conv = await run_alfred(
            user_message="Save that recipe",
            user_id="user_123",
            conversation=conv,
        )
    """
    from alfred.memory.conversation import initialize_conversation
    from alfred.core.modes import Mode
    
    # Compile the graph
    app = compile_alfred_graph()
    
    # Initialize or use existing conversation context
    conv_context = conversation if conversation else initialize_conversation()
    
    # Create initial state
    # Copy content_archive from conversation for cross-turn persistence
    initial_archive = conv_context.get("content_archive", {})
    
    # V3: Initialize or load entity registry (legacy)
    entity_registry = conv_context.get("entity_registry", {})

    # V4: Load id_registry using helper
    id_registry_data = conv_context.get("id_registry", None)
    if id_registry_data:
        entity_count = len(id_registry_data.get("ref_to_uuid", {})) if isinstance(id_registry_data, dict) else "?"
        logger.info(f"Workflow: Loaded registry with {entity_count} entities from prior turn")
    id_registry = _load_id_registry(id_registry_data)

    # V3: Get current turn number
    current_turn = conv_context.get("current_turn", 0) + 1

    # Phase 3: Process UI changes before Understand runs
    if ui_changes:
        if not id_registry:
            id_registry = SessionIdRegistry()
        _process_ui_changes(ui_changes, id_registry, conv_context, current_turn)

    # Phase 3b: Extract @-mentions and inject entity data
    if not id_registry:
        id_registry = SessionIdRegistry()
    await _resolve_mentions(user_message, user_id, id_registry, conv_context, current_turn)

    # V3: Initialize mode context from parameter
    selected_mode = Mode(mode) if mode in [m.value for m in Mode] else Mode.PLAN
    mode_context = ModeContext(selected_mode=selected_mode).to_dict()

    # Phase 0: Skip Router - create default router output
    default_router = _create_default_router_output(user_message)

    initial_state: AlfredState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "user_message": user_message,
        "router_output": default_router,  # Phase 0: Pre-populated, skip Router node
        "understand_output": None,  # V3
        "think_output": None,
        "context": {},
        "mode_context": mode_context,  # V3
        "entity_registry": entity_registry,  # V3 (legacy)
        "id_registry": id_registry,  # V4 CONSOLIDATION: SessionIdRegistry for cross-turn persistence
        "current_turn": current_turn,  # V3
        "current_step_index": 0,
        "step_results": {},
        "group_results": {},  # V3
        "current_step_tool_results": [],
        "current_subdomain": None,
        "schema_requests": 0,
        "pending_action": None,
        "content_archive": initial_archive,
        "turn_entities": [],  # V3
        "conversation": conv_context,
        "final_response": None,
        "error": None,
    }

    # Run the graph
    final_state = await app.ainvoke(initial_state)
    
    # Extract response and updated conversation
    response = final_state.get("final_response", "I'm sorry, I couldn't process that request.")
    updated_conversation = final_state.get("conversation", conv_context)
    
    # Debug: Check if registry was properly persisted
    registry_data = updated_conversation.get("id_registry")
    if registry_data:
        entity_count = len(registry_data.get("ref_to_uuid", {}))
        logger.info(f"Workflow: Returning conversation with {entity_count} entities in registry")
    else:
        logger.warning("Workflow: Returning conversation with NO registry - entities will be lost!")
    
    return response, updated_conversation


async def run_alfred_simple(
    user_message: str,
    user_id: str,
    conversation_id: str | None = None,
) -> str:
    """
    Simple wrapper for run_alfred that returns just the response.
    
    Use this for single-turn interactions where you don't need
    to maintain conversation state.
    """
    response, _ = await run_alfred(user_message, user_id, conversation_id)
    return response


async def run_alfred_streaming(
    user_message: str,
    user_id: str,
    conversation_id: str | None = None,
    conversation: dict | None = None,
    mode: str = "plan",  # V3: Accept mode from UI/CLI
    ui_changes: list[dict] | None = None,  # Phase 3: UI CRUD tracking
):
    """
    Run Alfred with streaming updates.

    Yields status updates as the workflow progresses:
    - {"type": "thinking", "message": "Planning..."}
    - {"type": "step", "step": 1, "total": 4, "description": "Reading inventory..."}
    - {"type": "step_complete", "step": 1, "total": 4}
    - {"type": "done", "response": "...", "conversation": {...}}

    Args:
        user_message: The user's input message
        user_id: The user's ID for context retrieval
        conversation_id: Optional conversation ID
        conversation: Optional existing conversation context
        mode: The interaction mode ("quick" | "plan")
        ui_changes: Optional list of UI changes (create/update/delete) from frontend

    Yields:
        Dict with status updates
    """
    from alfred.memory.conversation import initialize_conversation
    from alfred.core.modes import Mode
    
    # Compile the graph
    app = compile_alfred_graph()
    
    # Initialize or use existing conversation context
    conv_context = conversation if conversation else initialize_conversation()
    initial_archive = conv_context.get("content_archive", {})
    
    # V3: Initialize or load entity registry (legacy)
    entity_registry = conv_context.get("entity_registry", {})

    # V4: Load id_registry using helper
    id_registry = _load_id_registry(conv_context.get("id_registry", None))

    # V3: Get current turn number
    current_turn = conv_context.get("current_turn", 0) + 1

    # Phase 3: Process UI changes before Understand runs
    if ui_changes:
        if not id_registry:
            id_registry = SessionIdRegistry()
        _process_ui_changes(ui_changes, id_registry, conv_context, current_turn)

    # Phase 3b: Extract @-mentions and inject entity data
    if not id_registry:
        id_registry = SessionIdRegistry()
    await _resolve_mentions(user_message, user_id, id_registry, conv_context, current_turn)

    # V3: Initialize mode context from parameter
    selected_mode = Mode(mode) if mode in [m.value for m in Mode] else Mode.PLAN
    mode_context = ModeContext(selected_mode=selected_mode).to_dict()

    # Phase 0: Skip Router - create default router output
    default_router = _create_default_router_output(user_message)

    initial_state: AlfredState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "user_message": user_message,
        "router_output": default_router,  # Phase 0: Pre-populated, skip Router node
        "understand_output": None,  # V3
        "think_output": None,
        "context": {},
        "mode_context": mode_context,  # V3
        "entity_registry": entity_registry,  # V3 (legacy)
        "id_registry": id_registry,  # V4 CONSOLIDATION: SessionIdRegistry for cross-turn persistence
        "current_turn": current_turn,  # V3
        "current_step_index": 0,
        "step_results": {},
        "group_results": {},  # V3
        "current_step_tool_results": [],
        "current_subdomain": None,
        "schema_requests": 0,
        "pending_action": None,
        "content_archive": initial_archive,
        "turn_entities": [],  # V3
        "conversation": conv_context,
        "final_response": None,
        "error": None,
    }

    yield {"type": "thinking", "message": "Planning..."}

    # Track state for step updates
    last_step_index = -1
    total_steps = 0
    final_response = None
    final_conversation = None

    # Track step results for entity cards
    all_step_results: dict = {}

    # Session logger (if enabled)
    slog = get_session_logger()

    # Helper to ensure registry is a SessionIdRegistry object
    def ensure_registry(reg: SessionIdRegistry | dict | None) -> SessionIdRegistry | None:
        """Convert dict to SessionIdRegistry if needed."""
        if reg is None:
            return None
        if isinstance(reg, SessionIdRegistry):
            return reg
        if isinstance(reg, dict):
            return SessionIdRegistry.from_dict(reg)
        return None

    # Helper to emit active_context event
    def emit_active_context(registry: SessionIdRegistry | None) -> dict | None:
        """Emit active_context event if registry exists."""
        if registry and isinstance(registry, SessionIdRegistry):
            return {
                "type": "active_context",
                "data": registry.get_active_context_for_frontend(),
            }
        return None
    
    # Use LangGraph's streaming to get node-by-node updates
    async for event in app.astream(initial_state, stream_mode="updates"):
        # event is {node_name: node_output}
        for node_name, node_output in event.items():
            # Log node completion
            slog.node_exit(node_name, {"keys": list(node_output.keys()) if node_output else []})
            
            if node_name == "understand" and node_output:
                # Update registry reference from state (may be dict or object)
                updated_registry = ensure_registry(node_output.get("id_registry"))
                if updated_registry:
                    id_registry = updated_registry

                # Emit active_context after Understand (may pull/retain entities)
                context_event = emit_active_context(id_registry)
                if context_event:
                    yield context_event

            elif node_name == "think" and node_output:
                think_output = node_output.get("think_output")
                if think_output:
                    # Check decision type
                    decision = getattr(think_output, "decision", "plan_direct")
                    
                    if decision == "plan_direct" and hasattr(think_output, "steps"):
                        total_steps = len(think_output.steps)
                        # Send all step descriptions so frontend can build progress trail
                        step_descriptions = [s.description for s in think_output.steps]

                        # V10: Emit think_complete for inline progress display
                        yield {
                            "type": "think_complete",
                            "goal": think_output.goal,
                            "stepCount": total_steps,
                        }

                        yield {
                            "type": "plan",
                            "message": f"Planning {total_steps} step{'s' if total_steps != 1 else ''}...",
                            "goal": think_output.goal,
                            "total_steps": total_steps,
                            "steps": step_descriptions,
                        }
                    elif decision == "propose":
                        yield {
                            "type": "propose",
                            "message": "Confirming approach...",
                            "goal": think_output.goal,
                            "proposal_message": getattr(think_output, "proposal_message", None),
                            "assumptions": getattr(think_output, "assumptions", None),
                        }
                    elif decision == "clarify":
                        yield {
                            "type": "clarify",
                            "message": "Need more information...",
                            "goal": think_output.goal,
                            "questions": getattr(think_output, "clarification_questions", None),
                        }
            
            elif node_name == "act" and node_output:
                current_index = node_output.get("current_step_index", 0)
                # Don't overwrite think_output - preserve the one from think node
                # (act_node doesn't return think_output, so this would be None)

                # Update registry reference from state (may be dict or object)
                updated_registry = ensure_registry(node_output.get("id_registry"))
                if updated_registry:
                    id_registry = updated_registry

                # Track step results for entity cards
                step_results = node_output.get("step_results", {})
                all_step_results.update(step_results)
                
                # Log step info
                if think_output and hasattr(think_output, "steps") and current_index < len(think_output.steps):
                    step = think_output.steps[current_index]
                    slog.step_start(
                        step_index=current_index,
                        step_type=step.step_type,
                        subdomain=step.subdomain,
                        group=step.group,
                        description=step.description,
                    )
                
                # Get step description and group
                step_desc = ""
                step_group = 0
                step_type = ""
                if think_output and hasattr(think_output, "steps"):
                    total_steps = len(think_output.steps)
                    if current_index < total_steps:
                        current_step = think_output.steps[current_index]
                        step_desc = current_step.description
                        step_group = current_step.group
                        step_type = current_step.step_type
                
                # Check if step advanced
                if current_index > last_step_index:
                    # Previous step completed - include the step's data for entity cards
                    if last_step_index >= 0:
                        step_result = all_step_results.get(last_step_index)
                        step_data = _extract_step_data(step_result)
                        tool_calls = _extract_tool_calls(step_result)
                        yield {
                            "type": "step_complete",
                            "step": last_step_index + 1,
                            "total": total_steps,
                            "data": step_data,
                            "tool_calls": tool_calls,  # V10: Tool call summary for inline display
                        }
                        # Emit active_context after each step (reads/creates entities)
                        context_event = emit_active_context(id_registry)
                        if context_event:
                            yield context_event
                    
                    # New step started - V3: include group and step_type
                    yield {
                        "type": "step",
                        "step": current_index + 1,
                        "total": total_steps,
                        "description": step_desc,
                        "group": step_group,  # V3: For parallel step visualization
                        "step_type": step_type,  # V3: read/write/analyze/generate
                    }
                    last_step_index = current_index
                else:
                    # Act loop within same step - show working indicator
                    yield {
                        "type": "working",
                        "step": current_index + 1,
                    }
            
            elif node_name == "act_quick" and node_output:
                # Quick mode execution - update registry and emit context
                updated_registry = ensure_registry(node_output.get("id_registry"))
                if updated_registry:
                    id_registry = updated_registry

                # Emit active_context after Quick mode execution
                context_event = emit_active_context(id_registry)
                if context_event:
                    yield context_event

            elif node_name == "reply" and node_output:
                # Update registry reference from state (may be dict or object)
                updated_registry = ensure_registry(node_output.get("id_registry"))
                if updated_registry:
                    id_registry = updated_registry

                # Final step complete - include the step's data for entity cards
                if last_step_index >= 0 and total_steps > 0:
                    step_result = all_step_results.get(last_step_index)
                    step_data = _extract_step_data(step_result)
                    tool_calls = _extract_tool_calls(step_result)
                    yield {
                        "type": "step_complete",
                        "step": last_step_index + 1,
                        "total": total_steps,
                        "data": step_data,
                        "tool_calls": tool_calls,  # V10: Tool call summary for inline display
                    }
                    # Emit active_context for final step
                    context_event = emit_active_context(id_registry)
                    if context_event:
                        yield context_event

                # Capture final response
                final_response = node_output.get("final_response")

                # Emit final active_context with Reply
                context_event = emit_active_context(id_registry)

                # Phase 1: Yield response immediately after Reply, don't wait for Summarize
                # This makes the response appear faster to the user
                response = final_response or "I'm sorry, I couldn't process that request."
                yield {
                    "type": "done",
                    "response": response,
                    "conversation": conv_context,  # Use initial context, will be updated async
                    "active_context": context_event.get("data") if context_event else None,
                }
            
            elif node_name == "summarize" and node_output:
                # Capture updated conversation
                final_conversation = node_output.get("conversation")
                
                # Phase 1: Notify frontend that context is ready
                # This allows race condition handling: if user types before this,
                # frontend can show "Updating context..." message
                yield {
                    "type": "context_updated",
                    "conversation": final_conversation,
                }
    
    # Note: We already yielded "done" after reply, so we don't yield it again here
    # This comment block replaces the old synchronous yield at the end
