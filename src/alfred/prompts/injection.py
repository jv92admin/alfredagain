"""
Alfred V4 - Step-Type-Specific Prompt Injection.

This module assembles Act prompts based on step_type, mode, and context.

Step Types:
- read: Schema + filter syntax, minimal context
- analyze: Previous results prominently, no schema
- generate: User profile + creative guidance
- write: Schema + FK handling + entity tagging

V4 Changes:
- WorkingSet replaces scattered entity sections
- TurnIdMapper handles ID mapping for FK references
- BatchManifest tracks multi-item operations
- EntityContextModel provides tiered entity resolution
- SessionConstraints accumulates user preferences

Mode affects verbosity and example inclusion.

Note: Schema is passed in as a parameter (fetched by caller) to avoid async issues.
"""

from typing import Any, TYPE_CHECKING

from alfred.core.modes import Mode, MODE_CONFIG
from alfred.prompts.personas import get_persona_for_subdomain, get_full_subdomain_content

# V4 CONSOLIDATION: Only SessionIdRegistry needed now
if TYPE_CHECKING:
    from alfred.core.id_registry import SessionIdRegistry
    from alfred.graph.state import BatchManifest


def get_verbosity_label(mode: Mode) -> str:
    """Get human-readable verbosity label for prompt injection."""
    return MODE_CONFIG[mode]["verbosity"]


def build_act_prompt(
    step_description: str,
    step_type: str,
    subdomain: str,
    mode: Mode,
    entities: list[dict] | None = None,  # V4 CONSOLIDATION: changed from Entity to dict
    prev_group_results: list[dict] | None = None,
    user_profile: dict | None = None,
    schema: str | None = None,  # Schema passed in by caller
) -> str:
    """
    Assemble Act prompt based on step_type.
    
    Returns the dynamic context sections to inject into the Act prompt.
    The base Act instructions are in prompts/act/ directory (base.md + step_type.md).
    
    Args:
        step_description: What this step does
        step_type: read/analyze/generate/write
        subdomain: Which subdomain (for persona lookup)
        mode: Current mode (affects verbosity)
        entities: Available entities for context
        prev_group_results: Results from previous execution groups
        user_profile: User preferences (for generate steps)
        schema: Database schema (passed in by caller, async fetched)
    """
    sections = []
    
    # Step context (always)
    sections.append(build_step_context(step_description, step_type))
    
    # Step-type-specific sections
    if step_type == "read":
        sections.append(build_read_sections(subdomain, entities, schema))
    elif step_type == "analyze":
        sections.append(build_analyze_sections(prev_group_results, subdomain, user_profile))
    elif step_type == "generate":
        sections.append(build_generate_sections(subdomain, mode, user_profile, prev_group_results))
    elif step_type == "write":
        sections.append(build_write_sections(subdomain, entities, prev_group_results, schema, user_profile))
    else:
        # Fallback: include schema
        sections.append(build_read_sections(subdomain, entities, schema))
    
    return "\n\n".join(sections)


def build_step_context(step_description: str, step_type: str) -> str:
    """Build the step context section."""
    return f"""## Current Step

**Type:** {step_type}
**Description:** {step_description}"""


def build_read_sections(
    subdomain: str, 
    entities: list[dict] | None = None,  # V4 CONSOLIDATION
    schema: str | None = None,
) -> str:
    """
    Build sections for READ steps.
    
    Includes:
    - Schema for the subdomain
    - Filter syntax examples
    - Referenced entity IDs (if any)
    """
    parts = []
    
    # Schema (passed in by caller)
    if schema:
        parts.append(f"""## Database Schema

{schema}""")
    
    # Persona (read mode)
    persona = _get_persona(subdomain, "read")
    if persona:
        parts.append(f"""## Role for This Step

{persona}""")
    
    # Referenced entities (just IDs for joins)
    if entities:
        active_refs = [e.to_ref() for e in entities if e.state.value == "active"]
        if active_refs:
            refs_text = _format_entity_refs(active_refs)
            parts.append(f"""## Available Entity IDs

{refs_text}

Use these IDs for joins or filters when needed.""")
    
    return "\n\n".join(parts)


