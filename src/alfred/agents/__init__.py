"""
Alfred Agent System.

Phase 2.5: Lightweight agent protocol for multi-agent support.

This module provides the abstract interfaces for agents within Alfred:
- AgentProtocol: Base class for all agents (graph-based or streaming)
- AgentRouter: Routes requests to appropriate agents
- MultiAgentOrchestrator: Coordinates multiple agents

Current implementation uses single-agent mode (pantry agent handles everything).
The protocol exists to support future multi-agent scenarios and to formalize
bypass modes (cook, brainstorm) as first-class agents.

Domain Agents (kitchen):
- pantry: Kitchen inventory, recipes, meal planning (default)
- cook: Step-by-step cooking guidance (bypass mode)
- brainstorm: Recipe ideation and suggestions (bypass mode)
"""

from alfred.agents.base import (
    AgentProtocol,
    AgentRouter,
    AgentState,
    MultiAgentOrchestrator,
    StreamEvent,
)

__all__ = [
    "AgentProtocol",
    "AgentRouter",
    "AgentState",
    "MultiAgentOrchestrator",
    "StreamEvent",
]
