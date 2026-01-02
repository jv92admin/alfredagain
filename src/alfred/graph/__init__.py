"""
Alfred V2 - LangGraph Orchestration.

The graph implements: Router → Think → Act Loop → Reply → Summarize

Uses generic CRUD tools with subdomain-based schema filtering.
Maintains conversation memory across turns.
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
    RequestSchemaAction,
    RetrieveStepAction,
    RouterOutput,
    StepCompleteAction,
    ThinkOutput,
    ThinkStep,
    ToolCallAction,
)
from alfred.graph.workflow import (
    compile_alfred_graph,
    create_alfred_graph,
    run_alfred,
    run_alfred_simple,
)

__all__ = [
    # State and contracts
    "AlfredState",
    "ConversationContext",
    "EntityRef",
    "RouterOutput",
    "ThinkStep",
    "ThinkOutput",
    "ActAction",
    "ToolCallAction",
    "StepCompleteAction",
    "RequestSchemaAction",
    "RetrieveStepAction",
    "AskUserAction",
    "BlockedAction",
    "FailAction",
    # Workflow
    "create_alfred_graph",
    "compile_alfred_graph",
    "run_alfred",
    "run_alfred_simple",
]
