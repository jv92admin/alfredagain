"""
Alfred V3 Prompts - Modular prompt assembly.

This module provides:
- Step-type-specific prompt injection
- Subdomain personas and scope
- Contextual examples for Act steps
"""

from alfred.prompts.injection import build_act_prompt, get_verbosity_label
from alfred.prompts.personas import (
    SUBDOMAIN_INTRO,
    SUBDOMAIN_PERSONAS,
    SUBDOMAIN_SCOPE,
    get_subdomain_intro,
    get_persona_for_subdomain,
    get_scope_for_subdomain,
    get_subdomain_dependencies_summary,
    get_full_subdomain_content,
)
from alfred.prompts.examples import get_contextual_examples

__all__ = [
    # Injection
    "build_act_prompt",
    "get_verbosity_label",
    # Personas
    "SUBDOMAIN_INTRO",
    "SUBDOMAIN_PERSONAS",
    "SUBDOMAIN_SCOPE",
    "get_subdomain_intro",
    "get_persona_for_subdomain",
    "get_scope_for_subdomain",
    "get_subdomain_dependencies_summary",
    "get_full_subdomain_content",
    # Examples
    "get_contextual_examples",
]

