"""
Alfred Domain Configuration System.

This module provides the abstraction layer that enables Alfred's orchestration
engine to work with different domains (kitchen, FPL, etc.).

The key abstraction is DomainConfig - a protocol that each domain implements
to provide its entities, subdomains, personas, and formatting rules.

Usage:
    from alfred.domain import get_current_domain, DomainConfig

    domain = get_current_domain()
    table = domain.type_to_table["recipe"]  # "recipes"
"""

from alfred.domain.base import (
    DomainConfig,
    EntityDefinition,
    SubdomainDefinition,
)

# Lazy import to avoid circular dependencies
_current_domain: DomainConfig | None = None


def get_current_domain() -> DomainConfig:
    """
    Get the currently configured domain.

    Returns the kitchen domain by default. In the future, this could
    be configured via environment variable or settings.

    Returns:
        The active DomainConfig implementation
    """
    global _current_domain
    if _current_domain is None:
        from alfred.domain.kitchen import KITCHEN_DOMAIN
        _current_domain = KITCHEN_DOMAIN
    return _current_domain


def set_current_domain(domain: DomainConfig) -> None:
    """
    Set the active domain configuration.

    Used primarily for testing or when running multiple domains.

    Args:
        domain: The DomainConfig implementation to use
    """
    global _current_domain
    _current_domain = domain


__all__ = [
    "DomainConfig",
    "EntityDefinition",
    "SubdomainDefinition",
    "get_current_domain",
    "set_current_domain",
]
