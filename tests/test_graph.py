"""
Tests for the Alfred LangGraph workflow.

These tests verify the graph structure and basic flow.
"""

import pytest

from alfred.graph.state import (
    AlfredState,
    EntityRef,
    RouterOutput,
    PlannedStep,
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
            agent="pantry",
            goal="Add milk to inventory",
            complexity="low",
            context_needs=["inventory"],
        )
        assert output.agent == "pantry"
        assert output.complexity == "low"

    def test_think_output_with_planned_step(self):
        """ThinkOutput should use PlannedStep with tool assignments."""
        output = ThinkOutput(
            goal="Add milk to inventory",
            steps=[
                PlannedStep(
                    description="Add item to inventory",
                    tools=["manage_inventory"],
                    complexity="low",
                ),
            ],
        )
        assert len(output.steps) == 1
        assert output.steps[0].description == "Add item to inventory"
        assert output.steps[0].tools == ["manage_inventory"]

    def test_planned_step_with_multiple_tools(self):
        """PlannedStep can have 1-3 tools assigned."""
        step = PlannedStep(
            description="Find matching recipes",
            tools=["suggest_recipes", "query_recipe"],
            complexity="medium",
        )
        assert len(step.tools) == 2
        assert "suggest_recipes" in step.tools
        assert "query_recipe" in step.tools

    def test_step_complete_action_creation(self):
        """StepCompleteAction should be creatable with refs."""
        action = StepCompleteAction(
            step_name="Add item",
            result_summary="Added 2 cartons of milk",
            refs=[
                EntityRef(
                    type="inventory_item",
                    id="inv_456",
                    label="Milk (2 cartons)",
                    source="created",
                )
            ],
        )
        assert action.action == "step_complete"
        assert len(action.refs) == 1


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
