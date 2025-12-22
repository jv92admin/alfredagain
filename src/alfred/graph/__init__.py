"""
Alfred V2 - LangGraph Orchestration.

The graph implements: Router → Think → Act Loop → Reply
"""

from alfred.graph.state import (
    ActAction,
    AlfredState,
    AskUserAction,
    BlockedAction,
    EntityRef,
    FailAction,
    RouterOutput,
    Step,
    StepCompleteAction,
    ThinkOutput,
    ToolCallAction,
)
from alfred.graph.workflow import compile_alfred_graph, create_alfred_graph, run_alfred

__all__ = [
    # State and contracts
    "AlfredState",
    "EntityRef",
    "RouterOutput",
    "Step",
    "ThinkOutput",
    "ActAction",
    "ToolCallAction",
    "StepCompleteAction",
    "AskUserAction",
    "BlockedAction",
    "FailAction",
    # Workflow
    "create_alfred_graph",
    "compile_alfred_graph",
    "run_alfred",
]
