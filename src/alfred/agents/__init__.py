"""
Alfred Agent System.

Phase 2.5: Lightweight agent protocol for multi-agent support.

This module provides the abstract interfaces for agents within Alfred:
- AgentProtocol: Base class for all agents (graph-based or streaming)
- AgentRouter: Routes requests to appropriate agents
- MultiAgentOrchestrator: Coordinates multiple agents

Current implementation uses single-agent mode (one default agent handles everything).
The protocol exists to support future multi-agent scenarios and to formalize
domain bypass modes as first-class agents.

Domains register agents via DomainConfig.agents and bypass modes via
DomainConfig.bypass_modes.
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
