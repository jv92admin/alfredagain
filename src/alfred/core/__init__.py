"""
Alfred V4 Core - Data models for ID registry and mode system.

V4 CONSOLIDATION: Entity, EntityRegistry, EntityState removed.
SessionIdRegistry is now the single source of truth.
"""

from alfred.core.id_registry import SessionIdRegistry
from alfred.core.modes import Mode, ModeContext

__all__ = [
    "SessionIdRegistry",
    "Mode",
    "ModeContext",
]
