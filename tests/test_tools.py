"""
Tests for the Alfred tool system.

Tests cover:
- Tool registry functionality
- Tool summaries and detailed schemas
- Normalization utilities
"""

import pytest

from alfred.tools.registry import ToolRegistry, register_tool
from alfred.tools.normalize import normalize_name, clean_unit, extract_quantity_unit
from alfred.tools.base import make_entity_ref, format_inventory_label


class TestNormalization:
    """Test name and unit normalization utilities."""

    def test_normalize_name_lowercase(self):
        """Should lowercase names."""
        assert normalize_name("Chicken Thighs") == "chicken thighs"
        assert normalize_name("TOMATO") == "tomato"

    def test_normalize_name_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        assert normalize_name("  milk  ") == "milk"
        assert normalize_name("\tchicken\n") == "chicken"

    def test_normalize_name_collapses_spaces(self):
        """Should collapse multiple spaces."""
        assert normalize_name("green   pepper") == "green pepper"
        assert normalize_name("extra   virgin   olive   oil") == "extra virgin olive oil"

    def test_clean_unit_normalizes(self):
        """Should normalize common unit variations."""
        assert clean_unit("LBS") == "lb"
        assert clean_unit("Pounds") == "lb"
        assert clean_unit("ounces") == "oz"
        assert clean_unit("Cups") == "cup"
        assert clean_unit("TABLESPOON") == "tbsp"

    def test_clean_unit_preserves_unknown(self):
        """Should preserve unknown units."""
        assert clean_unit("pinch") == "pinch"
        assert clean_unit("dash") == "dash"

    def test_extract_quantity_unit_basic(self):
        """Should extract quantity and unit from text."""
        qty, unit, name = extract_quantity_unit("3 lbs chicken")
        assert qty == 3.0
        assert unit == "lb"
        assert name == "chicken"

    def test_extract_quantity_unit_fraction(self):
        """Should handle fractions."""
        qty, unit, name = extract_quantity_unit("1/2 cup flour")
        assert qty == 0.5
        assert unit == "cup"
        assert name == "flour"

    def test_extract_quantity_unit_no_quantity(self):
        """Should handle text without quantity."""
        qty, unit, name = extract_quantity_unit("chicken")
        assert qty is None
        assert unit is None
        assert name == "chicken"


class TestEntityRef:
    """Test EntityRef creation utilities."""

    def test_make_entity_ref(self):
        """Should create EntityRef with all fields."""
        ref = make_entity_ref(
            entity_type="inventory_item",
            entity_id="inv_123",
            label="2 lb chicken",
            source="created",
        )
        assert ref.type == "inventory_item"
        assert ref.id == "inv_123"
        assert ref.label == "2 lb chicken"
        assert ref.source == "created"

    def test_format_inventory_label(self):
        """Should format inventory labels nicely."""
        assert format_inventory_label("milk", 2, "gallons") == "2 gallons milk"
        assert format_inventory_label("butter", 0.5, "lb") == "0.5 lb butter"

    def test_format_inventory_label_whole_number(self):
        """Should use whole numbers when quantity is integer."""
        assert format_inventory_label("eggs", 12.0, "pieces") == "12 pieces eggs"


