"""
Domain Configuration Protocol.

This module defines the abstract interface that all domain implementations
must satisfy. The DomainConfig protocol enables Alfred's orchestration
engine to work with any domain (kitchen, FPL, etc.) without hardcoding
domain-specific logic.

Key concepts:
- EntityDefinition: Configuration for a single entity type (recipe, player, etc.)
- SubdomainDefinition: Logical grouping of related tables
- DomainConfig: The main protocol with all domain-specific methods
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from alfred.db.adapter import DatabaseAdapter


@dataclass
class EntityDefinition:
    """
    Configuration for a single entity type.

    Each entity type in a domain (e.g., recipe, inventory item, player)
    is described by an EntityDefinition.

    Attributes:
        type_name: Short identifier used in refs (e.g., "recipe", "inv", "player")
        table: Database table name (e.g., "recipes", "inventory", "players")
        primary_field: Field used for display labels (e.g., "name", "title")
        fk_fields: Foreign key columns that reference other entities
        complexity: Think node complexity hint ("high", "medium", None)
        label_fields: Fields used to compute entity labels (e.g., ["name"] or ["date", "meal_type"])
        nested_relations: Related tables to include in reads (e.g., ["recipe_ingredients"])
        detail_tracking: Whether to track summary vs full reads (V7 pattern)
    """

    type_name: str
    table: str
    primary_field: str = "name"
    fk_fields: list[str] = field(default_factory=list)
    complexity: str | None = None
    label_fields: list[str] = field(default_factory=lambda: ["name"])
    nested_relations: list[str] | None = None
    detail_tracking: bool = False


@dataclass
class SubdomainDefinition:
    """
    Logical grouping of related tables.

    Subdomains help the Think node understand how to route requests
    and which tables to consider together.

    Attributes:
        name: Subdomain identifier (e.g., "recipes", "inventory", "transfers")
        primary_table: The main table for this subdomain
        related_tables: Other tables that belong to this subdomain
        description: Human-readable description for Think prompt guidance
    """

    name: str
    primary_table: str
    related_tables: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ReadPreprocessResult:
    """
    Result of CRUDMiddleware.pre_read() processing.

    Encapsulates all modifications the middleware wants applied to a read query.

    Attributes:
        params: Modified DbReadParams (filters may have been rewritten)
        select_additions: Extra clauses to append to SELECT (e.g., nested relations)
        pre_filter_ids: IDs to filter results by (e.g., from semantic search)
        or_conditions: Additional Supabase-format OR condition strings
        short_circuit_empty: If True, return [] without querying the database
    """

    params: Any  # DbReadParams — Any to avoid circular import
    select_additions: list[str] = field(default_factory=list)
    pre_filter_ids: list[str] | None = None
    or_conditions: list[str] | None = None
    short_circuit_empty: bool = False


class CRUDMiddleware:
    """
    Base class for domain-specific CRUD middleware.

    The middleware pattern separates domain intelligence (semantic search,
    ingredient lookup, auto-includes) from the generic CRUD executor.
    Core CRUD handles query building, filter application, and ref translation.
    The middleware transforms params before execution and records before writes.

    Override methods in domain-specific subclasses. Default implementations
    are pass-throughs (no modification).
    """

    async def pre_read(self, params: Any, user_id: str) -> ReadPreprocessResult:
        """
        Pre-process a read operation.

        Can modify params (rewrite filters, remove processed filters),
        add select clause additions, provide pre-filter IDs, or
        short-circuit with empty results.

        Args:
            params: DbReadParams instance
            user_id: Current user's ID

        Returns:
            ReadPreprocessResult with modifications to apply
        """
        return ReadPreprocessResult(params=params)

    async def pre_write(self, table: str, records: list[dict]) -> list[dict]:
        """
        Pre-process records before a write (create) operation.

        Can enrich records (e.g., add ingredient IDs) or validate them.

        Args:
            table: Target table name
            records: Records to be inserted

        Returns:
            Modified records list
        """
        return records

    def deduplicate_batch(self, table: str, records: list[dict]) -> list[dict]:
        """
        Remove duplicate records from a batch insert.

        Args:
            table: Target table name
            records: Records to deduplicate

        Returns:
            Deduplicated records list
        """
        return records


class DomainConfig(ABC):
    """
    Protocol that domain implementations must satisfy.

    A DomainConfig provides all the domain-specific information that
    Alfred's orchestration engine needs:
    - Entity definitions (what types of things exist)
    - Subdomain organization (how tables are grouped)
    - Personas and examples (for LLM prompts)
    - Formatting rules (for output)
    - Schema information (for CRUD operations)

    Example implementation:
        class KitchenConfig(DomainConfig):
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
                        nested_relations=["recipe_ingredients"],
                    ),
                    ...
                }
    """

    # =========================================================================
    # Core Properties
    # =========================================================================

    @property
    @abstractmethod
    def name(self) -> str:
        """Domain name (e.g., 'kitchen', 'fpl')."""
        ...

    @property
    @abstractmethod
    def entities(self) -> dict[str, EntityDefinition]:
        """
        Entity definitions keyed by table name.

        Returns:
            Dict mapping table name to EntityDefinition
        """
        ...

    @property
    @abstractmethod
    def subdomains(self) -> dict[str, SubdomainDefinition]:
        """
        Subdomain definitions keyed by subdomain name.

        Returns:
            Dict mapping subdomain name to SubdomainDefinition
        """
        ...

    # =========================================================================
    # Computed Lookups (auto-derived from entities)
    # =========================================================================

    @property
    def table_to_type(self) -> dict[str, str]:
        """
        Map table names to entity type names.

        Returns:
            Dict like {"recipes": "recipe", "inventory": "inv"}
        """
        return {e.table: e.type_name for e in self.entities.values()}

    @property
    def type_to_table(self) -> dict[str, str]:
        """
        Map entity type names to table names.

        Returns:
            Dict like {"recipe": "recipes", "inv": "inventory"}
        """
        return {e.type_name: e.table for e in self.entities.values()}

    # =========================================================================
    # Prompt/Persona Providers
    # =========================================================================

    @abstractmethod
    def get_persona(self, subdomain: str, step_type: str) -> str:
        """
        Get the persona/system prompt for a subdomain and step type.

        Args:
            subdomain: The subdomain (e.g., "recipes", "inventory")
            step_type: The step type (e.g., "read", "write", "analyze")

        Returns:
            Persona text for the LLM
        """
        ...

    @abstractmethod
    def get_examples(
        self,
        subdomain: str,
        step_type: str,
        step_description: str = "",
        prev_subdomain: str | None = None,
    ) -> str:
        """
        Get example interactions for a subdomain and step type.

        Args:
            subdomain: The subdomain (e.g., "recipes", "inventory")
            step_type: The step type (e.g., "read", "write", "analyze")
            step_description: Description of the current step (for contextual matching)
            prev_subdomain: Previous step's subdomain (for cross-domain patterns)

        Returns:
            Example text for the LLM
        """
        ...

    def get_act_subdomain_header(self, subdomain: str, step_type: str) -> str:
        """
        Get the subdomain header for Act prompt context.

        Combines subdomain intro, persona, and scope into a single header block
        used at the top of Act prompts.

        Args:
            subdomain: The subdomain
            step_type: The step type

        Returns:
            Combined header markdown, or empty string
        """
        return ""

    @abstractmethod
    def get_table_format(self, table: str) -> dict[str, Any]:
        """
        Get formatting rules for a table.

        Used by the injection system to format table data for prompts.

        Args:
            table: The table name

        Returns:
            Dict with formatting configuration
        """
        ...

    @abstractmethod
    def get_empty_response(self, subdomain: str) -> str:
        """
        Get the empty response message for a subdomain.

        Used when a read returns no results.

        Args:
            subdomain: The subdomain

        Returns:
            Human-friendly "no results" message
        """
        ...

    # =========================================================================
    # Schema/FK Resolution
    # =========================================================================

    @abstractmethod
    def get_fk_enrich_map(self) -> dict[str, tuple[str, str]]:
        """
        Get FK field enrichment mapping.

        Used by SessionIdRegistry for lazy FK enrichment.

        Returns:
            Dict mapping FK field name to (target_table, name_column)
            e.g., {"ingredient_id": ("ingredients", "name")}
        """
        ...

    @abstractmethod
    def get_field_enums(self) -> dict[str, dict[str, list[str]]]:
        """
        Get categorical field values per subdomain.

        Used in Act prompts to show valid enum values.

        Returns:
            Dict like {"inventory": {"unit": ["kg", "g", "ml", ...]}}
        """
        ...

    @abstractmethod
    def get_semantic_notes(self) -> dict[str, str]:
        """
        Get subdomain-specific clarifications for the LLM.

        Returns:
            Dict mapping subdomain to semantic notes
        """
        ...

    @abstractmethod
    def get_fallback_schemas(self) -> dict[str, str]:
        """
        Get hardcoded schema fallbacks per subdomain.

        Used when database introspection fails.

        Returns:
            Dict mapping subdomain to schema text
        """
        ...

    @abstractmethod
    def get_scope_config(self) -> dict[str, dict]:
        """
        Get cross-subdomain relationship configuration.

        Defines which subdomains can access data from other subdomains.

        Returns:
            Dict with scope configuration
        """
        ...

    # =========================================================================
    # CRUD Configuration
    # =========================================================================

    def get_crud_middleware(self) -> CRUDMiddleware | None:
        """
        Get domain-specific CRUD middleware.

        The middleware provides pre_read/pre_write hooks for domain-specific
        query intelligence (semantic search, auto-includes, ingredient lookup, etc.).

        Returns:
            CRUDMiddleware instance, or None for raw CRUD without middleware
        """
        return None  # Default: no middleware

    @abstractmethod
    def get_user_owned_tables(self) -> set[str]:
        """
        Get tables that require user_id scoping.

        These tables have a user_id column and CRUD operations automatically
        filter/inject user_id for security.

        Returns:
            Set of table names (e.g., {"inventory", "recipes", "meal_plans"})
        """
        ...

    @abstractmethod
    def get_uuid_fields(self) -> set[str]:
        """
        Get FK field names that contain UUIDs.

        Used for sanitization (empty string → None) before database operations.
        LLMs sometimes output "" instead of null for optional FK fields.

        Returns:
            Set of field names (e.g., {"recipe_id", "ingredient_id", "meal_plan_id"})
        """
        ...

    @abstractmethod
    def get_subdomain_registry(self) -> dict[str, dict]:
        """
        Get subdomain-to-tables mapping for schema introspection.

        Returns:
            Dict mapping subdomain name to config dict with "tables" key
            e.g., {"recipes": {"tables": ["recipes", "recipe_ingredients"]}}
        """
        ...

    @abstractmethod
    def get_subdomain_examples(self) -> dict[str, list[str]]:
        """
        Get example queries per subdomain for Think node guidance.

        Returns:
            Dict mapping subdomain to list of example queries
        """
        ...

    # =========================================================================
    # Entity Processing
    # =========================================================================

    @abstractmethod
    def infer_entity_type_from_artifact(self, artifact: dict) -> str:
        """
        Infer entity type from an artifact's structure.

        Used when the entity type isn't explicitly provided.

        Args:
            artifact: The artifact dict to analyze

        Returns:
            Entity type name (e.g., "recipe", "inv")
        """
        ...

    @abstractmethod
    def compute_entity_label(
        self, record: dict, entity_type: str, ref: str
    ) -> str:
        """
        Compute a human-readable label for an entity.

        Args:
            record: The entity record from database
            entity_type: The entity type (e.g., "recipe", "meal")
            ref: The entity reference (e.g., "recipe_1")

        Returns:
            Human-readable label (e.g., "Chicken Tikka Masala")
        """
        ...

    def get_entity_data_legend(self, entity_type: str) -> str | None:
        """
        Get explanatory legend for entity-specific data tracking.

        Used for entities with detail_tracking=True (e.g., recipes with
        summary vs full read levels).

        Args:
            entity_type: The entity type name (e.g., "recipe")

        Returns:
            Legend text explaining data tracking markers, or None
        """
        return None  # Default: no special legend

    def detect_detail_level(self, entity_type: str, record: dict) -> str | None:
        """
        Detect the detail level of a read record.

        For entities with detail_tracking=True, determines whether
        the returned record is "summary" or "full" based on which
        fields are present.

        Args:
            entity_type: The entity type name
            record: The database record

        Returns:
            "summary", "full", or None if not applicable
        """
        return None  # Default: no detail tracking

    def compute_artifact_label(
        self, artifact: dict, entity_type: str, index: int
    ) -> str:
        """
        Extract a human-readable label from a generated artifact.

        Args:
            artifact: The generated artifact dict
            entity_type: Inferred entity type
            index: Index in the artifacts list

        Returns:
            Human-readable label
        """
        # Default: use name/title or fallback
        if artifact.get("name"):
            return artifact["name"]
        if artifact.get("title"):
            return artifact["title"]
        return f"item_{index + 1}"

    def get_tracked_entity_types(self) -> set[str]:
        """
        Get entity types that should be tracked across orchestration steps.

        Returns both table names and type names for flexible matching.

        Returns:
            Set of entity type identifiers
        """
        # Default: derive from entities with complexity hints
        tracked = set()
        for entity in self.entities.values():
            if entity.complexity:
                tracked.add(entity.table)
                tracked.add(entity.type_name)
        return tracked

    @abstractmethod
    def get_subdomain_aliases(self) -> dict[str, str]:
        """
        Get natural language aliases for subdomain normalization.

        Maps informal/approximate names to canonical subdomain names.

        Returns:
            Dict like {"pantry": "inventory", "groceries": "shopping"}
        """
        ...

    def get_archive_key_for_description(self, description: str) -> str | None:
        """
        Infer a semantic archive key from a step description.

        Used for archiving generate/analyze results with meaningful keys.

        Args:
            description: Step description text

        Returns:
            Archive key string, or None for default key
        """
        return None  # Default: no semantic key

    def get_archive_keys_for_subdomain(self, subdomain: str) -> list[str]:
        """
        Get archive keys to clear when saving to a subdomain.

        After a successful write, related archive entries should be cleared
        to prevent stale generated content from persisting.

        Args:
            subdomain: The subdomain being written to

        Returns:
            List of archive keys to clear
        """
        return []  # Default: don't clear any

    def get_entity_key_fields(self) -> list[str]:
        """
        Get key fields to display in generic entity context cards.

        These are the most useful fields to show inline when displaying
        entity data that doesn't have a custom formatter.

        Returns:
            List of field names
        """
        return []  # Default: no key fields

    def get_bold_skip_words(self) -> list[str]:
        """
        Words to skip when extracting entity names from bold markdown text.

        Bold text in assistant responses often contains entity names
        (e.g., **Chicken Tikka Masala**) but also section headings
        (e.g., **Ingredients**, **Instructions**). This list filters
        out common non-entity headings.

        Returns:
            List of lowercase words/phrases to skip
        """
        return []  # Default: no skip words

    def get_generated_content_markers(self) -> list[str]:
        """
        Markers that indicate assistant responses contain generated content.

        Used to detect when a message contains domain-specific generated
        content (e.g., recipe instructions, workout plans) for summarization.

        Returns:
            List of marker strings to check for (case-insensitive)
        """
        return []  # Default: no markers

    def get_generated_content_label(self) -> str:
        """
        Label for generated content in conversation summaries.

        Returns:
            Label string (e.g., "recipe", "workout plan")
        """
        return "content"

    def get_relevant_entity_types(self) -> set[str]:
        """
        Entity types considered relevant for conversation context display.

        Filters out low-level entity types (e.g., ingredients, sub-items)
        that would clutter the context.

        Returns:
            Set of entity type names to show in context
        """
        # Default: all entity types with complexity set
        return {e.type_name for e in self.entities.values() if e.complexity}

    # =========================================================================
    # Reply Formatting
    # =========================================================================

    @abstractmethod
    def get_subdomain_formatters(self) -> dict[str, Callable]:
        """
        Get domain-specific reply formatters per subdomain.

        These formatters transform raw data into user-friendly output.

        Returns:
            Dict mapping subdomain to formatter function
        """
        ...

    def get_strip_fields(self, context: str = "injection") -> set[str]:
        """
        Get fields to strip from records before presenting to LLM/user.

        Different contexts may strip different fields:
        - "injection": Fields stripped from prompt context (e.g., user_id)
        - "reply": Fields stripped from user-facing replies (e.g., all IDs)

        Args:
            context: "injection" or "reply"

        Returns:
            Set of field names to strip
        """
        return set()  # Default: strip nothing

    def format_entity_for_context(
        self, entity_type: str, ref: str, label: str, data: dict, **kwargs: Any
    ) -> list[str]:
        """
        Format an entity's data for inclusion in Act context.

        Domain-specific formatting (e.g., recipe data with grouped ingredients).
        Returns markdown lines.

        Args:
            entity_type: The entity type (e.g., "recipe", "meal")
            ref: Entity reference (e.g., "recipe_1")
            label: Human-readable label
            data: The entity data dict
            **kwargs: Additional context (e.g., registry for ref lookup)

        Returns:
            List of formatted markdown lines
        """
        # Default: simple key-value dump
        lines = [f"### `{ref}`: {label} ({entity_type})"]
        for k, v in data.items():
            if v is not None:
                lines.append(f"  {k}: {v}")
        return lines

    def infer_table_from_record(self, record: dict) -> str | None:
        """
        Infer the table name from a record's field structure.

        Used when the table isn't known but the record contents
        can identify which entity it belongs to.

        Args:
            record: A database record dict

        Returns:
            Table name or None if unrecognizable
        """
        return None  # Default: can't infer

    def get_system_prompt(self) -> str:
        """
        Get the domain-specific system prompt.

        The system prompt defines the assistant's identity and behavior.

        Returns:
            System prompt string
        """
        return f"You are a helpful {self.name} assistant."

    def get_quick_write_confirmation(
        self, subdomain: str, count: int, action: str
    ) -> str | None:
        """
        Get a confirmation message for quick-mode write operations.

        E.g., "Added 3 items to your shopping list." or "Added 2 items to your pantry."

        Args:
            subdomain: The subdomain written to
            count: Number of items affected
            action: The action performed (e.g., "add", "delete")

        Returns:
            Confirmation string, or None for generic handling
        """
        return None  # Default: no domain-specific confirmations

    def get_priority_fields(self) -> list[str]:
        """
        Get human-readable fields to prioritize in record display.

        These are the most useful fields to show when formatting records
        for user-facing replies.

        Returns:
            Ordered list of field names
        """
        return ["name", "title", "date", "description", "notes", "category"]

    def format_record_for_context(self, record: dict, table: str | None = None) -> str:
        """
        Format a single record for Act prompt context.

        Override for domain-specific rendering (e.g., table-aware formatting
        with quantity, location, cuisine fields).

        Args:
            record: A database record dict
            table: Optional table name for format lookup

        Returns:
            Formatted string (e.g., "  - Chicken Thighs (2 lbs) [fridge] id:inv_5")
        """
        if not record:
            return "  (empty)"
        name = record.get("name") or record.get("title") or "item"
        parts = [f"  - {name}"]
        if record.get("id"):
            parts.append(f"id:{record['id']}")
        return " ".join(parts)

    def format_records_for_context(
        self, records: list[dict], table: str | None = None
    ) -> list[str]:
        """
        Format a list of records for Act prompt context.

        Override for domain-specific grouping (e.g., recipe_ingredients
        grouped by recipe_id).

        Args:
            records: List of record dicts
            table: Optional table name for format lookup

        Returns:
            List of formatted strings, one per record or group
        """
        if not records:
            return ["  (no records)"]
        return [self.format_record_for_context(r, table) for r in records]

    def format_records_for_reply(
        self, records: list[dict], table_type: str | None, indent: int = 2
    ) -> str | None:
        """
        Format records for user-facing reply display.

        Domain-specific formatting for tables that need special treatment
        (e.g., preferences as key-value, recipes with full instructions).

        Args:
            records: List of record dicts
            table_type: Detected table type (from infer_table_from_record)
            indent: Indentation spaces

        Returns:
            Formatted string, or None to use generic formatting
        """
        return None  # Default: use generic formatting

    def get_item_tracking_keys(self) -> list[str]:
        """
        Get dict keys to check when tracking item names from results.

        These are top-level keys in result dicts that contain lists of items
        with 'name' fields (e.g., "recipes", "tasks").

        Returns:
            List of key names to check
        """
        # Default: derive from entity table names
        return list(self.entities.keys())

    # =========================================================================
    # Mode/Agent Registration
    # =========================================================================

    @property
    @abstractmethod
    def bypass_modes(self) -> dict[str, type]:
        """
        Get domain-specific graph-bypass mode handlers.

        These are modes that skip the LangGraph pipeline entirely
        (e.g., cook mode, brainstorm mode).

        Returns:
            Dict mapping mode name to handler class
        """
        ...

    @property
    @abstractmethod
    def default_agent(self) -> str:
        """
        Get the default agent name for single-agent mode.

        Used by _create_default_router_output() in workflow.

        Returns:
            Agent name (e.g., "main", "fpl_main")
        """
        ...

    @property
    def agents(self) -> list:
        """
        Get the list of available agents for this domain.

        Phase 2.5: Returns AgentProtocol instances for multi-agent support.
        Default implementation returns empty list (single-agent mode).

        Returns:
            List of AgentProtocol instances
        """
        return []  # Default: no agents registered (uses bypass_modes)

    @property
    def agent_router(self):
        """
        Get the agent router for multi-agent mode.

        Phase 2.5: Returns AgentRouter instance or None for single-agent.
        Default implementation returns None (single-agent mode).

        Returns:
            AgentRouter instance or None
        """
        return None  # Default: single-agent mode

    def get_payload_compilers(self) -> list:
        """
        Get domain-specific payload compilers.

        Returns SubdomainCompiler instances that map generated artifacts
        to schema-ready payloads for database writes.

        Returns:
            List of SubdomainCompiler instances
        """
        return []  # Default: no compilers

    def get_mode_llm_config(self) -> dict[str, dict[str, Any]]:
        """
        Get LLM config overrides for domain-specific bypass modes.

        Keys are mode/node names (e.g., "cook", "brainstorm").
        Values are dicts with optional "verbosity" and "temperature" keys.

        Returns:
            Dict mapping mode name to LLM config overrides
        """
        return {}  # Default: no bypass mode LLM configs

    def get_reply_prompt_content(self) -> str:
        """
        Get domain-specific reply instructions for the Reply node.

        Returns the full reply template with domain-specific examples
        in <identity>, <subdomains>, and <principles> sections.
        When provided, this replaces the core reply.md template entirely
        (but NOT the system prompt header from get_system_prompt()).

        Returns:
            Markdown string with the complete Reply instructions,
            or empty string to fall back to core template + injection.
        """
        return ""  # Default: fall back to core template + injection

    def get_act_prompt_content(self, step_type: str) -> str:
        """
        Get domain-specific full system prompt for the Act node.

        Returns the complete Act system prompt for the given step type,
        including base layer, CRUD tools reference (for read/write),
        step-type mechanics, and domain-specific examples.

        When provided, this replaces the core template assembly entirely.

        Args:
            step_type: The act step type (read, write, analyze, generate)

        Returns:
            Full system prompt string, or empty string to fall back
            to core template assembly + injection.
        """
        return ""  # Default: fall back to core template assembly

    def get_act_prompt_injection(self, step_type: str) -> str:
        """
        Get domain-specific guidance to append to Act node prompts.

        Called for each step type (read, write, analyze, generate).
        Returns markdown text appended after the core Act prompt layers.

        Args:
            step_type: The act step type (read, write, analyze, generate)

        Returns:
            Markdown string with domain-specific examples and guidance,
            or empty string for no injection.
        """
        return ""  # Default: no domain-specific Act guidance

    def get_think_prompt_content(self) -> str:
        """
        Get domain-specific system prompt for the Think node.

        Returns the full system prompt with domain-specific examples,
        conversation management patterns, output contract examples,
        and all entity-specific guidance. When provided, this replaces
        the core think.md template AND the injection variables entirely.

        Returns:
            Markdown string with the complete Think system prompt,
            or empty string to fall back to core template + injection.
        """
        return ""  # Default: fall back to core template + injection

    def get_understand_prompt_content(self) -> str:
        """
        Get domain-specific content for the Understand node prompt.

        Returns the full prompt body with domain-specific examples,
        reference resolution patterns, quick mode table, curation examples,
        and output contract examples. The core provides only the system prompt;
        ALL user prompt content comes from the domain.

        Returns:
            Markdown string with the complete Understand prompt body,
            or empty string to fall back to the core template.
        """
        return ""  # Default: fall back to core template

    def get_think_domain_context(self) -> str:
        """
        Get domain-specific context/philosophy for Think node.

        Replaces the {domain_context} placeholder in think.md.
        Contains the domain's purpose, philosophy, and what it enables.

        Returns:
            Markdown string with domain context.
        """
        return ""  # Default: no domain-specific Think context

    def get_think_planning_guide(self) -> str:
        """
        Get domain-specific planning guide for Think node.

        Replaces the {domain_planning_guide} placeholder in think.md.
        Contains subdomains, linked tables, complex domain descriptions,
        and domain-specific planning patterns.

        Returns:
            Markdown string with planning guide content.
        """
        return ""  # Default: no domain-specific planning guide

    def get_reply_subdomain_guide(self) -> str:
        """
        Get domain-specific subdomain formatting guide for Reply node.

        Returns markdown describing how to present each subdomain's data
        to the user (e.g., inventory grouped by location, recipes in
        magazine-style format). Injected into reply prompt.

        Returns:
            Markdown string with subdomain presentation rules.
        """
        return ""  # Default: no domain-specific reply formatting

    def get_router_prompt_injection(self) -> str:
        """
        Get domain-specific content for Router prompt.

        Returns markdown with available agents, their descriptions,
        and routing examples. Injected into router prompt.

        Returns:
            Markdown string with agent definitions and examples.
        """
        return ""  # Default: no domain-specific router content

    def get_handoff_system_prompts(self) -> dict[str, str]:
        """
        Get system prompts for bypass mode handoff summaries.

        Returns:
            Dict mapping mode name to handoff system prompt text
        """
        return {}  # Default: no handoff prompts

    @abstractmethod
    def get_handoff_result_model(self) -> type:
        """
        Get the domain-specific HandoffResult Pydantic model.

        Base has: summary, action, action_detail.
        Domain extends with additional fields (e.g., recipe_content, transfer_plan).

        Returns:
            Pydantic model class for handoff results
        """
        ...

    # --- User Context (profile, dashboard, guidance) ---

    async def get_user_profile(self, user_id: str) -> str:
        """
        Return formatted user profile text for prompt injection.

        Includes hard constraints (diet, allergies, household), capabilities,
        taste preferences, and recent activity. Used by Think and Act nodes.

        Returns:
            Markdown-formatted profile string, or empty string if unavailable.
        """
        return ""

    async def get_domain_snapshot(self, user_id: str) -> str:
        """
        Return formatted domain-state summary for Think node context.

        Provides a snapshot of the user's current domain state (e.g., inventory
        counts, saved items, upcoming plans). Used by Think node for planning.

        Returns:
            Markdown-formatted snapshot string, or empty string if unavailable.
        """
        return ""

    async def get_subdomain_guidance(self, user_id: str) -> dict[str, str]:
        """
        Return per-subdomain user preference/guidance text.

        Used by Think (all subdomains) and Act (specific subdomain) nodes
        to inject user preferences into prompts.

        Returns:
            Dict mapping subdomain name to guidance text.
        """
        return {}

    # --- Database Access ---

    @abstractmethod
    def get_db_adapter(self) -> "DatabaseAdapter":
        """
        Return a database adapter for CRUD operations.

        Called per-request by the CRUD executor. The returned adapter
        must support .table() and .rpc() methods. For Supabase domains,
        this wraps get_client() which handles auth token from request context.

        Returns:
            A DatabaseAdapter-compatible object.
        """
        ...
