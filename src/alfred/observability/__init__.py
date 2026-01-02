"""
Alfred V3 - Observability Package.

Provides:
- LangSmith tracing integration
- Session logging (JSONL files)
- Cost tracking
- Performance metrics
"""

from alfred.observability.langsmith import (
    init_langsmith,
    trace_llm_call,
    get_run_url,
)

from alfred.observability.session_logger import (
    SessionLogger,
    get_session_logger,
    init_session_logger,
    close_session_logger,
)

__all__ = [
    # LangSmith
    "init_langsmith",
    "trace_llm_call",
    "get_run_url",
    # Session logging
    "SessionLogger",
    "get_session_logger",
    "init_session_logger",
    "close_session_logger",
]

