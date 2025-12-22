"""Basic health check tests."""

import pytest


def test_import_alfred():
    """Test that alfred package can be imported."""
    import alfred
    assert alfred.__version__ == "2.0.0"


def test_import_state():
    """Test that state models can be imported."""
    from alfred.graph.state import (
        EntityRef,
        RouterOutput,
        ThinkOutput,
        AlfredState,
    )
    
    # Create a simple EntityRef
    ref = EntityRef(
        type="ingredient",
        id="ing_123",
        label="Tomato",
        source="db_lookup",
    )
    assert ref.type == "ingredient"
    assert ref.id == "ing_123"

