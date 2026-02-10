"""
Kitchen-specific Router prompt content.

Extracted from the original router.md agent definitions.
Injected into the Router prompt via DomainConfig.get_router_prompt_injection().
"""

ROUTER_CONTENT = """\
## Agents Available

| Agent | Handles | Examples |
|-------|---------|----------|
| `pantry` | Inventory, recipes, meal planning, shopping lists | "Add milk", "What can I cook?", "Plan dinner for the week" |
| `coach` | Fitness, nutrition goals, workout planning | "Track my calories", "Suggest a protein-rich meal" |
| `cellar` | Wine collection, pairings, recommendations | "What wine goes with salmon?", "Add a bottle of Malbec" |

**Default to `pantry`** for general food/cooking questions."""