def build_analyze_sections(
    prev_group_results: list[dict] | None = None,
    subdomain: str | None = None,
    user_profile: dict | None = None,
) -> str:
    """
    Build sections for ANALYZE steps.
    
    Includes:
    - Previous results prominently
    - User subdomain guidance (if available)
    - Critical warning about data sources
    
    Does NOT include:
    - Schema (not querying DB)
    - Entity data (only results)
    """
    parts = []
    
    # User subdomain guidance (personalization)
    if subdomain and user_profile:
        guidance_section = format_subdomain_guidance_section(user_profile, subdomain)
        if guidance_section:
            parts.append(guidance_section)
    
    # Previous results (THE data source)
    if prev_group_results:
        results_text = _format_prev_results(prev_group_results)
        parts.append(f"""## Data to Analyze

{results_text}""")
    else:
        parts.append("""## Data to Analyze

No data from previous steps. Report "No data to analyze" in your step_complete.""")
    
    # Critical warning
    parts.append("""## CRITICAL

Only analyze the data shown above in "Data to Analyze".
- If the data is empty `[]`, report "No data to analyze"
- Do NOT invent or hallucinate data
- Do NOT use entity references as data sources
- Your analysis must be grounded in the actual results shown""")
    
    return "\n\n".join(parts)


def build_generate_sections(
    subdomain: str,
    mode: Mode,
    user_profile: dict | None = None,
    prev_group_results: list[dict] | None = None,
) -> str:
    """
    Build sections for GENERATE steps.
    
    Includes:
    - Persona (generate mode)
    - User profile for personalization
    - Verbosity guidance
    - Prior context (summary)
    - Entity tagging instructions
    """
    parts = []
    
    # Persona (generate mode)
    persona = _get_persona(subdomain, "generate")
    if persona:
        parts.append(f"""## Role for This Step

{persona}""")
    
    # User profile (general)
    if user_profile:
        profile_text = _format_user_profile(user_profile, mode)
        parts.append(f"""## User Profile

{profile_text}""")
    
    # Subdomain-specific guidance (personalization)
    if user_profile:
        guidance_section = format_subdomain_guidance_section(user_profile, subdomain)
        if guidance_section:
            parts.append(guidance_section)
    
    # Prior context (summary, not full data)
    if prev_group_results:
        summary = _summarize_prev_results(prev_group_results)
        parts.append(f"""## Prior Context

{summary}""")
    
    # Generation guidance
    verbosity = get_verbosity_label(mode)
    parts.append(f"""## Generation Guidelines

- **Verbosity:** {verbosity}
- **Personalize:** Use user preferences shown above
- **Be creative:** But stay grounded in user's context""")
    
    # Entity tagging
    parts.append("""## Entity Tagging

When generating content, tag it for tracking:
```json
{
  "temp_id": "temp_recipe_1",
  "type": "recipe",
  "label": "Quick Weeknight Pasta"
}
```

Use `temp_id` prefix for generated content. This allows the system to track it.""")
    
    return "\n\n".join(parts)


def build_write_sections(
    subdomain: str,
    entities: list[dict] | None = None,  # V4 CONSOLIDATION
    prev_group_results: list[dict] | None = None,
    schema: str | None = None,
    user_profile: dict | None = None,
) -> str:
    """
    Build sections for WRITE steps.
    
    Includes:
    - Schema for the subdomain
    - User subdomain guidance (for naming, tagging preferences)
    - FK handling guidance
    - Entity IDs from prior steps
    - Entity tagging instructions
    """
    parts = []
    
    # User subdomain guidance (personalization for naming, tagging, etc.)
    if user_profile:
        guidance_section = format_subdomain_guidance_section(user_profile, subdomain)
        if guidance_section:
            parts.append(guidance_section)
    
    # Schema (passed in by caller)
    if schema:
        parts.append(f"""## Database Schema

{schema}""")
    
    # Persona
    persona = _get_persona(subdomain, "write")
    if persona:
        parts.append(f"""## Role for This Step

{persona}""")
    
    # Entity IDs for FK references
    if entities:
        pending_refs = [e.to_ref() for e in entities if e.state.value == "pending"]
        active_refs = [e.to_ref() for e in entities if e.state.value == "active"]
        
        if pending_refs or active_refs:
            parts.append("## Entity IDs from Prior Steps")
            if active_refs:
                parts.append(f"**Active (confirmed):**\n{_format_entity_refs(active_refs)}")
            if pending_refs:
                parts.append(f"**Pending (awaiting confirmation):**\n{_format_entity_refs(pending_refs)}")
    
    # IDs from prev group results
    if prev_group_results:
        ids_text = _extract_ids_from_results(prev_group_results)
        if ids_text:
            parts.append(f"""## IDs from Previous Steps

{ids_text}""")
    
    # Entity tagging for writes
    parts.append("""## Entity Tagging on Write

When creating records:
- Tag new entities with state: "pending" (awaiting user confirmation)
- Include temp_id if no DB ID yet
- Report created entities in step_complete data

```json
{
  "new_entities": [
    {"id": "uuid-from-db", "type": "recipe", "label": "Butter Chicken", "state": "pending"}
  ]
}
```""")
    
    return "\n\n".join(parts)


