"""
Kitchen Payload Compilers.

Domain-specific compilers that transform rich generated artifacts
into schema-ready payloads for database writes.
"""

from typing import Any

from alfred.core.payload_compiler import (
    CompilationResult,
    CompiledPayload,
    CompiledRecord,
    LinkedRecord,
    SubdomainCompiler,
)


class RecipeCompiler(SubdomainCompiler):
    """Compiler for recipe subdomain."""

    @property
    def subdomain(self) -> str:
        return "recipes"

    def compile(self, artifacts: list[dict], context: dict[str, Any]) -> CompilationResult:
        """
        Compile recipe artifacts into schema-ready payloads.

        Input artifact structure (rich):
        {
            "name": "Garlic Butter Salmon",
            "description": "A delicious pan-seared salmon...",
            "cuisine": "American",
            "prep_time": 10,
            "cook_time": 15,
            "servings": 4,
            "difficulty": "easy",
            "instructions": ["Step 1...", "Step 2..."],
            "ingredients": [
                {"name": "salmon fillet", "quantity": 4, "unit": "oz"},
                {"name": "garlic", "quantity": 3, "unit": "cloves"},
            ],
            "tags": ["quick", "healthy"],
            "notes": "Best served immediately..."
        }

        Output (schema-ready):
        - Main record for `recipes` table
        - Linked records for `recipe_ingredients` table
        """
        payloads = []
        warnings = []
        user_id = context.get("user_id")

        for i, artifact in enumerate(artifacts):
            ref = artifact.get("ref", f"gen_recipe_{i + 1}")

            # Compile main recipe record
            recipe_data = {
                "name": artifact.get("name", "Untitled Recipe"),
                "description": artifact.get("description"),
                "cuisine": artifact.get("cuisine"),
                "prep_time_minutes": artifact.get("prep_time"),
                "cook_time_minutes": artifact.get("cook_time"),
                "servings": artifact.get("servings"),
                "difficulty": artifact.get("difficulty"),
                "instructions": artifact.get("instructions", []),
            }

            if user_id:
                recipe_data["user_id"] = user_id

            # Handle fields that might be lost
            if artifact.get("notes"):
                warnings.append(f"{ref}: 'notes' field simplified to description")
                if recipe_data.get("description"):
                    recipe_data["description"] += f"\n\nNotes: {artifact['notes']}"
                else:
                    recipe_data["description"] = artifact["notes"]

            if artifact.get("tags"):
                warnings.append(f"{ref}: 'tags' preserved as-is (ensure tags table exists)")

            # Compile linked ingredient records
            linked = []
            ingredients = artifact.get("ingredients", [])
            if ingredients:
                ingredient_records = []
                for ing in ingredients:
                    ing_record = {
                        "ingredient_name": ing.get("name", ing.get("ingredient_name", "")),
                        "quantity": ing.get("quantity"),
                        "unit": ing.get("unit"),
                    }
                    ingredient_records.append(ing_record)

                if ingredient_records:
                    linked.append(LinkedRecord(
                        table="recipe_ingredients",
                        records=ingredient_records
                    ))

            record = CompiledRecord(
                ref=ref,
                data=recipe_data,
                linked_records=linked
            )

            payloads.append(CompiledPayload(
                target_table="recipes",
                records=[record],
                warnings=warnings.copy()
            ))
            warnings.clear()

        return CompilationResult(payloads=payloads, warnings=warnings)


class MealPlanCompiler(SubdomainCompiler):
    """Compiler for meal planning subdomain."""

    @property
    def subdomain(self) -> str:
        return "meal_plans"

    def compile(self, artifacts: list[dict], context: dict[str, Any]) -> CompilationResult:
        """Compile meal plan artifacts into schema-ready payloads."""
        payloads = []
        warnings = []
        user_id = context.get("user_id")

        for i, artifact in enumerate(artifacts):
            ref = artifact.get("ref", f"gen_meal_{i + 1}")

            meal_data = {
                "date": artifact.get("date"),
                "meal_type": artifact.get("meal_type", "dinner"),
                "recipe_id": artifact.get("recipe_id"),
                "notes": artifact.get("notes"),
            }

            if user_id:
                meal_data["user_id"] = user_id

            record = CompiledRecord(ref=ref, data=meal_data)
            payloads.append(CompiledPayload(
                target_table="meal_plans",
                records=[record]
            ))

        return CompilationResult(payloads=payloads, warnings=warnings)


