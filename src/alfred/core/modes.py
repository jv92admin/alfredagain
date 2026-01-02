"""
Alfred V3 - Mode System.

Modes control complexity adaptation:
- QUICK: 1-2 steps, minimal planning, terse responses
- COOK: 2-4 steps, recipe-focused, light confirmation
- PLAN: 4-8 steps, full planning, explicit proposals
- CREATE: 2-4 steps, generation-focused, rich output

Mode Selection:
1. Primary: User selects mode in UI (explicit, reliable)
2. Secondary: CLI --mode flag
3. Fallback: User profile default
"""

from dataclasses import dataclass
from enum import Enum


class Mode(Enum):
    """User interaction modes."""
    
    QUICK = "quick"    # 1-2 steps, minimal planning
    COOK = "cook"      # Quick + recipe focus
    PLAN = "plan"      # Full pipeline
    CREATE = "create"  # Generation-focused


# Mode behavior configuration
MODE_CONFIG = {
    Mode.QUICK: {
        "max_steps": 2,
        "skip_think": True,         # Go directly to Act
        "proposal_required": False,
        "verbosity": "terse",
        "examples_in_prompt": False,
        "profile_detail": "minimal",
    },
    Mode.COOK: {
        "max_steps": 4,
        "skip_think": False,
        "proposal_required": False,
        "verbosity": "focused",
        "examples_in_prompt": True,
        "profile_detail": "compact",
    },
    Mode.PLAN: {
        "max_steps": 8,
        "skip_think": False,
        "proposal_required": True,  # For complex requests
        "verbosity": "detailed",
        "examples_in_prompt": True,
        "profile_detail": "full",
    },
    Mode.CREATE: {
        "max_steps": 4,
        "skip_think": False,
        "proposal_required": False,  # Optional
        "verbosity": "rich",
        "examples_in_prompt": False,  # Creative freedom
        "profile_detail": "full",
    },
}


@dataclass
class ModeContext:
    """
    Current mode context for a request.
    
    Mode is determined by:
    1. UI/CLI selection (explicit)
    2. User profile default (fallback)
    """
    
    selected_mode: Mode          # Current mode for this request
    profile_default: Mode | None = None  # User's default from profile
    
    @property
    def config(self) -> dict:
        """Get configuration for current mode."""
        return MODE_CONFIG[self.selected_mode]
    
    @property
    def max_steps(self) -> int:
        return self.config["max_steps"]
    
    @property
    def skip_think(self) -> bool:
        return self.config["skip_think"]
    
    @property
    def proposal_required(self) -> bool:
        return self.config["proposal_required"]
    
    @property
    def verbosity(self) -> str:
        return self.config["verbosity"]
    
    @property
    def examples_in_prompt(self) -> bool:
        return self.config["examples_in_prompt"]
    
    @property
    def profile_detail(self) -> str:
        return self.config["profile_detail"]
    
    def to_dict(self) -> dict:
        """Serialize for state storage."""
        return {
            "selected_mode": self.selected_mode.value,
            "profile_default": self.profile_default.value if self.profile_default else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModeContext":
        """Deserialize from dict."""
        return cls(
            selected_mode=Mode(data["selected_mode"]),
            profile_default=Mode(data["profile_default"]) if data.get("profile_default") else None,
        )
    
    @classmethod
    def default(cls) -> "ModeContext":
        """Default mode context (Plan mode)."""
        return cls(selected_mode=Mode.PLAN)


def get_verbosity_label(mode: Mode) -> str:
    """Get human-readable verbosity label for prompt injection."""
    return MODE_CONFIG[mode]["verbosity"]

