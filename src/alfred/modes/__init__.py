"""
Alfred modes — lightweight conversation modes that bypass the LangGraph graph.

Cook and Brainstorm modes are standalone async generators that share session
infrastructure (auth, conversation persistence, SSE) but skip the full
Understand → Think → Act → Reply → Summarize pipeline.
"""

from alfred.modes.cook import run_cook_session
from alfred.modes.brainstorm import run_brainstorm

__all__ = ["run_cook_session", "run_brainstorm"]