class TestToolRegistry:
    """Test the tool registry system."""

    def test_registry_is_singleton(self):
        """Registry should be a singleton."""
        reg1 = ToolRegistry()
        reg2 = ToolRegistry()
        assert reg1 is reg2

    def test_register_and_retrieve_tool(self):
        """Should register and retrieve tools."""
        registry = ToolRegistry()
        registry.clear()  # Start fresh

        async def test_tool(user_id: str, name: str) -> dict:
            """A test tool."""
            return {"name": name}

        registry.register(
            name="test_tool",
            fn=test_tool,
            agent="test",
            summary="A test tool",
            category="test",
        )

        tool = registry.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"
        assert tool.summary == "A test tool"
        assert tool.agent == "test"

    def test_get_tools_for_agent(self):
        """Should return tools for specific agent."""
        registry = ToolRegistry()
        registry.clear()

        async def tool_a(user_id: str) -> dict:
            return {}

        async def tool_b(user_id: str) -> dict:
            return {}

        registry.register("tool_a", tool_a, "pantry", "Tool A", "vault")
        registry.register("tool_b", tool_b, "coach", "Tool B", "vault")

        pantry_tools = registry.get_tools_for_agent("pantry")
        assert len(pantry_tools) == 1
        assert pantry_tools[0].name == "tool_a"

    def test_shared_tools_available_to_all_agents(self):
        """Shared tools should be available to all agents."""
        registry = ToolRegistry()
        registry.clear()

        async def shared_tool(user_id: str) -> dict:
            return {}

        async def agent_tool(user_id: str) -> dict:
            return {}

        registry.register("shared_tool", shared_tool, "shared", "Shared", "cross")
        registry.register("agent_tool", agent_tool, "pantry", "Agent", "vault")

        pantry_tools = registry.get_tools_for_agent("pantry")
        tool_names = {t.name for t in pantry_tools}

        assert "shared_tool" in tool_names
        assert "agent_tool" in tool_names

    def test_get_summaries(self):
        """Should return formatted tool summaries."""
        registry = ToolRegistry()
        registry.clear()

        async def tool_a(user_id: str) -> dict:
            return {}

        async def tool_b(user_id: str) -> dict:
            return {}

        registry.register("manage_inventory", tool_a, "pantry", "Add, update, remove items", "vault")
        registry.register("query_inventory", tool_b, "pantry", "Search inventory", "vault")

        summaries = registry.get_summaries("pantry")

        assert "VAULT:" in summaries
        assert "manage_inventory: Add, update, remove items" in summaries
        assert "query_inventory: Search inventory" in summaries

    def test_get_detailed_schemas(self):
        """Should return detailed schemas for specific tools."""
        registry = ToolRegistry()
        registry.clear()

        async def my_tool(
            user_id: str,
            name: str,
            quantity: float = 1.0,
        ) -> dict:
            """Add an item to inventory."""
            return {}

        registry.register("my_tool", my_tool, "pantry", "My tool", "vault")

        schemas = registry.get_detailed_schemas(["my_tool"])

        assert "my_tool(" in schemas
        assert "name:" in schemas
        assert "quantity:" in schemas

    def test_decorator_registration(self):
        """The @register_tool decorator should work."""
        # Get a fresh registry and reimport tools
        from alfred.tools.registry import ToolRegistry
        
        # Get the singleton (which may have been cleared)
        registry = ToolRegistry()
        
        # Reimport to trigger decorator registration
        import importlib
        from alfred.tools import vaults
        importlib.reload(vaults.inventory)
        
        tool = registry.get_tool("manage_inventory")
        assert tool is not None
        assert tool.agent == "pantry"


class TestToolSummaryFormat:
    """Test that tool summaries are formatted correctly for LLM consumption."""

    def test_summaries_are_grouped_by_category(self):
        """Summaries should be grouped by category."""
        registry = ToolRegistry()
        registry.clear()

        async def vault_tool(user_id: str) -> dict:
            return {}

        async def cross_tool(user_id: str) -> dict:
            return {}

        registry.register("vault_tool", vault_tool, "pantry", "Vault", "vault")
        registry.register("cross_tool", cross_tool, "pantry", "Cross", "cross")

        summaries = registry.get_summaries("pantry")

        # Categories should appear
        assert "VAULT:" in summaries
        assert "CROSS:" in summaries

    def test_unknown_tool_in_schemas(self):
        """Should handle unknown tools gracefully."""
        registry = ToolRegistry()
        registry.clear()

        schemas = registry.get_detailed_schemas(["nonexistent_tool"])
        assert "Unknown tool: nonexistent_tool" in schemas

