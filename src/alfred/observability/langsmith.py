"""
Alfred V2 - LangSmith Integration.

Provides tracing and observability through LangSmith:
- Automatic trace initialization
- Run tracking with metadata
- Cost estimation per request

To enable:
1. Set LANGCHAIN_TRACING_V2=true
2. Set LANGCHAIN_API_KEY=<your-key>
3. Set LANGCHAIN_PROJECT=alfred-v2 (optional)

Traces will appear at: https://smith.langchain.com/
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import uuid4

# LangSmith client (optional import)
try:
    from langsmith import Client as LangSmithClient
    from langsmith.run_trees import RunTree
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    LangSmithClient = None
    RunTree = None


# Global state
_langsmith_client: Any = None
_tracing_enabled: bool = False


def init_langsmith() -> bool:
    """
    Initialize LangSmith tracing if configured.
    
    Returns True if tracing is enabled, False otherwise.
    Call this once at application startup.
    """
    global _langsmith_client, _tracing_enabled
    
    if not LANGSMITH_AVAILABLE:
        print("ℹ️  LangSmith not available (langsmith package not installed)")
        return False
    
    # Check environment variables
    tracing_enabled = os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
    api_key = os.environ.get("LANGCHAIN_API_KEY")
    project = os.environ.get("LANGCHAIN_PROJECT", "alfred-v2")
    
    if not tracing_enabled:
        print("ℹ️  LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true to enable)")
        return False
    
    if not api_key:
        print("⚠️  LangSmith API key not set (LANGCHAIN_API_KEY)")
        return False
    
    try:
        _langsmith_client = LangSmithClient()
        _tracing_enabled = True
        print(f"✅ LangSmith tracing enabled for project: {project}")
        return True
    except Exception as e:
        print(f"⚠️  Failed to initialize LangSmith: {e}")
        return False


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled."""
    return _tracing_enabled


@asynccontextmanager
async def trace_llm_call(
    name: str,
    run_type: str = "chain",
    inputs: dict | None = None,
    metadata: dict | None = None,
):
    """
    Context manager for tracing an LLM call or chain.
    
    Usage:
        async with trace_llm_call("think_node", inputs={"goal": goal}) as run:
            result = await call_llm(...)
            run.end(outputs={"steps": result.steps})
    """
    if not _tracing_enabled or not LANGSMITH_AVAILABLE:
        # No-op context manager
        yield type("MockRun", (), {"end": lambda self, **kwargs: None})()
        return
    
    run_id = str(uuid4())
    project = os.environ.get("LANGCHAIN_PROJECT", "alfred-v2")
    
    run = RunTree(
        name=name,
        run_type=run_type,
        inputs=inputs or {},
        extra=metadata or {},
        project_name=project,
        id=run_id,
    )
    
    try:
        run.post()
        yield run
    except Exception as e:
        run.end(error=str(e))
        run.patch()
        raise
    else:
        run.patch()


def get_run_url(run_id: str) -> str | None:
    """
    Get the LangSmith URL for a specific run.
    
    Returns None if tracing is disabled.
    """
    if not _tracing_enabled:
        return None
    
    project = os.environ.get("LANGCHAIN_PROJECT", "alfred-v2")
    return f"https://smith.langchain.com/o/{project}/runs/{run_id}"


# Cost estimation (based on OpenAI pricing as of Dec 2024)
MODEL_COSTS = {
    # Per 1M tokens
    "gpt-4.1-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5": {"input": 1.25, "output": 10.00},
    "gpt-5.1": {"input": 1.25, "output": 10.00},
    "gpt-5.2": {"input": 1.75, "output": 14.00},
    "gpt-5-pro": {"input": 15.00, "output": 120.00},
    "gpt-5.2-pro": {"input": 21.00, "output": 168.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.00},
}


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Estimate the cost of an LLM call.
    
    Returns cost in USD.
    """
    costs = MODEL_COSTS.get(model, MODEL_COSTS["gpt-4.1-mini"])
    
    input_cost = (input_tokens / 1_000_000) * costs["input"]
    output_cost = (output_tokens / 1_000_000) * costs["output"]
    
    return input_cost + output_cost


class CostTracker:
    """
    Track cumulative costs across a session.
    
    Usage:
        tracker = CostTracker()
        tracker.add("gpt-4.1-mini", 500, 100)
        tracker.add("gpt-4o", 200, 50)
        print(tracker.total_cost)
    """
    
    def __init__(self):
        self.calls: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
    
    def add(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        node: str = "unknown",
    ) -> float:
        """Add a call and return its estimated cost."""
        cost = estimate_cost(model, input_tokens, output_tokens)
        
        self.calls.append({
            "timestamp": datetime.utcnow().isoformat(),
            "model": model,
            "node": node,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        })
        
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        
        return cost
    
    def summary(self) -> dict:
        """Get a summary of tracked costs."""
        return {
            "total_calls": len(self.calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "by_model": self._costs_by_model(),
            "by_node": self._costs_by_node(),
        }
    
    def _costs_by_model(self) -> dict[str, float]:
        """Get costs grouped by model."""
        by_model: dict[str, float] = {}
        for call in self.calls:
            model = call["model"]
            by_model[model] = by_model.get(model, 0.0) + call["cost"]
        return {k: round(v, 6) for k, v in by_model.items()}
    
    def _costs_by_node(self) -> dict[str, float]:
        """Get costs grouped by node."""
        by_node: dict[str, float] = {}
        for call in self.calls:
            node = call["node"]
            by_node[node] = by_node.get(node, 0.0) + call["cost"]
        return {k: round(v, 6) for k, v in by_node.items()}


# Global cost tracker for session-level tracking
_session_tracker: CostTracker | None = None


def get_session_tracker() -> CostTracker:
    """Get or create the session cost tracker."""
    global _session_tracker
    if _session_tracker is None:
        _session_tracker = CostTracker()
    return _session_tracker


def reset_session_tracker() -> None:
    """Reset the session cost tracker."""
    global _session_tracker
    _session_tracker = CostTracker()