class TaskCompiler(SubdomainCompiler):
    """Compiler for tasks subdomain."""

    @property
    def subdomain(self) -> str:
        return "tasks"

    def compile(self, artifacts: list[dict], context: dict[str, Any]) -> CompilationResult:
        """Compile task artifacts into schema-ready payloads."""
        payloads = []
        warnings = []
        user_id = context.get("user_id")

        for i, artifact in enumerate(artifacts):
            ref = artifact.get("ref", f"gen_task_{i + 1}")

            task_data = {
                "title": artifact.get("title", "Untitled Task"),
                "description": artifact.get("description"),
                "due_date": artifact.get("due_date"),
                "status": artifact.get("status", "pending"),
                "priority": artifact.get("priority"),
            }

            if user_id:
                task_data["user_id"] = user_id

            record = CompiledRecord(ref=ref, data=task_data)
            payloads.append(CompiledPayload(
                target_table="tasks",
                records=[record]
            ))

        return CompilationResult(payloads=payloads, warnings=warnings)


class InventoryCompiler(SubdomainCompiler):
    """Compiler for inventory subdomain."""

    @property
    def subdomain(self) -> str:
        return "inventory"

    def compile(self, artifacts: list[dict], context: dict[str, Any]) -> CompilationResult:
        """Compile inventory artifacts into schema-ready payloads."""
        payloads = []
        warnings = []
        user_id = context.get("user_id")

        for i, artifact in enumerate(artifacts):
            ref = artifact.get("ref", f"gen_inventory_{i + 1}")

            inv_data = {
                "ingredient_id": artifact.get("ingredient_id"),
                "ingredient_name": artifact.get("ingredient_name", artifact.get("name")),
                "quantity": artifact.get("quantity"),
                "unit": artifact.get("unit"),
                "expiration_date": artifact.get("expiration_date"),
                "location": artifact.get("location"),
            }

            if user_id:
                inv_data["user_id"] = user_id

            record = CompiledRecord(ref=ref, data=inv_data)
            payloads.append(CompiledPayload(
                target_table="inventory",
                records=[record]
            ))

        return CompilationResult(payloads=payloads, warnings=warnings)


class ShoppingCompiler(SubdomainCompiler):
    """Compiler for shopping list subdomain."""

    @property
    def subdomain(self) -> str:
        return "shopping"

    def compile(self, artifacts: list[dict], context: dict[str, Any]) -> CompilationResult:
        """Compile shopping list artifacts into schema-ready payloads."""
        payloads = []
        warnings = []
        user_id = context.get("user_id")

        for i, artifact in enumerate(artifacts):
            ref = artifact.get("ref", f"gen_shopping_{i + 1}")

            shopping_data = {
                "ingredient_id": artifact.get("ingredient_id"),
                "ingredient_name": artifact.get("ingredient_name", artifact.get("name")),
                "quantity": artifact.get("quantity"),
                "unit": artifact.get("unit"),
                "category": artifact.get("category"),
                "checked": artifact.get("checked", False),
            }

            if user_id:
                shopping_data["user_id"] = user_id

            record = CompiledRecord(ref=ref, data=shopping_data)
            payloads.append(CompiledPayload(
                target_table="shopping_list",
                records=[record]
            ))

        return CompilationResult(payloads=payloads, warnings=warnings)


# All kitchen compilers for registration
KITCHEN_COMPILERS = [
    RecipeCompiler(),
    MealPlanCompiler(),
    TaskCompiler(),
    InventoryCompiler(),
    ShoppingCompiler(),
]
