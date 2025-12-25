"""
Alfred V2 - LangGraph Orchestration.

The graph implements: Router → Think → Act Loop → Reply

Uses generic CRUD tools with subdomain-based schema filtering.
"""

# Import tools module
import alfred.tools  # noqa: F401

from alfred.graph.state import (
    ActAction,
    AlfredState,
    AskUserAction,
    BlockedAction,
    ConversationContext,
    EntityRef,
    FailAction,
    PlannedStep,
    RequestSchemaAction,
    RouterOutput,
    StepCompleteAction,
    ThinkOutput,
    ToolCallAction,
)
from alfred.graph.workflow import compile_alfred_graph, create_alfred_graph, run_alfred

__all__ = [
    # State and contracts
    "AlfredState",
    "ConversationContext",
    "EntityRef",
    "RouterOutput",
    "PlannedStep",
    "ThinkOutput",
    "ActAction",
    "ToolCallAction",
    "StepCompleteAction",
    "RequestSchemaAction",
    "AskUserAction",
    "BlockedAction",
    "FailAction",
    # Workflow
    "create_alfred_graph",
    "compile_alfred_graph",
    "run_alfred",
]
