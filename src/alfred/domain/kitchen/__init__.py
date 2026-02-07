"""
Kitchen Domain Configuration.

This module provides the KITCHEN_DOMAIN singleton that implements
the DomainConfig protocol for Alfred's kitchen management assistant.

Usage:
    from alfred.domain.kitchen import KITCHEN_DOMAIN

    table = KITCHEN_DOMAIN.type_to_table["recipe"]  # "recipes"
"""

from typing import Any, Callable

from alfred.domain.base import DomainConfig, EntityDefinition, SubdomainDefinition


class KitchenConfig(DomainConfig):
    """
    Kitchen domain configuration.

    Provides all kitchen-specific entity definitions, subdomains,
    personas, and formatting rules.
    """

    # =========================================================================
    # Core Properties
    # =========================================================================

    @property
    def name(self) -> str:
        return "kitchen"

    @property
    def entities(self) -> dict[str, EntityDefinition]:
        return {
            "recipes": EntityDefinition(
                type_name="recipe",
                table="recipes",
                primary_field="name",
                fk_fields=[],
                complexity="high",
                label_fields=["name"],
                nested_relations=["recipe_ingredients"],
                detail_tracking=True,  # V7 summary vs full tracking
            ),
            "recipe_ingredients": EntityDefinition(
                type_name="ri",
                table="recipe_ingredients",
                primary_field="ingredient_id",  # FK-based
                fk_fields=["recipe_id", "ingredient_id"],
                label_fields=["ingredient_id"],
            ),
            "inventory": EntityDefinition(
                type_name="inv",
                table="inventory",
                primary_field="name",
                fk_fields=["ingredient_id"],
                label_fields=["name"],
            ),
            "shopping_list": EntityDefinition(
                type_name="shop",
                table="shopping_list",
                primary_field="name",
                fk_fields=["ingredient_id"],
                label_fields=["name"],
            ),
            "meal_plans": EntityDefinition(
                type_name="meal",
                table="meal_plans",
                primary_field="date",
                fk_fields=["recipe_id"],
                complexity="medium",
                label_fields=["date", "meal_type"],  # Special label format
            ),
            "tasks": EntityDefinition(
                type_name="task",
                table="tasks",
                primary_field="title",
                fk_fields=["recipe_id", "meal_plan_id"],
                label_fields=["title"],
            ),
            "preferences": EntityDefinition(
                type_name="pref",
                table="preferences",
                primary_field="name",
                label_fields=["name"],
            ),
            "ingredients": EntityDefinition(
                type_name="ing",
                table="ingredients",
                primary_field="name",
                label_fields=["name"],
            ),
            "cooking_log": EntityDefinition(
                type_name="log",
                table="cooking_log",
                primary_field="cooked_at",
                fk_fields=["recipe_id"],
                label_fields=["cooked_at"],
            ),
            "flavor_preferences": EntityDefinition(
                type_name="flavor",
                table="flavor_preferences",
                primary_field="name",
                label_fields=["name"],
            ),
        }

    @property
    def subdomains(self) -> dict[str, SubdomainDefinition]:
        return {
            "inventory": SubdomainDefinition(
                name="inventory",
                primary_table="inventory",
                related_tables=["ingredients"],
                description="User's pantry/fridge/freezer items.",
            ),
            "recipes": SubdomainDefinition(
                name="recipes",
                primary_table="recipes",
                related_tables=["recipe_ingredients", "ingredients"],
                description="Recipes and their ingredients. Recipes link to recipe_ingredients.",
            ),
            "shopping": SubdomainDefinition(
                name="shopping",
                primary_table="shopping_list",
                related_tables=["ingredients"],
                description="Shopping list. Often populated from recipes or meal plans.",
            ),
            "meal_plans": SubdomainDefinition(
                name="meal_plans",
                primary_table="meal_plans",
                related_tables=["recipes", "tasks"],
                description="Meal planning calendar. Links to recipes and spawns tasks.",
            ),
            "tasks": SubdomainDefinition(
                name="tasks",
                primary_table="tasks",
                related_tables=["meal_plans", "recipes"],
                description="Reminders and to-dos. Can be standalone or linked to meals/recipes.",
            ),
            "preferences": SubdomainDefinition(
                name="preferences",
                primary_table="preferences",
                related_tables=["flavor_preferences"],
                description="User preferences. Changes affect UX significantly.",
            ),
            "history": SubdomainDefinition(
                name="history",
                primary_table="cooking_log",
                related_tables=[],
                description="Cooking log. Simple event recording.",
            ),
        }

    # =========================================================================
    # Prompt/Persona Providers
    # =========================================================================

    def get_persona(self, subdomain: str, step_type: str) -> str:
        """Get persona for subdomain. Delegates to personas module."""
        from alfred.domain.kitchen.personas import get_persona_for_subdomain
        return get_persona_for_subdomain(subdomain, step_type)

    def get_examples(self, subdomain: str, step_type: str) -> str:
        """Get examples for subdomain. Delegates to examples module."""
        from alfred.domain.kitchen.examples import get_contextual_examples
        return get_contextual_examples(subdomain, step_type)

    def get_table_format(self, table: str) -> dict[str, Any]:
        """Get formatting rules for a table."""
        from alfred.domain.kitchen.formatters import TABLE_FORMAT_PROTOCOLS
        return TABLE_FORMAT_PROTOCOLS.get(table, {})

    def get_empty_response(self, subdomain: str) -> str:
        """Get empty response message for a subdomain."""
        from alfred.domain.kitchen.formatters import EMPTY_RESPONSES
        return EMPTY_RESPONSES.get(subdomain, "No items found.")

    # =========================================================================
    # Schema/FK Resolution
    # =========================================================================

    def get_fk_enrich_map(self) -> dict[str, tuple[str, str]]:
        """FK field → (target_table, name_column) for lazy enrichment."""
        return {
            "recipe_id": ("recipes", "name"),
            "ingredient_id": ("ingredients", "name"),
            "meal_plan_id": ("meal_plans", "date"),  # Use date for meal plans
            "task_id": ("tasks", "title"),
            "parent_recipe_id": ("recipes", "name"),
        }

    def get_field_enums(self) -> dict[str, dict[str, list[str]]]:
        """Get categorical field values per subdomain."""
        from alfred.domain.kitchen.schema import FIELD_ENUMS
        return FIELD_ENUMS

    def get_semantic_notes(self) -> dict[str, str]:
        """Get subdomain-specific clarifications."""
        from alfred.domain.kitchen.schema import SEMANTIC_NOTES
        return SEMANTIC_NOTES

    def get_fallback_schemas(self) -> dict[str, str]:
        """Get hardcoded schema fallbacks."""
        from alfred.domain.kitchen.schema import FALLBACK_SCHEMAS
        return FALLBACK_SCHEMAS

    def get_scope_config(self) -> dict[str, dict]:
        """Get cross-subdomain relationship configuration."""
        from alfred.domain.kitchen.schema import SUBDOMAIN_SCOPE
        return SUBDOMAIN_SCOPE

    # =========================================================================
    # CRUD Configuration
    # =========================================================================

    def get_crud_middleware(self):
        """Get kitchen CRUD middleware for semantic search, auto-includes, etc."""
        from alfred.domain.kitchen.crud_middleware import KitchenCRUDMiddleware
        return KitchenCRUDMiddleware()

    def get_user_owned_tables(self) -> set[str]:
        """Tables requiring user_id scoping."""
        from alfred.domain.kitchen.crud_middleware import USER_OWNED_TABLES
        return USER_OWNED_TABLES

    def get_uuid_fields(self) -> set[str]:
        """FK field names containing UUIDs."""
        from alfred.domain.kitchen.crud_middleware import UUID_FIELDS
        return UUID_FIELDS

    def get_subdomain_registry(self) -> dict[str, dict]:
        """Subdomain-to-tables mapping for schema introspection."""
        from alfred.domain.kitchen.schema import SUBDOMAIN_REGISTRY
        return SUBDOMAIN_REGISTRY

    def get_subdomain_examples(self) -> dict[str, list[str]]:
        """Example queries per subdomain."""
        from alfred.domain.kitchen.schema import SUBDOMAIN_EXAMPLES
        return SUBDOMAIN_EXAMPLES

    # =========================================================================
    # Entity Processing
    # =========================================================================

    def infer_entity_type_from_artifact(self, artifact: dict) -> str:
        """Infer entity type from artifact structure."""
        # Check for recipe-specific fields
        if any(k in artifact for k in ("instructions", "recipe_ingredients", "prep_time")):
            return "recipe"
        # Check for inventory-specific fields
        if any(k in artifact for k in ("quantity", "unit", "location", "expiry_date")):
            return "inv"
        # Check for meal plan fields
        if any(k in artifact for k in ("date", "meal_type", "recipe_id")):
            return "meal"
        # Check for task fields
        if any(k in artifact for k in ("due_date", "completed", "priority")):
            return "task"
        # Check for shopping list
        if "in_cart" in artifact:
            return "shop"
        # Default fallback
        return "recipe"  # Most common for generated content

    def compute_entity_label(
        self, record: dict, entity_type: str, ref: str
    ) -> str:
        """Compute human-readable label for an entity."""
        # Standard name/title fields
        if record.get("name"):
            return record["name"]
        if record.get("title"):
            return record["title"]

        # Special handling for meal_plans: "Jan 12 [lunch]"
        if entity_type == "meal" and record.get("date"):
            date = record["date"]
            meal_type = record.get("meal_type", "meal")
            try:
                from datetime import datetime
                if isinstance(date, str):
                    dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                    date = dt.strftime("%b %d")  # "Jan 12"
            except Exception:
                pass
            return f"{date} [{meal_type}]"

        # Fallback to ref
        return ref

    def get_entity_data_legend(self, entity_type: str) -> str | None:
        """Get explanatory legend for entity-specific data tracking."""
        if entity_type == "recipe":
            return (
                "**For recipes:** "
                "`[read:full]` = has instructions + ingredients, "
                "`[read:summary]` = metadata only (re-read with instructions for details)"
            )
        return None

    def detect_detail_level(self, entity_type: str, record: dict) -> str | None:
        """Detect whether a recipe read returned full or summary data."""
        if entity_type == "recipe":
            return "full" if "instructions" in record else "summary"
        return None

    def compute_artifact_label(
        self, artifact: dict, entity_type: str, index: int
    ) -> str:
        """Extract label from a generated artifact."""
        if artifact.get("name"):
            return artifact["name"]
        if artifact.get("title"):
            return artifact["title"]
        # Meal plan: try date range
        if entity_type == "meal_plan":
            meal_plan = artifact.get("meal_plan", [])
            if meal_plan and isinstance(meal_plan, list):
                dates = [e.get("date") for e in meal_plan if e.get("date")]
                if dates:
                    return f"Meal Plan {dates[0]} to {dates[-1]}"
            return "Generated Meal Plan"
        return f"item_{index + 1}"

    def get_tracked_entity_types(self) -> set[str]:
        """Entity types tracked across orchestration steps."""
        return {"recipes", "meal_plans", "tasks", "recipe", "meal_plan", "task"}

    def get_subdomain_aliases(self) -> dict[str, str]:
        """Natural language aliases for subdomain normalization."""
        return {
            # Singular → plural
            "recipe": "recipes",
            "meal_plan": "meal_plans",
            "preference": "preferences",
            # Natural language
            "pantry": "inventory",
            "fridge": "inventory",
            "ingredients": "inventory",
            "shopping_list": "shopping",
            "groceries": "shopping",
            "meals": "meal_plans",
            "meal planning": "meal_plans",
            "diet": "preferences",
            "dietary": "preferences",
            "restrictions": "preferences",
        }

    def get_archive_key_for_description(self, description: str) -> str | None:
        """Infer archive key from step description."""
        desc_lower = description.lower()
        if "recipe" in desc_lower:
            return "generated_recipes"
        if "meal" in desc_lower and "plan" in desc_lower:
            return "generated_meal_plan"
        if "analyz" in desc_lower or "compar" in desc_lower:
            return "analysis_result"
        return None

    def get_archive_keys_for_subdomain(self, subdomain: str) -> list[str]:
        """Archive keys to clear when saving to a subdomain."""
        mapping = {
            "recipes": ["generated_recipes"],
            "meal_plans": ["generated_meal_plan"],
        }
        return mapping.get(subdomain, [])

    def get_entity_key_fields(self) -> list[str]:
        """Key fields for generic entity context cards."""
        return [
            "quantity", "unit", "location", "category",
            "date", "meal_type", "status",
        ]

    def get_bold_skip_words(self) -> list[str]:
        """Kitchen section headings to skip when extracting entity names."""
        return [
            "ingredient", "instruction", "serve", "step",
            "note", "tip", "prep", "cook time",
        ]

    # =========================================================================
    # Reply Formatting
    # =========================================================================

    def get_subdomain_formatters(self) -> dict[str, Callable]:
        """Get domain-specific reply formatters."""
        from alfred.domain.kitchen.formatters import (
            format_inventory_summary,
            format_shopping_summary,
            format_recipe_summary,
            format_meal_plan_summary,
            format_task_summary,
        )
        return {
            "inventory": format_inventory_summary,
            "shopping": format_shopping_summary,
            "recipes": format_recipe_summary,
            "meal_plans": format_meal_plan_summary,
            "tasks": format_task_summary,
        }

    def get_strip_fields(self, context: str = "injection") -> set[str]:
        """Get fields to strip from records."""
        from alfred.domain.kitchen.formatters import (
            INJECTION_STRIP_FIELDS,
            REPLY_STRIP_FIELDS,
        )
        if context == "reply":
            return REPLY_STRIP_FIELDS
        return INJECTION_STRIP_FIELDS

    def format_entity_for_context(
        self, entity_type: str, ref: str, label: str, data: dict, **kwargs
    ) -> list[str]:
        """Format entity data for Act context."""
        if entity_type == "recipe":
            from alfred.domain.kitchen.formatters import format_recipe_data
            return format_recipe_data(ref, label, data, registry=kwargs.get("registry"))
        # Default: simple key-value
        return super().format_entity_for_context(entity_type, ref, label, data, **kwargs)

    def infer_table_from_record(self, record: dict) -> str | None:
        """Infer table name from record fields."""
        if not isinstance(record, dict):
            return None
        if "dietary_restrictions" in record or "allergies" in record or "cooking_skill_level" in record:
            return "preferences"
        if "recipe_id" in record and "name" in record and "quantity" in record:
            return "recipe_ingredients"
        if "meal_type" in record and "date" in record:
            return "meal_plans"
        if "cuisine" in record or "prep_time" in record or "cook_time" in record or "total_time" in record:
            return "recipes"
        if "location" in record or "expiry_date" in record:
            return "inventory"
        if "is_purchased" in record:
            return "shopping_list"
        if "due_date" in record or "status" in record:
            return "tasks"
        return None

    def get_system_prompt(self) -> str:
        """Get kitchen system prompt."""
        from pathlib import Path
        prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "system.md"
        return prompt_path.read_text(encoding="utf-8")

    # =========================================================================
    # Mode/Agent Registration
    # =========================================================================

    @property
    def bypass_modes(self) -> dict[str, type]:
        """Get graph-bypass mode handlers."""
        from alfred.modes.cook import run_cook_session
        from alfred.modes.brainstorm import run_brainstorm_session
        # Note: These are functions, not classes. The type annotation
        # is flexible - in practice these are async generator functions.
        return {
            "cook": run_cook_session,
            "brainstorm": run_brainstorm_session,
        }

    @property
    def default_agent(self) -> str:
        """Default agent for single-agent mode."""
        return "main"

    # Phase 2.5: Agent protocol support
    # Kitchen uses single-agent mode with bypass_modes for cook/brainstorm.
    # These properties use DomainConfig defaults (empty list, None router).
    # Future: Could wrap cook/brainstorm as AgentProtocol implementations.

    @property
    def agents(self) -> list:
        """Kitchen agents - currently empty (single-agent mode)."""
        return []  # bypass_modes handles cook/brainstorm

    @property
    def agent_router(self):
        """Kitchen router - None for single-agent mode."""
        return None

    def get_handoff_result_model(self) -> type:
        """Get the HandoffResult Pydantic model."""
        from alfred.modes.handoff import HandoffResult
        return HandoffResult


# Singleton instance
KITCHEN_DOMAIN = KitchenConfig()