# =============================================================================
# Helper Functions
# =============================================================================


def _get_persona(subdomain: str, step_type: str = "read") -> str | None:
    """Get persona text for subdomain."""
    persona = get_persona_for_subdomain(subdomain, step_type)
    return persona if persona else None


def _format_entity_refs(refs: list[dict]) -> str:
    """Format entity refs for prompt injection."""
    if not refs:
        return "None"
    
    lines = []
    for ref in refs[:10]:  # Limit to 10
        lines.append(f"- {ref['type']}: {ref['label']} (ID: {ref['id']})")
    
    if len(refs) > 10:
        lines.append(f"... and {len(refs) - 10} more")
    
    return "\n".join(lines)


def _format_prev_results(results: list[dict]) -> str:
    """Format previous results for analyze steps in a clean, readable format."""
    if not results:
        return "No prior results."
    
    lines = []
    for i, result in enumerate(results):
        if isinstance(result, dict):
            data = result.get("data", result)
            # Try to detect table from result metadata or first record
            table = result.get("table")
            if not table and isinstance(data, list) and data:
                # Infer from record structure
                table = _infer_table_from_record(data[0])
            
            if isinstance(data, list):
                table_label = f" from `{table}`" if table else ""
                lines.append(f"**Step {i} results** ({len(data)} items{table_label}):")
                formatted = _format_records_for_table(data[:50], table)
                lines.extend(formatted)
                if len(data) > 50:
                    lines.append(f"  ... and {len(data) - 50} more items")
            elif isinstance(data, dict):
                lines.append(f"**Step {i} result**:")
                lines.append(_format_record_clean(data, table))
            else:
                lines.append(f"**Step {i}**: {str(data)[:200]}")
        lines.append("")
    
    return "\n".join(lines)


def _infer_table_from_record(record: dict) -> str | None:
    """Infer table name from record structure."""
    if not isinstance(record, dict):
        return None
    
    # Table-specific field patterns
    if "recipe_id" in record and "name" in record and "quantity" in record:
        return "recipe_ingredients"
    if "meal_type" in record and "date" in record:
        return "meal_plans"
    if "cuisine" in record or "prep_time" in record or "cook_time" in record:
        return "recipes"
    if "location" in record or "expiry_date" in record:
        return "inventory"
    if "is_purchased" in record:
        return "shopping_list"
    if "due_date" in record or "status" in record:
        return "tasks"
    if "dietary_restrictions" in record or "allergies" in record:
        return "preferences"
    
    return None


# =============================================================================
# Table-Specific Formatting Protocols
# =============================================================================

# Define how each table should be formatted for LLM consumption
# Format: {table: {primary: str, details: [str], show_id: bool}}
_TABLE_FORMAT_PROTOCOLS = {
    "inventory": {
        "primary": "name",
        "details": ["quantity", "unit", "location", "category", "expiry_date"],
        "show_id": True,
    },
    "shopping_list": {
        "primary": "name", 
        "details": ["quantity", "unit", "category"],
        "show_id": True,
    },
    "recipes": {
        "primary": "name",
        "details": ["cuisine", "total_time", "servings", "occasions", "health_tags"],
        "show_id": True,  # Critical for FK references
        "format": "recipe",  # Custom format with grouped ingredients
    },
    "recipe_ingredients": {
        "primary": "name",
        "details": ["quantity", "unit"],
        "show_id": False,  # Not needed, use recipe_id
        "group_by": "recipe_id",  # Hint to group these
    },
    "meal_plans": {
        "primary": "date",
        "details": ["meal_type", "recipe_id"],  # Show recipe_id for linking
        "show_id": True,
        "format": "meal_plan",  # Custom format: date [slot] → recipe
    },
    "tasks": {
        "primary": "title",
        "details": ["due_date", "status", "category"],
        "show_id": True,
    },
    "preferences": {
        "primary": None,  # Special: no single primary, show as key-value pairs
        "details": ["dietary_restrictions", "allergies", "favorite_cuisines", "cooking_skill_level"],
        "show_id": False,
        "format": "key_value",  # Special format mode
    },
}

