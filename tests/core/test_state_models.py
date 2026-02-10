"""
Tests for core graph state models.

These models are domain-agnostic — they work with any DomainConfig.
"""

import pytest

from alfred.graph.state import (
    AlfredState,
    EntityRef,
    RouterOutput,
    ThinkStep,
    ThinkOutput,
    StepCompleteAction,
)


class TestEntityRef:
    """Test EntityRef creation and fields."""

    def test_creation(self):
        ref = EntityRef(
            type="item",
            id="item_1",
            label="Widget",
            source="db_lookup",
        )
        assert ref.type == "item"
        assert ref.id == "item_1"
        assert ref.label == "Widget"
        assert ref.source == "db_lookup"

    def test_source_values(self):
        for source in ("db_lookup", "user_input", "generated"):
            ref = EntityRef(type="note", id="note_1", label="N", source=source)
            assert ref.source == source


class TestRouterOutput:
    """Test RouterOutput creation."""

    def test_creation(self):
        output = RouterOutput(
            agent="main",
            goal="Add item to list",
            complexity="low",
        )
        assert output.agent == "main"
        assert output.goal == "Add item to list"
        assert output.complexity == "low"


class TestThinkStep:
    """Test ThinkStep (V3 step types: read, analyze, generate, write)."""

    def test_read_step(self):
        step = ThinkStep(
            description="Find matching items",
            step_type="read",
            subdomain="items",
            group=0,
        )
        assert step.step_type == "read"
        assert step.subdomain == "items"
        assert step.group == 0

    def test_write_step(self):
        step = ThinkStep(
            description="Create a new item",
            step_type="write",
            subdomain="items",
            group=1,
        )
        assert step.step_type == "write"
        assert step.group == 1


class TestThinkOutput:
    """Test ThinkOutput with steps."""

    def test_creation_with_steps(self):
        output = ThinkOutput(
            goal="Add item to list",
            steps=[
                ThinkStep(
                    description="Add item",
                    step_type="write",
                    subdomain="items",
                    complexity="low",
                ),
            ],
        )
        assert len(output.steps) == 1
        assert output.steps[0].description == "Add item"
        assert output.steps[0].subdomain == "items"


class TestStepCompleteAction:
    """Test StepCompleteAction."""

    def test_creation(self):
        action = StepCompleteAction(
            result_summary="Added 2 items",
            data={"id": "item_1", "name": "Widget", "quantity": 2},
        )
        assert action.action == "step_complete"
        assert action.result_summary == "Added 2 items"
        assert action.data is not None


class TestAlfredState:
    """Test AlfredState TypedDict."""

    def test_creation(self):
        state: AlfredState = {
            "user_id": "user_123",
            "user_message": "Add a widget to my list",
            "router_output": None,
            "think_output": None,
            "context": {},
            "current_step_index": 0,
            "completed_steps": [],
            "pending_action": None,
            "final_response": None,
            "error": None,
        }
        assert state["user_message"] == "Add a widget to my list"
        assert state["current_step_index"] == 0
