"""
Tests for core Mode enum and ModeContext — domain-agnostic.
"""

import pytest

from alfred.core.modes import Mode, MODE_CONFIG, ModeContext, get_verbosity_label


class TestModeEnum:
    """Test Mode enum values."""

    def test_core_modes_exist(self):
        assert Mode.QUICK.value == "quick"
        assert Mode.PLAN.value == "plan"
        assert Mode.CREATE.value == "create"

    def test_no_kitchen_bypass_modes_in_core_enum(self):
        """Core Mode enum should NOT contain cook/brainstorm."""
        mode_values = {m.value for m in Mode}
        assert "cook" not in mode_values
        assert "brainstorm" not in mode_values


class TestModeConfig:
    """Test MODE_CONFIG structure."""

    def test_all_modes_have_config(self):
        for mode in Mode:
            assert mode in MODE_CONFIG, f"Missing config for {mode}"

    def test_plan_config(self):
        config = MODE_CONFIG[Mode.PLAN]
        assert config["max_steps"] == 8
        assert config["skip_think"] is False
        assert config["proposal_required"] is True
        assert config["verbosity"] == "detailed"

    def test_quick_config(self):
        config = MODE_CONFIG[Mode.QUICK]
        assert config["max_steps"] == 2
        assert config["skip_think"] is True
        assert config["verbosity"] == "terse"

    def test_create_config(self):
        config = MODE_CONFIG[Mode.CREATE]
        assert config["max_steps"] == 4
        assert config["skip_think"] is False
        assert config["verbosity"] == "rich"

    def test_no_bypass_graph_in_core_modes(self):
        """Core modes should not have bypass_graph flag."""
        for mode in Mode:
            config = MODE_CONFIG[mode]
            assert config.get("bypass_graph") is None or config.get("bypass_graph") is False


class TestModeContext:
    """Test ModeContext dataclass."""

    def test_default(self):
        ctx = ModeContext.default()
        assert ctx.selected_mode == Mode.PLAN

    def test_max_steps(self):
        ctx = ModeContext(selected_mode=Mode.QUICK)
        assert ctx.max_steps == 2

    def test_round_trip(self):
        ctx = ModeContext(selected_mode=Mode.CREATE)
        data = ctx.to_dict()
        restored = ModeContext.from_dict(data)
        assert restored.selected_mode == Mode.CREATE

    def test_verbosity(self):
        ctx = ModeContext(selected_mode=Mode.PLAN)
        assert ctx.verbosity == "detailed"


class TestVerbosityLabel:
    """Test get_verbosity_label."""

    def test_plan_verbosity(self):
        label = get_verbosity_label(Mode.PLAN)
        assert isinstance(label, str)
        assert len(label) > 0