# Fields to always strip (internal noise)
_STRIP_FIELDS = {"user_id", "created_at", "updated_at", "ingredient_id"}


def _format_record_clean(record: dict, table: str | None = None) -> str:
    """Format a single record using table-specific protocol."""
    if not record:
        return "  (empty)"
    
    # Get protocol for this table (or use generic)
    protocol = _TABLE_FORMAT_PROTOCOLS.get(table, {
        "primary": "name",
        "details": ["quantity", "unit", "location"],
        "show_id": True,
    })
    
    # Special format: key-value pairs (for preferences, single-row configs)
    if protocol.get("format") == "key_value":
        return _format_record_key_value(record, protocol)
    
    # Special format: meal plan (date [slot] → recipe)
    if protocol.get("format") == "meal_plan":
        return _format_meal_plan_record(record, protocol)
    
    # Special format: recipe (with grouped ingredients)
    if protocol.get("format") == "recipe":
        return _format_recipe_record(record, protocol)
    
    # Get primary identifier
    primary_field = protocol.get("primary", "name")
    primary_value = record.get(primary_field) or record.get("name") or record.get("title") or "item"
    
    parts = [f"  - {primary_value}"]
    
    # Add configured details
    for field in protocol.get("details", []):
        value = record.get(field)
        if value is not None and value != "":
            # Format based on field type
            if field in ("quantity",):
                unit = record.get("unit", "")
                parts.append(f"({value}{' ' + unit if unit else ''})")
            elif field in ("location", "meal_type", "status"):
                parts.append(f"[{value}]")
            elif field in ("cuisine", "category"):
                parts.append(f"({value})")
            elif field in ("date", "due_date", "expiry_date"):
                parts.append(f"@{value}")
            elif field == "recipe_id":
                # V4: IDs are simple refs (recipe_1)
                # V5: Include label if available (from prior reads)
                label = record.get("_recipe_id_label")
                if label:
                    parts.append(f"recipe:{label} ({value})")
                else:
                    parts.append(f"recipe:{value}")
            elif field in ("total_time", "servings"):
                parts.append(f"{field}:{value}")
            elif field in ("tags", "occasions", "health_tags", "flavor_tags", "equipment_tags") and isinstance(value, list):
                parts.append(f"[{', '.join(value[:3])}{'...' if len(value) > 3 else ''}]")
            else:
                parts.append(f"{field}:{value}")
    
    # Add ID if protocol says to
    # V4: IDs are simple refs (recipe_1, inv_5), show in full
    if protocol.get("show_id", True) and record.get("id"):
        parts.append(f"id:{record['id']}")
    
    return " ".join(parts)


def _format_record_key_value(record: dict, protocol: dict) -> str:
    """Format a record as key-value pairs (for preferences, configs)."""
    lines = ["  User Preferences:"]
    for field in protocol.get("details", []):
        value = record.get(field)
        if value is not None and value != "" and value != []:
            # Format arrays nicely
            if isinstance(value, list):
                value_str = ", ".join(str(v) for v in value)
            else:
                value_str = str(value)
            # Human-friendly field names
            label = field.replace("_", " ").title()
            lines.append(f"    - {label}: {value_str}")
    return "\n".join(lines)


def _format_meal_plan_record(record: dict, protocol: dict) -> str:
    """
    Format a meal plan record: date [slot] → recipe (id:meal_1)
    
    Examples:
    - 2026-01-12 [lunch] → Butter Chicken (recipe_1) id:meal_1
    - 2026-01-13 [dinner] → recipe_2 id:meal_2
    """
    date = record.get("date", "no-date")
    meal_type = record.get("meal_type", "meal")
    recipe_ref = record.get("recipe_id", "no-recipe")
    meal_id = record.get("id", "")
    
    # Try to get enriched recipe name
    recipe_label = record.get("_recipe_id_label")
    
    if recipe_label:
        recipe_part = f"{recipe_label} ({recipe_ref})"
    else:
        recipe_part = recipe_ref
    
    # Format: date [slot] → recipe id:meal_X
    parts = [f"  - {date} [{meal_type}] → {recipe_part}"]
    
    if meal_id:
        parts.append(f"id:{meal_id}")
    
    return " ".join(parts)


