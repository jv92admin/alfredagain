"""
Alfred V2 - Graph Workflow Definition.

This module constructs the LangGraph workflow:
Router → Think (with subdomain hints) → Act Loop (with CRUD) → Reply

The Think node outputs steps with subdomain assignments.
Act receives subdomain schema and uses generic CRUD tools.
"""

from langgraph.graph import END, StateGraph

from alfred.graph.nodes import (
    act_node,
    reply_node,
    router_node,
    should_continue_act,
    think_node,
)
from alfred.graph.state import AlfredState


def create_alfred_graph() -> StateGraph:
    """
    Create the Alfred LangGraph workflow.
    
    Flow:
        START → router → think → act ⟲ → reply → END
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
    
    # Reply → END
    graph.add_edge("reply", END)
    
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
) -> str:
    """
    Run Alfred on a user message.
    
    This is the main entry point for processing user requests.
    
    Args:
        user_message: The user's input message
        user_id: The user's ID for context retrieval
        conversation_id: Optional conversation ID for continuity
        
    Returns:
        Alfred's response string
        
    Example:
        response = await run_alfred(
            user_message="What can I make for dinner?",
            user_id="user_123",
        )
        print(response)
    """
    # Compile the graph
    app = compile_alfred_graph()
    
    # Create initial state
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
        "final_response": None,
        "error": None,
    }
    
    # Run the graph
    final_state = await app.ainvoke(initial_state)
    
    # Extract response
    return final_state.get("final_response", "I'm sorry, I couldn't process that request.")
