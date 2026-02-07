"""
Agent Protocol Definitions.

Phase 2.5: Lightweight agent abstractions for multi-agent support.

This module defines the core interfaces for agents:
- AgentProtocol: Base class for specialized agents
- AgentRouter: Routes requests to appropriate agents
- MultiAgentOrchestrator: Coordinates multiple agents

Design Notes:
- Agents can be graph-based (full LangGraph pipeline) or streaming (bypass modes)
- Current bypass modes (cook, brainstorm) are effectively agents
- Single-agent mode remains the default (no router needed)
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentState:
    """
    Minimal state passed to agents.

    This is a simplified view of AlfredState for agent processing.
    Agents receive what they need without full graph state complexity.
    """

    user_message: str
    user_id: str
    conversation_context: dict[str, Any]
    mode_context: dict[str, Any] | None = None


@dataclass
class StreamEvent:
    """
    Event yielded by streaming agents.

    Matches the event structure used by run_alfred_streaming().
    """

    type: str  # "chunk", "progress", "handoff", "done", etc.
    data: dict[str, Any]


class AgentProtocol(ABC):
    """
    Base protocol for specialized agents within a domain.

    Agents handle specific types of requests or modes. They can be:

    1. **Graph-based (full pipeline)**: Uses LangGraph, returns final state
       Example: The main "main" agent runs the full Think→Act→Reply graph

    2. **Streaming (bypass mode)**: Yields chunks directly, skips graph
       Example: A bypass-mode agent wraps a domain mode runner for guided sessions

    The `is_streaming` property determines which processing model applies.

    Example Implementation:
    ```python
    class BypassAgent(AgentProtocol):
        @property
        def name(self) -> str:
            return "guided_session"

        @property
        def description(self) -> str:
            return "Step-by-step guidance for a specific task"

        @property
        def capabilities(self) -> list[str]:
            return ["guided workflow", "context-aware advice", "step tracking"]

        @property
        def is_streaming(self) -> bool:
            return True  # Bypass mode - yields chunks directly

        async def process_streaming(self, state: AgentState) -> AsyncIterator[StreamEvent]:
            from alfred.domain.{name}.modes.{mode} import run_{mode}_session
            async for event in run_{mode}_session(...):
                yield StreamEvent(type=event["type"], data=event)
    ```
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique agent identifier (e.g., 'pantry', 'cook', 'brainstorm')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this agent does."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """List of capabilities for routing decisions."""
        ...

    @property
    def is_streaming(self) -> bool:
        """
        Whether this agent uses streaming (bypass) mode.

        - True: Agent yields StreamEvents via process_streaming()
        - False: Agent returns final state via process()

        Default is False (graph-based processing).
        """
        return False

    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        Process a request and return final state (graph-based agents).

        Override this for agents that run the full LangGraph pipeline.

        Args:
            state: Agent state with user message and context

        Returns:
            Final state dict after processing
        """
        raise NotImplementedError(
            f"Agent {self.name} must implement process() or process_streaming()"
        )

    async def process_streaming(self, state: AgentState) -> AsyncIterator[StreamEvent]:
        """
        Process a request yielding events (streaming/bypass agents).

        Override this for agents that bypass the graph and stream directly.

        Args:
            state: Agent state with user message and context

        Yields:
            StreamEvent objects for each chunk/progress/completion
        """
        raise NotImplementedError(
            f"Streaming agent {self.name} must implement process_streaming()"
        )
        # Make this a generator
        if False:
            yield StreamEvent(type="done", data={})


class AgentRouter(ABC):
    """
    Routes requests to the appropriate agent.

    The router examines the user message and context to determine
    which agent should handle the request.

    For single-agent domains, no router is needed (returns default agent).
    Multi-agent domains implement routing logic based on:
    - Message content/intent
    - Current mode
    - Conversation history
    - Entity context

    Example Implementation:
    ```python
    class DomainRouter(AgentRouter):
        async def route(self, message: str, context: dict) -> str:
            # Check if in a bypass mode registered by the domain
            mode = context.get("mode")
            if mode in domain.bypass_modes:
                return mode
            # Default to main agent
            return "main"
    ```
    """

    @abstractmethod
    async def route(self, message: str, context: dict[str, Any]) -> str:
        """
        Determine which agent should handle this request.

        Args:
            message: User's message
            context: Conversation and entity context

        Returns:
            Name of the agent to handle the request
        """
        ...


class MultiAgentOrchestrator:
    """
    Coordinates multiple agents within a domain.

    The orchestrator:
    1. Uses the router to determine which agent handles a request
    2. Dispatches to the appropriate agent
    3. Handles streaming vs graph-based agent differences

    For single-agent mode, the domain can return None for router,
    and the orchestrator will always use the default agent.

    Usage:
    ```python
    orchestrator = MultiAgentOrchestrator(
        agents=[MainAgent(), CookAgent(), BrainstormAgent()],
        router=KitchenRouter(),
        default_agent="main",
    )

    # For graph-based processing
    result = await orchestrator.process(state)

    # For streaming
    async for event in orchestrator.process_streaming(state):
        yield event
    ```
    """

    def __init__(
        self,
        agents: list[AgentProtocol],
        router: AgentRouter | None = None,
        default_agent: str,
    ):
        """
        Initialize the orchestrator.

        Args:
            agents: List of available agents
            router: Optional router for multi-agent selection
            default_agent: Agent name to use when router is None
        """
        self.agents: dict[str, AgentProtocol] = {a.name: a for a in agents}
        self.router = router
        self.default_agent = default_agent

    async def get_agent(self, message: str, context: dict[str, Any]) -> AgentProtocol:
        """
        Get the appropriate agent for a request.

        Args:
            message: User's message
            context: Conversation context

        Returns:
            The agent that should handle this request
        """
        if self.router is None:
            agent_name = self.default_agent
        else:
            agent_name = await self.router.route(message, context)

        if agent_name not in self.agents:
            raise ValueError(
                f"Unknown agent '{agent_name}'. "
                f"Available: {list(self.agents.keys())}"
            )

        return self.agents[agent_name]

    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        Process a request using the appropriate agent.

        Args:
            state: Agent state with user message and context

        Returns:
            Final state from the agent

        Raises:
            NotImplementedError: If selected agent is streaming-only
        """
        agent = await self.get_agent(
            state.user_message,
            state.conversation_context,
        )

        if agent.is_streaming:
            raise NotImplementedError(
                f"Agent '{agent.name}' is streaming-only. "
                "Use process_streaming() instead."
            )

        return await agent.process(state)

    async def process_streaming(
        self, state: AgentState
    ) -> AsyncIterator[StreamEvent]:
        """
        Process a request with streaming output.

        Args:
            state: Agent state with user message and context

        Yields:
            StreamEvent objects from the agent
        """
        agent = await self.get_agent(
            state.user_message,
            state.conversation_context,
        )

        if agent.is_streaming:
            async for event in agent.process_streaming(state):
                yield event
        else:
            # Graph-based agent - wrap result as single event
            result = await agent.process(state)
            yield StreamEvent(type="result", data=result)
            yield StreamEvent(type="done", data={})