def _format_recipe_record(record: dict, protocol: dict) -> str:
    """
    Format a recipe record with grouped ingredients.
    
    Output format:
    ```
    recipe_1 (Chicken Tikka):
      cuisine: indian | time: 45min | servings: 4
      occasions: weeknight | health: high-protein
      proteins: chicken
      vegetables: onion, bell pepper
      dairy: yogurt
      spices: garam masala, turmeric
      [instructions: 8 steps]  # only if present
    ```
    """
    lines = []
    
    # Line 1: Name and ID
    name = record.get("name", "Recipe")
    recipe_id = record.get("id", "")
    lines.append(f"  {recipe_id} ({name}):")
    
    # Line 2: Core metadata
    meta_parts = []
    if record.get("cuisine"):
        meta_parts.append(f"cuisine: {record['cuisine']}")
    
    # Combine prep + cook time if available
    prep = record.get("prep_time_minutes") or record.get("prep_time")
    cook = record.get("cook_time_minutes") or record.get("cook_time")
    total = record.get("total_time")
    if total:
        meta_parts.append(f"time: {total}")
    elif prep or cook:
        time_str = f"{prep or 0}+{cook or 0}min"
        meta_parts.append(f"time: {time_str}")
    
    if record.get("servings"):
        meta_parts.append(f"servings: {record['servings']}")
    if record.get("difficulty"):
        meta_parts.append(f"difficulty: {record['difficulty']}")
    
    if meta_parts:
        lines.append(f"    {' | '.join(meta_parts)}")
    
    # Line 3: Tags (occasions, health)
    tag_parts = []
    if record.get("occasions"):
        tag_parts.append(f"occasions: {', '.join(record['occasions'][:3])}")
    if record.get("health_tags"):
        tag_parts.append(f"health: {', '.join(record['health_tags'][:3])}")
    if record.get("flavor_tags"):
        tag_parts.append(f"flavor: {', '.join(record['flavor_tags'][:2])}")
    if record.get("equipment_tags"):
        tag_parts.append(f"equipment: {', '.join(record['equipment_tags'][:2])}")
    
    if tag_parts:
        lines.append(f"    {' | '.join(tag_parts)}")
    
    # Ingredients grouped by category
    ingredients = record.get("recipe_ingredients", [])
    if ingredients:
        # Group by category
        from collections import defaultdict
        by_category = defaultdict(list)
        for ing in ingredients:
            cat = ing.get("category") or "other"
            name = ing.get("name", "?")
            by_category[cat].append(name)
        
        # Display each category
        # Priority order for display
        category_order = ["proteins", "vegetables", "produce", "fruits", "dairy", "cheese", 
                         "grains", "rice", "pasta", "pantry", "canned", "spices", 
                         "cuisine_indian", "cuisine_thai", "cuisine_mexican", "other"]
        
        displayed_cats = set()
        for cat in category_order:
            if cat in by_category:
                names = by_category[cat]
                # Dedupe and join
                unique_names = list(dict.fromkeys(names))  # preserve order, dedupe
                lines.append(f"    {cat}: {', '.join(unique_names)}")
                displayed_cats.add(cat)
        
        # Any remaining categories
        for cat, names in by_category.items():
            if cat not in displayed_cats:
                unique_names = list(dict.fromkeys(names))
                lines.append(f"    {cat}: {', '.join(unique_names)}")
    
    # Instructions (only if present)
    instructions = record.get("instructions")
    if instructions:
        if isinstance(instructions, list):
            lines.append(f"    [instructions: {len(instructions)} steps]")
        else:
            lines.append(f"    [instructions: included]")
    
    return "\n".join(lines)


def _format_records_for_table(records: list[dict], table: str | None = None) -> list[str]:
    """
    Format a list of records with table-aware formatting.
    
    For recipe_ingredients, groups by recipe_id for clarity.
    """
    if not records:
        return ["  (no records)"]
    
    protocol = _TABLE_FORMAT_PROTOCOLS.get(table, {})
    
    # Check if we should group (e.g., recipe_ingredients by recipe_id)
    group_by = protocol.get("group_by")
    
    if group_by and table == "recipe_ingredients":
        # Group by recipe_id and summarize
        from collections import defaultdict
        grouped = defaultdict(list)
        for rec in records:
            key = rec.get(group_by, "unknown")
            grouped[key].append(rec.get("name", "item"))
        
        lines = []
        for recipe_id, ingredients in grouped.items():
            # V4: IDs are simple refs, show in full
            lines.append(f"  - recipe:{recipe_id}: {len(ingredients)} ingredients ({', '.join(ingredients[:5])}{'...' if len(ingredients) > 5 else ''})")
        return lines
    
    # Standard formatting
    return [_format_record_clean(rec, table) for rec in records]


