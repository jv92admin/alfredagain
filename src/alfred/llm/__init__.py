"""
Alfred V2 - LLM Client.

Provides structured LLM calls via Instructor.
"""

from alfred.llm.client import call_llm, get_client
from alfred.llm.model_router import get_model

__all__ = [
    "get_client",
    "call_llm",
    "get_model",
]
