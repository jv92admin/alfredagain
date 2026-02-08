"""
Tests for the Alfred LangGraph workflow.

These tests verify the graph structure and basic flow.
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
from alfred.graph.workflow import create_alfred_graph


class TestGraphStructure:
    """Test that the graph is correctly structured."""

    def test_graph_has_expected_nodes(self):
        """Graph should have router, think, act, reply nodes."""
        graph = create_alfred_graph()
        
        # Access the nodes from the graph builder
        node_names = set(graph.nodes.keys())
        
        expected_nodes = {"router", "think", "act", "reply"}
        assert expected_nodes.issubset(node_names), f"Missing nodes: {expected_nodes - node_names}"

    def test_graph_compiles(self):
        """Graph should compile without errors."""
        from alfred.graph.workflow import compile_alfred_graph
        
        compiled = compile_alfred_graph()
        # If we get here without error, the graph is valid
        assert compiled is not None


class TestStateModels:
    """Test the Pydantic models for graph state."""

    def test_entity_ref_creation(self):
        """EntityRef should be creatable with all fields."""
        ref = EntityRef(
            type="ingredient",
            id="ing_123",
            label="Tomato",
            source="db_lookup",
        )
        assert ref.type == "ingredient"
        assert ref.id == "ing_123"
        assert ref.label == "Tomato"
        assert ref.source == "db_lookup"

    def test_router_output_creation(self):
        """RouterOutput should be creatable with required fields."""
        output = RouterOutput(
            agent="main",
            goal="Add milk to inventory",
            complexity="low",
            context_needs=["inventory"],
        )
        assert output.agent == "main"
        assert output.complexity == "low"

    def test_think_output_with_steps(self):
        """ThinkOutput should use ThinkStep with subdomain hints."""
        output = ThinkOutput(
            goal="Add milk to inventory",
            steps=[
                ThinkStep(
                    description="Add item to inventory",
                    step_type="write",
                    subdomain="inventory",
                ),
            ],
        )
        assert len(output.steps) == 1
        assert output.steps[0].description == "Add item to inventory"
        assert output.steps[0].subdomain == "inventory"
        assert output.steps[0].subdomain == "inventory"

    def test_think_step_v3_types(self):
        """ThinkStep should use V3 step types: read, analyze, generate, write."""
        step = ThinkStep(
            description="Find matching recipes",
            step_type="read",
            subdomain="recipes",
            group=0,
        )
        assert step.step_type == "read"
        assert step.subdomain == "recipes"
        assert step.group == 0

    def test_step_complete_action_creation(self):
        """StepCompleteAction should be creatable with result_summary."""
        action = StepCompleteAction(
            result_summary="Added 2 cartons of milk",
            data={"id": "inv_456", "name": "milk", "quantity": 2},
        )
        assert action.action == "step_complete"
        assert action.result_summary == "Added 2 cartons of milk"
        assert action.data is not None


class TestAlfredState:
    """Test the AlfredState TypedDict."""

    def test_state_can_be_created(self):
        """AlfredState should be creatable as a dict."""
        state: AlfredState = {
            "user_id": "user_123",
            "user_message": "Add milk to my pantry",
            "router_output": None,
            "think_output": None,
            "context": {},
            "current_step_index": 0,
            "completed_steps": [],
            "pending_action": None,
            "final_response": None,
            "error": None,
        }
        assert state["user_message"] == "Add milk to my pantry"
        assert state["current_step_index"] == 0
