"""
Multi-turn scenario runner for testing specific conversation flows.

Usage:
    python tests/scenario_runner.py                              # Run all scenarios
    python tests/scenario_runner.py gen_artifact_flow            # Run specific scenario
    python tests/scenario_runner.py --list                       # List available scenarios
    python tests/scenario_runner.py --user <user_id> <scenario>  # Use specific user ID

Environment:
    ALFRED_TEST_USER_ID  - Default user ID for testing (if --user not provided)

Logs are written to: tests/scenario_logs/<scenario_name>_<timestamp>/
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alfred.graph.workflow import run_alfred
from alfred.memory.conversation import initialize_conversation

# Default test user - override with --user or ALFRED_TEST_USER_ID env var
DEFAULT_TEST_USER = "00000000-0000-0000-0000-000000000001"


@dataclass
class Turn:
    """A single turn in a scenario."""
    user_message: str
    description: str = ""
    # Optional: verify something about the state after this turn
    verify: Callable[[dict, str], bool] | None = None


@dataclass
class Scenario:
    """A multi-turn test scenario."""
    name: str
    description: str
    turns: list[Turn] = field(default_factory=list)


# =============================================================================
# Scenario Definitions
# =============================================================================

SCENARIOS: dict[str, Scenario] = {}


def register_scenario(scenario: Scenario):
    """Register a scenario for running."""
    SCENARIOS[scenario.name] = scenario
    return scenario


# -----------------------------------------------------------------------------
# Scenario: Generated Artifact Flow
# Tests: generate → modify → save
# -----------------------------------------------------------------------------
register_scenario(Scenario(
    name="gen_artifact_flow",
    description="Test generating a recipe, modifying it, then saving",
    turns=[
        Turn(
            user_message="Generate a simple Thai basil chicken recipe for me",
            description="Generate initial recipe - should create gen_recipe_1",
        ),
        Turn(
            user_message="Add a squeeze of lime at the end to brighten it",
            description="Modify gen_recipe_1 - should use generate step, not write",
        ),
        Turn(
            user_message="Perfect, save that recipe",
            description="Save gen_recipe_1 - should use write step with db_create",
        ),
    ],
))


# -----------------------------------------------------------------------------
# Scenario: Read Rerouting
# Tests: generate → filler turns → read back (via rerouting from pending_artifacts)
# -----------------------------------------------------------------------------
register_scenario(Scenario(
    name="read_rerouting",
    description="Test reading a generated artifact after it fades from active context",
    turns=[
        Turn(
            user_message="Generate a simple shakshuka recipe for me",
            description="Generate recipe - creates gen_recipe_1",
        ),
        Turn(
            user_message="Add a dozen eggs to my fridge",
            description="Unrelated inventory action - pushes gen_recipe_1 back in context",
        ),
        Turn(
            user_message="Actually remove those eggs, I already have some",
            description="Another unrelated action - gen_recipe_1 should fade from active entities",
        ),
        Turn(
            user_message="Show me that shakshuka recipe you made earlier",
            description="Read gen_recipe_1 - should trigger read rerouting (not in active context)",
        ),
        Turn(
            user_message="Add crumbled feta on top as a finishing touch",
            description="Modify gen_recipe_1 - should use generate step",
        ),
        Turn(
            user_message="Save that recipe",
            description="Save gen_recipe_1 - should use write step with db_create",
        ),
    ],
))


# -----------------------------------------------------------------------------
# Scenario: Generate Multiple, Save Some
# Tests: multiple artifacts, partial save
# -----------------------------------------------------------------------------
register_scenario(Scenario(
    name="multi_artifact",
    description="Test generating multiple recipes and saving selectively",
    turns=[
        Turn(
            user_message="Generate 2 quick weeknight dinner ideas using chicken",
            description="Generate multiple recipes - should create gen_recipe_1, gen_recipe_2",
        ),
        Turn(
            user_message="I like the first one, save just that",
            description="Save only gen_recipe_1 - gen_recipe_2 should remain pending",
        ),
        Turn(
            user_message="What recipes do I have that aren't saved yet?",
            description="Should still see gen_recipe_2 as pending",
        ),
    ],
))


# =============================================================================
# Runner
# =============================================================================

async def run_scenario(
    scenario: Scenario,
    log_dir: Path,
    user_id: str,
    verbose: bool = True,
) -> bool:
    """
    Run a scenario and log results.

    Returns True if all turns completed successfully.
    """
    print(f"\n{'='*60}")
    print(f"Scenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(f"User ID: {user_id}")
    print(f"{'='*60}")

    conversation = initialize_conversation()

    # Create scenario log directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scenario_log_dir = log_dir / f"{scenario.name}_{timestamp}"
    scenario_log_dir.mkdir(parents=True, exist_ok=True)

    all_passed = True
    results = []

    for i, turn in enumerate(scenario.turns, 1):
        print(f"\n--- Turn {i}: {turn.description or turn.user_message[:50]} ---")
        print(f"User: {turn.user_message}")

        turn_result = {
            "turn": i,
            "description": turn.description,
            "user_message": turn.user_message,
            "response": None,
            "error": None,
            "state_snapshot": None,
        }

        try:
            response, conversation = await run_alfred(
                user_message=turn.user_message,
                user_id=user_id,
                conversation=conversation,
            )

            turn_result["response"] = response
            print(f"Alfred: {response[:200]}{'...' if len(response) > 200 else ''}")

            # Capture state snapshot
            state_snapshot = {
                "turn_count": len(conversation.get("recent_turns", [])),
                "id_registry": None,
                "pending_artifacts": None,
            }

            # Try to get registry state
            if "id_registry" in conversation:
                registry_data = conversation["id_registry"]
                state_snapshot["id_registry"] = {
                    "ref_to_uuid": registry_data.get("ref_to_uuid", {}),
                    "ref_actions": registry_data.get("ref_actions", {}),
                    "ref_labels": registry_data.get("ref_labels", {}),
                }
                state_snapshot["pending_artifacts"] = list(
                    registry_data.get("pending_artifacts", {}).keys()
                )

            turn_result["state_snapshot"] = state_snapshot

            if verbose:
                if state_snapshot["pending_artifacts"]:
                    print(f"[State] Pending artifacts: {state_snapshot['pending_artifacts']}")
                if state_snapshot["id_registry"]:
                    refs = list(state_snapshot["id_registry"]["ref_to_uuid"].keys())
                    print(f"[State] Known refs: {refs}")

            # Run verification if provided
            if turn.verify:
                passed = turn.verify(conversation, response)
                turn_result["verification_passed"] = passed
                if not passed:
                    print(f"[FAIL] Verification failed for turn {i}")
                    all_passed = False
                else:
                    print(f"[PASS] Verification passed")

        except Exception as e:
            turn_result["error"] = str(e)
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

        results.append(turn_result)

        # Write turn log
        turn_log_path = scenario_log_dir / f"turn_{i:02d}.json"
        with open(turn_log_path, "w", encoding="utf-8") as f:
            json.dump(turn_result, f, indent=2, default=str)

    # Write summary
    summary = {
        "scenario": scenario.name,
        "description": scenario.description,
        "timestamp": timestamp,
        "all_passed": all_passed,
        "turn_count": len(scenario.turns),
        "results": results,
    }

    summary_path = scenario_log_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"Scenario complete: {'PASSED' if all_passed else 'FAILED'}")
    print(f"Logs written to: {scenario_log_dir}")
    print(f"{'='*60}")

    return all_passed


async def main():
    """Main entry point."""
    args = sys.argv[1:]

    # Handle --list flag
    if "--list" in args:
        print("Available scenarios:")
        for name, scenario in SCENARIOS.items():
            print(f"  {name}: {scenario.description}")
        return

    # Parse --user flag
    user_id = os.environ.get("ALFRED_TEST_USER_ID", DEFAULT_TEST_USER)
    if "--user" in args:
        idx = args.index("--user")
        if idx + 1 < len(args):
            user_id = args[idx + 1]
            args = args[:idx] + args[idx + 2:]  # Remove --user and its value
        else:
            print("Error: --user requires a user ID")
            return

    # Determine which scenarios to run
    scenario_names = [a for a in args if not a.startswith("--")]
    if scenario_names:
        scenarios_to_run = [SCENARIOS[name] for name in scenario_names if name in SCENARIOS]
        unknown = [name for name in scenario_names if name not in SCENARIOS]
        if unknown:
            print(f"Unknown scenario(s): {unknown}")
            print("Use --list to see available scenarios")
            return
    else:
        scenarios_to_run = list(SCENARIOS.values())

    # Create log directory
    log_dir = Path(__file__).parent / "scenario_logs"
    log_dir.mkdir(exist_ok=True)

    print(f"Using user ID: {user_id}")

    # Run scenarios
    results = {}
    for scenario in scenarios_to_run:
        passed = await run_scenario(scenario, log_dir, user_id)
        results[scenario.name] = passed

    # Print final summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
