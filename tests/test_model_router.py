"""
Tests for model router functionality.
"""

import os
import pytest


class TestModelRouter:
    """Tests for model routing based on complexity."""
    
    def test_low_complexity_uses_mini(self):
        """Low complexity should use gpt-4.1-mini."""
        # Force dev mode
        os.environ["ALFRED_USE_ADVANCED_MODELS"] = "false"
        
        # Re-import to get fresh config
        import importlib
        from alfred.llm import model_router
        importlib.reload(model_router)
        
        from alfred.llm.model_router import MODEL_CONFIGS
        
        assert MODEL_CONFIGS["low"]["model"] == "gpt-4.1-mini"
    
    def test_advanced_models_can_be_enabled(self):
        """When advanced models enabled, high complexity should use gpt-5.1."""
        os.environ["ALFRED_USE_ADVANCED_MODELS"] = "true"
        
        import importlib
        from alfred.llm import model_router
        importlib.reload(model_router)
        
        from alfred.llm.model_router import MODEL_CONFIGS
        
        assert MODEL_CONFIGS["high"]["model"] == "gpt-5.1"
        assert MODEL_CONFIGS["medium"]["model"] == "gpt-4.1"
    
    def test_node_temperatures(self):
        """Nodes should have appropriate temperatures."""
        from alfred.llm.model_router import NODE_TEMPERATURE
        
        # Act should be most deterministic
        assert NODE_TEMPERATURE["act"] < NODE_TEMPERATURE["think"]
        
        # Reply can be warmer
        assert NODE_TEMPERATURE["reply"] > NODE_TEMPERATURE["act"]
        
        # Router should be deterministic
        assert NODE_TEMPERATURE["router"] < 0.3
    
    def test_get_node_config(self):
        """get_node_config should merge complexity and node settings."""
        from alfred.llm.model_router import get_node_config
        
        config = get_node_config("act", "low")
        
        assert "model" in config
        assert "temperature" in config
        assert config["temperature"] == 0.25  # Act-specific temperature


class TestCostEstimation:
    """Tests for cost estimation utilities."""
    
    def test_estimate_cost(self):
        """Cost estimation should return reasonable values."""
        from alfred.observability.langsmith import estimate_cost
        
        # 1000 tokens in, 500 out for gpt-4.1-mini
        cost = estimate_cost("gpt-4.1-mini", 1000, 500)
        
        assert cost > 0
        assert cost < 0.01  # Should be very cheap for mini
    
    def test_cost_tracker(self):
        """Cost tracker should accumulate costs."""
        from alfred.observability.langsmith import CostTracker
        
        tracker = CostTracker()
        tracker.add("gpt-4.1-mini", 1000, 500, node="think")
        tracker.add("gpt-4.1-mini", 500, 200, node="act")
        
        assert tracker.total_input_tokens == 1500
        assert tracker.total_output_tokens == 700
        assert tracker.total_cost > 0
        assert len(tracker.calls) == 2
    
    def test_cost_tracker_summary(self):
        """Cost tracker summary should group by model and node."""
        from alfred.observability.langsmith import CostTracker
        
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

