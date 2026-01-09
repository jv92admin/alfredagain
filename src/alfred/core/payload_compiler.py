"""
V4: Payload Compilation

Pre-normalizes generated content into schema-ready payloads for Write steps.
Each subdomain has its own compiler that maps rich artifacts to database records.

This runs BETWEEN Generate and Write steps, ensuring:
1. Generated artifacts are preserved in full
2. Schema-validated payloads are ready for db_create
3. Discrepancies between rich content and schema are surfaced
"""

from dataclasses import dataclass, field
from typing import Any, Protocol
from abc import ABC, abstractmethod


@dataclass
class LinkedRecord:
    """A record to be created in a related table (e.g., recipe_ingredients)."""
    table: str
    records: list[dict[str, Any]]


@dataclass
class CompiledRecord:
    """A single schema-ready record ready for db_create."""
    ref: str  # Maps to batch item (e.g., gen_recipe_1)
    data: dict[str, Any]  # Schema-validated fields
    linked_records: list[LinkedRecord] = field(default_factory=list)


@dataclass
class CompiledPayload:
    """Complete compiled payload for a Write step."""
    target_table: str
    records: list[CompiledRecord]
    warnings: list[str] = field(default_factory=list)  # What was lost in compilation


@dataclass
class CompilationResult:
    """Result of payload compilation."""
    payloads: list[CompiledPayload]
    warnings: list[str]
    success: bool = True


class SubdomainCompiler(ABC):
    """Base class for subdomain-specific payload compilers."""
    
    @property
    @abstractmethod
    def subdomain(self) -> str:
        """Return the subdomain this compiler handles."""
        pass
    
    @abstractmethod
    def compile(self, artifacts: list[dict], context: dict[str, Any]) -> CompilationResult:
        """Compile artifacts into schema-ready payloads."""
        pass


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
                # Notes field might not exist in schema - add to warnings
                warnings.append(f"{ref}: 'notes' field simplified to description")
                if recipe_data.get("description"):
                    recipe_data["description"] += f"\n\nNotes: {artifact['notes']}"
                else:
                    recipe_data["description"] = artifact["notes"]
            
            if artifact.get("tags"):
                # Tags might need special handling
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
                    # recipe_id will be substituted by ID mapper after recipe is created
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
                "recipe_id": artifact.get("recipe_id"),  # May need FK substitution
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


# =============================================================================
# Compiler Registry
# =============================================================================


class PayloadCompilerRegistry:
    """Registry for subdomain compilers."""
    
    def __init__(self):
        self._compilers: dict[str, SubdomainCompiler] = {}
        self._register_default_compilers()
    
    def _register_default_compilers(self):
        """Register all default subdomain compilers."""
        for compiler_cls in [
            RecipeCompiler,
            MealPlanCompiler,
            TaskCompiler,
            InventoryCompiler,
            ShoppingCompiler,
        ]:
            compiler = compiler_cls()
            self._compilers[compiler.subdomain] = compiler
    
    def get_compiler(self, subdomain: str) -> SubdomainCompiler | None:
        """Get compiler for a subdomain."""
        return self._compilers.get(subdomain)
    
    def compile(
        self,
        subdomain: str,
        artifacts: list[dict],
        context: dict[str, Any]
    ) -> CompilationResult:
        """
        Compile artifacts for a given subdomain.
        
        Args:
            subdomain: Target subdomain (e.g., "recipes", "meal_plans")
            artifacts: List of rich artifacts from Generate step
            context: Execution context (user_id, etc.)
        
        Returns:
            CompilationResult with payloads and any warnings
        """
        compiler = self.get_compiler(subdomain)
        if not compiler:
            return CompilationResult(
                payloads=[],
                warnings=[f"No compiler for subdomain: {subdomain}"],
                success=False
            )
        
        return compiler.compile(artifacts, context)


# Global registry instance
_registry = PayloadCompilerRegistry()


def compile_payloads(
    subdomain: str,
    artifacts: list[dict],
    context: dict[str, Any] | None = None
) -> CompilationResult:
    """
    Compile artifacts into schema-ready payloads.
    
    This is the main entry point for payload compilation.
    Called between Generate and Write steps.
    
    Args:
        subdomain: Target subdomain
        artifacts: Rich artifacts from Generate step
        context: Optional execution context
    
    Returns:
        CompilationResult with compiled payloads and warnings
    """
    return _registry.compile(subdomain, artifacts, context or {})


def get_compiled_payload_for_step(
    step_metadata: dict[int, dict],
    target_step_idx: int,
    subdomain: str,
    context: dict[str, Any] | None = None
) -> CompilationResult | None:
    """
    Get compiled payload for a write step based on prior generate step.
    
    Searches backwards from target_step_idx to find the most recent
    generate step with artifacts, then compiles them.
    
    Args:
        step_metadata: Step metadata dictionary
        target_step_idx: Index of the write step
        subdomain: Target subdomain
        context: Execution context
    
    Returns:
        CompilationResult if artifacts found, None otherwise
    """
    # Search backwards for most recent generate step with artifacts
    for idx in range(target_step_idx - 1, -1, -1):
        meta = step_metadata.get(idx)
        if meta and meta.get("step_type") == "generate":
            artifacts = meta.get("artifacts", [])
            if artifacts:
                return compile_payloads(subdomain, artifacts, context)
    
    return None
