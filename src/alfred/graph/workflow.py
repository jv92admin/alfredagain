"""
Alfred V2 - Graph Workflow Definition.

This module constructs the LangGraph workflow:
Router → Think (with subdomain hints) → Act Loop (with CRUD) → Reply → Summarize

The Think node outputs steps with subdomain assignments.
Act receives subdomain schema and uses generic CRUD tools.
Summarize maintains conversation memory after each exchange.
"""

from typing import Any

from langgraph.graph import END, StateGraph

from alfred.graph.nodes import (
    act_node,
    reply_node,
    router_node,
    should_continue_act,
    summarize_node,
    think_node,
)
from alfred.graph.state import AlfredState


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
        entities[table].append({
            "id": record.get("id"),
            "name": record.get("name", record.get("title", table)),
        })
    
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


def create_alfred_graph() -> StateGraph:
    """
    Create the Alfred LangGraph workflow.
    
    Flow:
        START → router → think → act ⟲ → reply → summarize → END
                                   ↓
                              (ask_user/fail)
    
    Returns:
        Compiled StateGraph ready for execution
    """
    # Create the graph with our state schema
    graph = StateGraph(AlfredState)
    
    # ==========================================================================
    # Add Nodes
    # ==========================================================================
    
    graph.add_node("router", router_node)
    graph.add_node("think", think_node)
    graph.add_node("act", act_node)
    graph.add_node("reply", reply_node)
    graph.add_node("summarize", summarize_node)
    
    # ==========================================================================
    # Add Edges
    # ==========================================================================
    
    # Entry point
    graph.set_entry_point("router")
    
    # Router → Think (always)
    graph.add_edge("router", "think")
    
    # Think → Act (always)
    graph.add_edge("think", "act")
    
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
) -> tuple[str, dict]:
    """
    Run Alfred on a user message.
    
    This is the main entry point for processing user requests.
    
    Args:
        user_message: The user's input message
        user_id: The user's ID for context retrieval
        conversation_id: Optional conversation ID for continuity
        conversation: Optional existing conversation context (for multi-turn)
        
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
    
    # Compile the graph
    app = compile_alfred_graph()
    
    # Initialize or use existing conversation context
    conv_context = conversation if conversation else initialize_conversation()
    
    # Create initial state
    # Copy content_archive from conversation for cross-turn persistence
    initial_archive = conv_context.get("content_archive", {})
    
    initial_state: AlfredState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "user_message": user_message,
        "router_output": None,
        "think_output": None,
        "context": {},
        "current_step_index": 0,
        "step_results": {},
        "current_step_tool_results": [],  # Multi-tool-call pattern
        "current_subdomain": None,
        "schema_requests": 0,
        "pending_action": None,
        "content_archive": initial_archive,  # Persisted across turns
        "conversation": conv_context,
        "final_response": None,
        "error": None,
    }
    
    # Run the graph
    final_state = await app.ainvoke(initial_state)
    
    # Extract response and updated conversation
    response = final_state.get("final_response", "I'm sorry, I couldn't process that request.")
    updated_conversation = final_state.get("conversation", conv_context)
    
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
        
    Yields:
        Dict with status updates
    """
    from alfred.memory.conversation import initialize_conversation
    
    # Compile the graph
    app = compile_alfred_graph()
    
    # Initialize or use existing conversation context
    conv_context = conversation if conversation else initialize_conversation()
    initial_archive = conv_context.get("content_archive", {})
    
    initial_state: AlfredState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "user_message": user_message,
        "router_output": None,
        "think_output": None,
        "context": {},
        "current_step_index": 0,
        "step_results": {},
        "current_step_tool_results": [],
        "current_subdomain": None,
        "schema_requests": 0,
        "pending_action": None,
        "content_archive": initial_archive,
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
    
    # Use LangGraph's streaming to get node-by-node updates
    async for event in app.astream(initial_state, stream_mode="updates"):
        # event is {node_name: node_output}
        for node_name, node_output in event.items():
            if node_name == "think" and node_output:
                think_output = node_output.get("think_output")
                if think_output and hasattr(think_output, "steps"):
                    total_steps = len(think_output.steps)
                    # Send all step descriptions so frontend can build progress trail
                    step_descriptions = [s.description for s in think_output.steps]
                    yield {
                        "type": "plan",
                        "message": f"Planning {total_steps} step{'s' if total_steps != 1 else ''}...",
                        "goal": think_output.goal,
                        "total_steps": total_steps,
                        "steps": step_descriptions,
                    }
            
            elif node_name == "act" and node_output:
                current_index = node_output.get("current_step_index", 0)
                think_output = node_output.get("think_output")
                
                # Track step results for entity cards
                step_results = node_output.get("step_results", {})
                all_step_results.update(step_results)
                
                # Get step description
                step_desc = ""
                if think_output and hasattr(think_output, "steps"):
                    total_steps = len(think_output.steps)
                    if current_index < total_steps:
                        step_desc = think_output.steps[current_index].description
                
                # Check if step advanced
                if current_index > last_step_index:
                    # Previous step completed - include the step's data for entity cards
                    if last_step_index >= 0:
                        step_data = _extract_step_data(all_step_results.get(last_step_index))
                        yield {
                            "type": "step_complete",
                            "step": last_step_index + 1,
                            "total": total_steps,
                            "data": step_data,
                        }
                    
                    # New step started
                    yield {
                        "type": "step",
                        "step": current_index + 1,
                        "total": total_steps,
                        "description": step_desc,
                    }
                    last_step_index = current_index
                else:
                    # Act loop within same step - show working indicator
                    yield {
                        "type": "working",
                        "step": current_index + 1,
                    }
            
            elif node_name == "reply" and node_output:
                # Final step complete - include the step's data for entity cards
                if last_step_index >= 0 and total_steps > 0:
                    step_data = _extract_step_data(all_step_results.get(last_step_index))
                    yield {
                        "type": "step_complete",
                        "step": last_step_index + 1,
                        "total": total_steps,
                        "data": step_data,
                    }
                # Capture final response
                final_response = node_output.get("final_response")
            
            elif node_name == "summarize" and node_output:
                # Capture updated conversation
                final_conversation = node_output.get("conversation")
    
    # Use captured state (don't run graph again!)
    response = final_response or "I'm sorry, I couldn't process that request."
    updated_conversation = final_conversation or conv_context
    
    yield {
        "type": "done",
        "response": response,
        "conversation": updated_conversation,
    }
