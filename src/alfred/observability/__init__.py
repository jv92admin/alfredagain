"""
Alfred V2 - Observability Package.

Provides:
- LangSmith tracing integration
- Cost tracking
- Performance metrics
"""

from alfred.observability.langsmith import (
    init_langsmith,
    trace_llm_call,
    get_run_url,
)

__all__ = [
    "init_langsmith",
    "trace_llm_call",
    "get_run_url",
]

