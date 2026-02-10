"""
Tests for Think node complexity mapping.

V3/V4: ThinkStep.complexity is derived from step_type (property, not constructor arg).
adjust_step_complexity() is now a pass-through — complexity escalation is
handled via domain entity definitions (EntityDefinition.complexity).
"""

import pytest
from alfred.graph.state import ThinkStep
from alfred.graph.nodes.think import adjust_step_complexity


class TestStepComplexityProperty:
    """Test ThinkStep.complexity property derivation from step_type."""

    def test_read_is_low(self):
        step = ThinkStep(description="Read recipes", step_type="read", subdomain="recipes")
        assert step.complexity == "low"

    def test_write_is_low(self):
        step = ThinkStep(description="Write item", step_type="write", subdomain="inventory")
        assert step.complexity == "low"

    def test_generate_is_high(self):
        step = ThinkStep(description="Generate recipe", step_type="generate", subdomain="recipes")
        assert step.complexity == "high"

    def test_analyze_is_medium(self):
        step = ThinkStep(description="Analyze inventory", step_type="analyze", subdomain="inventory")
        assert step.complexity == "medium"


class TestAdjustStepComplexity:
    """Test adjust_step_complexity pass-through."""

    def test_returns_same_step(self):
        """adjust_step_complexity should return the step unchanged (V4 behavior)."""
        step = ThinkStep(description="Read recipes", step_type="read", subdomain="recipes")
        adjusted = adjust_step_complexity(step)
        assert adjusted is step

    def test_generate_stays_high(self):
        step = ThinkStep(description="Generate recipe", step_type="generate", subdomain="recipes")
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "high"

    def test_analyze_stays_medium(self):
        step = ThinkStep(description="Analyze ingredients", step_type="analyze", subdomain="recipes")
        adjusted = adjust_step_complexity(step)
        assert adjusted.complexity == "medium"
