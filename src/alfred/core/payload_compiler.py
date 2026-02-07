"""
V4: Payload Compilation

Pre-normalizes generated content into schema-ready payloads for Write steps.
Each subdomain has its own compiler that maps rich artifacts to database records.
Domain-specific compilers are registered via DomainConfig.get_payload_compilers().

This runs BETWEEN Generate and Write steps, ensuring:
1. Generated artifacts are preserved in full
2. Schema-validated payloads are ready for db_create
3. Discrepancies between rich content and schema are surfaced
"""

from dataclasses import dataclass, field
from typing import Any
from abc import ABC, abstractmethod


@dataclass
class LinkedRecord:
    """A record to be created in a related table."""
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


# =============================================================================
# Compiler Registry
# =============================================================================


class PayloadCompilerRegistry:
    """Registry for subdomain compilers. Populated from DomainConfig."""

    def __init__(self):
        self._compilers: dict[str, SubdomainCompiler] = {}

    def register(self, compiler: SubdomainCompiler) -> None:
        """Register a subdomain compiler."""
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


def _get_registry() -> PayloadCompilerRegistry:
    """Get a compiler registry populated from the current domain config."""
    from alfred.domain import get_current_domain
    domain = get_current_domain()
    registry = PayloadCompilerRegistry()
    for compiler in domain.get_payload_compilers():
        registry.register(compiler)
    return registry


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
    registry = _get_registry()
    return registry.compile(subdomain, artifacts, context or {})


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
