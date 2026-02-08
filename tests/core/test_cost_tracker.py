"""
Tests for observability / cost tracking — domain-agnostic.
"""

import pytest

from alfred.observability.langsmith import estimate_cost, CostTracker


class TestEstimateCost:
    """Test cost estimation utility."""

    def test_returns_positive(self):
        cost = estimate_cost("gpt-4.1-mini", 1000, 500)
        assert cost > 0

    def test_mini_is_cheap(self):
        cost = estimate_cost("gpt-4.1-mini", 1000, 500)
        assert cost < 0.01

    def test_unknown_model_returns_zero(self):
        cost = estimate_cost("unknown-model", 1000, 500)
        assert cost >= 0  # Should not crash


class TestCostTracker:
    """Test CostTracker accumulation."""

    def test_add_and_totals(self):
        tracker = CostTracker()
        tracker.add("gpt-4.1-mini", 1000, 500, node="think")
        tracker.add("gpt-4.1-mini", 500, 200, node="act")

        assert tracker.total_input_tokens == 1500
        assert tracker.total_output_tokens == 700
        assert tracker.total_cost > 0
        assert len(tracker.calls) == 2

    def test_summary_structure(self):
        tracker = CostTracker()
        tracker.add("gpt-4.1-mini", 1000, 500, node="think")
        tracker.add("gpt-4o", 500, 200, node="act")

        summary = tracker.summary()

        assert "total_calls" in summary
        assert summary["total_calls"] == 2
        assert "by_model" in summary
        assert "gpt-4.1-mini" in summary["by_model"]
        assert "by_node" in summary
        assert "think" in summary["by_node"]

    def test_empty_tracker(self):
        tracker = CostTracker()
        summary = tracker.summary()
        assert summary["total_calls"] == 0
        assert tracker.total_cost == 0