def _summarize_prev_results(results: list[dict]) -> str:
    """Summarize previous results for generate steps (not full data)."""
    if not results:
        return "No prior data available."
    
    summaries = []
    for i, result in enumerate(results):
        if isinstance(result, dict):
            if "result_summary" in result:
                summaries.append(f"Step {i}: {result['result_summary']}")
            elif "data" in result:
                data = result["data"]
                if isinstance(data, list):
                    summaries.append(f"Step {i}: {len(data)} records")
                else:
                    summaries.append(f"Step {i}: Data available")
    
    return "\n".join(summaries) if summaries else "Prior steps completed."


def _extract_ids_from_results(results: list[dict]) -> str:
    """Extract entity IDs from previous results for write steps."""
    ids = []
    for result in results:
        if isinstance(result, dict):
            # Check for IDs in various formats
            if "id" in result:
                ids.append(result["id"])
            if "data" in result:
                data = result["data"]
                if isinstance(data, dict) and "id" in data:
                    ids.append(data["id"])
                elif isinstance(data, list):
                    for item in data[:5]:  # Limit
                        if isinstance(item, dict) and "id" in item:
                            ids.append(item["id"])
    
    if not ids:
        return ""
    
    return "Available IDs: " + ", ".join(str(id) for id in ids[:10])


def _format_user_profile(profile: dict, mode: Mode) -> str:
    """Format user profile based on mode verbosity."""
    if not profile:
        return "No user profile available."
    
    detail = MODE_CONFIG[mode]["profile_detail"]
    
    if detail == "minimal":
        # Just restrictions and allergies
        parts = []
        if profile.get("dietary_restrictions"):
            parts.append(f"Restrictions: {', '.join(profile['dietary_restrictions'])}")
        if profile.get("allergies"):
            parts.append(f"Allergies: {', '.join(profile['allergies'])}")
        return "\n".join(parts) if parts else "No restrictions."
    
    elif detail == "compact":
        # Restrictions + current focus
        parts = []
        if profile.get("dietary_restrictions"):
            parts.append(f"Restrictions: {', '.join(profile['dietary_restrictions'])}")
        if profile.get("current_vibes"):
            parts.append(f"Current focus: {', '.join(profile['current_vibes'])}")
        return "\n".join(parts) if parts else "No profile data."
    
    else:  # full
        # Everything
        import json
        return json.dumps(profile, indent=2)


# =============================================================================
# Subdomain Guidance (User Preference Modules)
# =============================================================================

# Max tokens per subdomain guidance (~200 tokens ≈ 800 chars)
MAX_GUIDANCE_CHARS = 800


def get_subdomain_guidance(
    user_profile: dict | None,
    subdomain: str,
) -> str | None:
    """
    Extract subdomain-specific guidance from user profile.
    
    Returns narrative preference module for the given subdomain,
    or None if not available.
    
    These are injected into Analyze and Generate steps to personalize
    Alfred's reasoning and generation behavior.
    """
    if not user_profile:
        return None
    
    guidance_dict = user_profile.get("subdomain_guidance", {})
    if not guidance_dict or not isinstance(guidance_dict, dict):
        return None
    
    guidance = guidance_dict.get(subdomain)
    if not guidance or not isinstance(guidance, str):
        return None
    
    # Truncate if too long (with note)
    if len(guidance) > MAX_GUIDANCE_CHARS:
        return guidance[:MAX_GUIDANCE_CHARS] + "..."
    
    return guidance


def format_subdomain_guidance_section(
    user_profile: dict | None,
    subdomain: str,
) -> str:
    """
    Format subdomain guidance as a prompt section.
    
    Returns empty string if no guidance available.
    """
    guidance = get_subdomain_guidance(user_profile, subdomain)
    if not guidance:
        return ""
    
    return f"""## User Preferences ({subdomain})

{guidance}
"""


def format_all_subdomain_guidance(user_profile: dict | None) -> str:
    """
    Format ALL subdomain guidance for Think node.
    
    Think needs to see all guidance to make informed planning decisions
    about which subdomains to use and how.
    
    Returns empty string if no guidance available.
    """
    if not user_profile:
        return ""
    
    guidance_dict = user_profile.get("subdomain_guidance", {})
    if not guidance_dict or not isinstance(guidance_dict, dict):
        return ""
    
    parts = []
    for subdomain, guidance in guidance_dict.items():
        if guidance and isinstance(guidance, str):
            # Truncate each if needed
            if len(guidance) > MAX_GUIDANCE_CHARS:
                guidance = guidance[:MAX_GUIDANCE_CHARS] + "..."
            parts.append(f"**{subdomain}:** {guidance}")
    
    if not parts:
        return ""
    
    return "## User Preferences (by domain)\n\n" + "\n\n".join(parts)


