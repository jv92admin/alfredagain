"""
Alfred Kitchen — kitchen management domain for Alfred.

Importing this package registers the kitchen domain with Alfred's core.
"""

from alfred.domain import register_domain


def _register():
    """Register KITCHEN_DOMAIN with core. Called at import time."""
    from alfred_kitchen.domain import KITCHEN_DOMAIN
    register_domain(KITCHEN_DOMAIN)


_register()
