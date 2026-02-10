"""
Alfred Domain Configuration System.

This module provides the abstraction layer that enables Alfred's orchestration
engine to work with different domains (kitchen, FPL, etc.).

The key abstraction is DomainConfig - a protocol that each domain implements
to provide its entities, subdomains, personas, and formatting rules.

Usage:
    from alfred.domain import register_domain, get_current_domain, DomainConfig

    # At app startup:
    register_domain(my_domain)

    # Anywhere in core:
    domain = get_current_domain()
"""

from alfred.domain.base import (
    DomainConfig,
    EntityDefinition,
    SubdomainDefinition,
)

_current_domain: DomainConfig | None = None


def register_domain(domain: DomainConfig) -> None:
    """
    Register the active domain configuration.

    Must be called at app startup before any core functions are used.
    Each domain application (kitchen, FPL, etc.) calls this once.

    Args:
        domain: The DomainConfig implementation to use
    """
    global _current_domain
    _current_domain = domain


def get_current_domain() -> DomainConfig:
    """
    Get the currently registered domain.

    Falls back to kitchen domain auto-import for backwards compatibility.
    This fallback will be removed in Phase 4b when all entry points
    use explicit register_domain() calls.

    Returns:
        The active DomainConfig implementation

    Raises:
        RuntimeError: If no domain is registered (after fallback removal)
    """
    global _current_domain
    if _current_domain is None:
        # Backwards-compat fallback — import alfred_kitchen triggers registration
        import alfred_kitchen  # noqa: F401
        if _current_domain is None:
            raise RuntimeError(
                "No domain registered. Import alfred_kitchen or call register_domain()."
            )
    return _current_domain


# Deprecated alias — use register_domain() instead
set_current_domain = register_domain


__all__ = [
    "DomainConfig",
    "EntityDefinition",
    "SubdomainDefinition",
    "register_domain",
    "get_current_domain",
    "set_current_domain",  # deprecated alias
]