# =============================================================================
# Quick Mode Prompt Builder
# =============================================================================


def build_act_quick_prompt(
    intent: str,
    subdomain: str,
    schema: str,
    today: str,
    user_message: str = "",
    engagement_summary: str = "",
    user_preferences: dict | None = None,
) -> tuple[str, str]:
    """
    Build system and user prompts for Act Quick mode.
    
    Act Quick is just Act doing a single step. We reuse the same prompt components
    with a simplified wrapper.
    
    Args:
        intent: Plaintext intent from Understand (e.g., "Add 1lb popcorn to inventory")
        subdomain: Target subdomain (inventory, shopping, recipes, etc.)
        schema: Database schema for the subdomain
        today: Today's date in ISO format
        user_message: The user's original message (contains actual data to process)
        engagement_summary: Current session context (what we're helping with)
        user_preferences: User profile data (allergies, restrictions, etc.)
        
    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    from pathlib import Path
    from alfred.prompts.personas import get_subdomain_intro, get_persona_for_subdomain
    
    # === SYSTEM PROMPT: Load Act's prompts, same as Act ===
    prompts_dir = Path(__file__).parent.parent.parent / "prompts" / "act"
    
    def load_prompt(filename: str) -> str:
        path = prompts_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else ""
    
    base = load_prompt("base.md")
    crud = load_prompt("crud.md")
    
    # Quick mode header replaces the looping mechanics
    quick_header = """# Alfred Quick Execution

You are Alfred's execution engine for a simple, single-step request.

**Your job:** Return ONE tool call. No looping, no step_complete.

**Output:** `{"tool": "db_read|db_create|db_update|db_delete", "params": {...}}`

**⚠️ CRITICAL: Filter values must be LITERAL values only.**
- ✅ `"value": "%cod%"` — literal string
- ✅ `"value": ["cod", "salmon"]` — literal array  
- ❌ `"value": "select ... from ..."` — NO SQL, NO subqueries

---

"""
    
    # Combine: quick header + crud (tools + filters)
    system_prompt = quick_header + crud
    
    # === USER PROMPT: Same structure as Act ===
    subdomain_intro = get_subdomain_intro(subdomain)
    subdomain_persona = get_persona_for_subdomain(subdomain, "read")  # Default to read persona
    
    user_parts = []
    
    # Subdomain intro (same as Act)
    user_parts.append(subdomain_intro)
    
    # Status section (simplified from Act)
    user_parts.append(f"""---

## STATUS
| Today | {today} |
| Task | {intent} |""")
    
    # Task section (same as Act)
    user_parts.append(f"""---

## 1. Task

User said: "{user_message}"

Your job: **{intent}**""")
    
    # User profile (if available)
    if user_preferences:
        pref_parts = []
        if user_preferences.get("allergies"):
            pref_parts.append(f"Allergies: {', '.join(user_preferences['allergies'])}")
        if user_preferences.get("dietary_restrictions"):
            pref_parts.append(f"Diet: {', '.join(user_preferences['dietary_restrictions'])}")
        if pref_parts:
            user_parts.append(f"""---

## 2. User Profile

{chr(10).join(pref_parts)}""")
    
    # Schema (same as Act)
    user_parts.append(f"""---

## 3. Schema ({subdomain})

{schema}""")
    
    # Guidance/persona (same as Act)
    if subdomain_persona:
        user_parts.append(f"""---

## 4. Guidance

{subdomain_persona}""")
    
    # Decision prompt (simplified - no step_complete)
    user_parts.append("""---

## DECISION

Analyze the intent and choose the appropriate tool:
- **db_read** for listing/showing/getting
- **db_create** for adding/creating/saving
- **db_update** for changing/modifying/updating
- **db_delete** for removing/deleting/clearing

