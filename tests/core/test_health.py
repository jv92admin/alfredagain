"""
Core health check — verify alfred package imports without kitchen.
"""

import pytest


def test_import_alfred():
    """Test that alfred package can be imported."""
    import alfred
    assert alfred.__version__ == "2.0.0"


def test_import_state_models():
    """Test that state models can be imported."""
    from alfred.graph.state import (
        EntityRef,
        RouterOutput,
        ThinkStep,
        AlfredState,
    )
    ref = EntityRef(type="item", id="item_1", label="Widget", source="db_lookup")
    assert ref.type == "item"


def test_import_domain_config():
    """Test that domain config can be imported."""
    from alfred.domain.base import DomainConfig, EntityDefinition, SubdomainDefinition
    assert DomainConfig is not None


def test_import_core_settings():
    """Test that CoreSettings can be imported without kitchen."""
    from alfred.config import CoreSettings
    assert CoreSettings is not None


def test_import_modes():
    """Test that core modes can be imported."""
    from alfred.core.modes import Mode, MODE_CONFIG
    assert Mode.PLAN.value == "plan"
    assert Mode.PLAN in MODE_CONFIG