Return: `{"tool": "...", "params": {"table": "...", ...}}`""")
    
    user_prompt = "\n\n".join(user_parts)
    
    return system_prompt, user_prompt


# =============================================================================
# V4 Context Building Functions
# =============================================================================


def build_v4_context_sections(
    step_type: str,
    registry: "SessionIdRegistry | None" = None,
    batch_manifest: "BatchManifest | None" = None,
) -> str:
    """
    V4 CONSOLIDATION: Build context sections for Act prompts.
    
    Uses SessionIdRegistry as single source of truth.
    
    Args:
        step_type: Current step type
        registry: SessionIdRegistry instance
        batch_manifest: BatchManifest instance (if batch operation)
    """
    sections = []
    
    # 1. Entity context from registry
    if registry:
        entity_section = registry.format_for_act_prompt()
        if entity_section and "No entities" not in entity_section:
            sections.append(entity_section)
    
    # 2. Batch Manifest (if multi-item operation)
    if batch_manifest and batch_manifest.total > 1:
        sections.append(batch_manifest.to_prompt_table())
    
    if not sections:
        return ""
    
    return "\n\n---\n\n".join(sections)


def build_write_context(
    registry: "SessionIdRegistry | None" = None,
    batch_manifest: "BatchManifest | None" = None,
    compiled_payloads: list | None = None,
) -> str:
    """
    V4 CONSOLIDATION: Build context specifically for WRITE steps.
    
    Write steps need:
    1. What to save (from registry)
    2. Batch progress (if multi-item)
    
    Returns a focused context section.
    """
    sections = []
    
    # 1. Batch Manifest (what we're saving)
    if batch_manifest and batch_manifest.total > 0:
        sections.append(batch_manifest.to_prompt_table())
    
    # 2. Entity context from registry
    if registry:
        entity_section = registry.format_for_act_prompt()
        if entity_section and "No entities" not in entity_section:
            sections.append(entity_section)
    
    # 3. Content to Save (compiled payloads)
    if compiled_payloads:
        import json
        lines = ["## Content to Save (Pre-Compiled)", ""]
        for payload in compiled_payloads:
            if hasattr(payload, 'target_table'):
                for record in payload.records:
                    lines.append(f"**{record.ref}** → `{payload.target_table}`:")
                    lines.append("```json")
                    lines.append(json.dumps(record.data, indent=2, default=str))
                    lines.append("```")
                    if record.linked_records:
                        for linked in record.linked_records:
                            lines.append(f"  └─ `{linked.table}`: {len(linked.records)} records")
                    lines.append("")
        sections.append("\n".join(lines))
    
    if not sections:
        return "*No content to save.*"
    
    return "\n\n---\n\n".join(sections)


def build_entity_context_for_understand(
    registry: "SessionIdRegistry | None" = None,
) -> str:
    """
    V4 CONSOLIDATION: Build entity context for Understand node.
    
    Uses SessionIdRegistry to show all tracked entities.
    """
    if registry:
        return registry.format_for_understand_prompt()
    return "*No entities tracked.*"


# V4 CONSOLIDATION: build_constraints_context removed - constraints not needed with simplified system


# =============================================================================
# V4 Summarize Context Building
# =============================================================================


def build_summarize_context(
    step_results: dict[int, Any],
    step_metadata: dict[int, dict],
    registry: "SessionIdRegistry | None" = None,
    batch_manifest: "BatchManifest | None" = None,
) -> str:
    """
    V4 CONSOLIDATION: Build context for Summarize node.
    
    Uses SessionIdRegistry for entity information.
    """
    sections = []
    
    # 1. Entity Summary from registry
    if registry:
        entity_section = registry.format_for_act_prompt()
        if entity_section and "No entities" not in entity_section:
            sections.append(entity_section)
    
    # 2. Step Results Summary
    if step_metadata:
        lines = ["### Steps Executed", ""]
        for idx, meta in sorted(step_metadata.items()):
            step_type = meta.get("step_type", "unknown")
            desc = meta.get("description", "")[:50]
            artifacts = meta.get("artifacts", [])
            artifact_count = len(artifacts) if artifacts else 0
            
            status = "✅"
            if step_type == "generate" and artifact_count > 0:
                status = f"📝 ({artifact_count} items)"
            elif step_type == "write":
                status = "💾"
            
            lines.append(f"- Step {idx + 1} [{step_type}]: {desc} {status}")
        sections.append("\n".join(lines))
    
    # 3. Batch Progress (if applicable)
    if batch_manifest and batch_manifest.total > 0:
        lines = [
            "### Batch Progress",
            f"- Total: {batch_manifest.total}",
            f"- Completed: {batch_manifest.completed_count}",
            f"- Failed: {batch_manifest.failed_count}",
        ]
        sections.append("\n".join(lines))
    
    if not sections:
        return "No turn activity to summarize."
    
    return "\n\n".join(sections)

