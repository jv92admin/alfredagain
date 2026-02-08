"""
Alfred V4 - Step-Type-Specific Prompt Injection.

This module assembles Act prompts based on step_type, mode, and context.

## Architecture (see docs/prompts/act-prompt-structure.md)

User prompts are built from two layers:
1. COMMON SECTIONS (all step types): status, task, entity context, conversation, decision
2. STEP-TYPE SECTIONS (varies): schema (read/write), guidance (analyze/generate), artifacts (write)

The main entry point is `build_act_user_prompt()` which combines both layers.

## Step Types
- read: Schema + filter syntax + CRUD examples
- analyze: Previous results prominently, analysis guidance, no schema
- generate: User profile + creative guidance + subdomain persona
- write: Schema + FK handling + batch manifest + artifacts

## Key Functions
- build_act_user_prompt() — Main entry point, assembles full user prompt
- build_common_sections() — Sections used by ALL step types
- build_step_type_sections() — Step-type-specific sections

Note: Schema is passed in as a parameter (fetched by caller) to avoid async issues.
"""

from datetime import date
from typing import Any, TYPE_CHECKING

from alfred.core.modes import Mode, MODE_CONFIG

# V4 CONSOLIDATION: Only SessionIdRegistry needed now
if TYPE_CHECKING:
    from alfred.core.id_registry import SessionIdRegistry
    from alfred.graph.state import BatchManifest


def get_verbosity_label(mode: Mode) -> str:
    """Get human-readable verbosity label for prompt injection."""
    return MODE_CONFIG[mode]["verbosity"]


# =============================================================================
# Main Entry Point: build_act_user_prompt()
# =============================================================================


def build_act_user_prompt(
    # Step info
    step_type: str,
    step_index: int,
    total_steps: int,
    step_description: str,
    subdomain: str,
    user_message: str,
    # Context data
    entity_context: str,
    conversation_context: str,
    prev_turn_context: str,
    prev_step_results: str,
    current_step_results: str,
    # Step-type specific (passed only when needed)
    schema: str | None = None,
    profile_section: str | None = None,
    subdomain_guidance: str | None = None,
    batch_manifest_section: str | None = None,
    artifacts_section: str | None = None,
    archive_section: str | None = None,
    prev_step_note: str | None = None,
    # Metadata
    tool_calls_made: int = 0,
    prev_subdomain: str | None = None,
) -> str:
    """
    Build the complete Act user prompt from common + step-type sections.
    
    This is the main entry point for Act prompt assembly.
    See docs/prompts/act-prompt-structure.md for the full specification.
    
    Args:
        step_type: read, write, analyze, or generate
        step_index: Current step index (0-based)
        total_steps: Total number of steps in plan
        step_description: What this step should accomplish
        subdomain: Target subdomain (recipes, inventory, etc.)
        user_message: User's original request
        entity_context: Formatted entity refs/data from SessionIdRegistry
        conversation_context: Recent conversation history
        prev_turn_context: Summary of last turn's steps
        prev_step_results: Results from earlier steps this turn
        current_step_results: Tool results from current step (if any)
        schema: Database schema (read/write only)
        profile_section: User profile (analyze/generate only)
        subdomain_guidance: User's subdomain-specific preferences
        batch_manifest_section: Batch progress table (write only)
        artifacts_section: Generated content (write/generate/analyze)
        archive_section: Available archives from prior turns
        prev_step_note: Note from previous step
        tool_calls_made: Number of tool calls so far in this step
        prev_subdomain: Previous step's subdomain (for cross-domain examples)
        
    Returns:
        Complete user prompt string
    """
    today = date.today().isoformat()
    
    # === Build common sections ===
    common = _build_common_sections(
        step_type=step_type,
        step_index=step_index,
        total_steps=total_steps,
        step_description=step_description,
        subdomain=subdomain,
        user_message=user_message,
        entity_context=entity_context,
        conversation_context=conversation_context,
        prev_turn_context=prev_turn_context,
        prev_step_results=prev_step_results,
        current_step_results=current_step_results,
        tool_calls_made=tool_calls_made,
        today=today,
    )
    
    # === Build step-type-specific sections ===
    specific = _build_step_type_sections(
        step_type=step_type,
        subdomain=subdomain,
        step_description=step_description,
        schema=schema,
        profile_section=profile_section,
        subdomain_guidance=subdomain_guidance,
        batch_manifest_section=batch_manifest_section,
        artifacts_section=artifacts_section,
        archive_section=archive_section,
        prev_step_note=prev_step_note,
        prev_subdomain=prev_subdomain,
    )
    
    # === Assemble final prompt ===
    # Order: header → schema → status → profile → task → guidance → data → entities → context → decision
    parts = []
    
    # 1. Subdomain header (step-type persona)
    if specific.get("subdomain_header"):
        parts.append(specific["subdomain_header"])
        parts.append("---")
    
    # 2. Schema (read/write only) — right after header so examples can reference it
    if specific.get("schema"):
        parts.append(specific["schema"])
        parts.append("---")
    
    # 3. User preferences for write steps (profile + subdomain guidance)
    if step_type == "write":
        if profile_section:
            parts.append(profile_section)
        if subdomain_guidance:
            parts.append(subdomain_guidance)
    
    # 4. STATUS table
    parts.append(common["status"])
    parts.append("---")
    
    # 5. Previous step note (if any)
    if specific.get("prev_note"):
        parts.append(specific["prev_note"])
        parts.append("---")
    
    # 6. User profile (analyze/generate only)
    if profile_section and step_type in ("analyze", "generate"):
        parts.append(profile_section)
    
    # 7. Subdomain guidance (user preferences - after profile for analyze/generate)
    if step_type in ("analyze", "generate") and subdomain_guidance:
        parts.append(subdomain_guidance)
    
    # 8. Task section
    parts.append(common["task"])
    parts.append("---")
    
    # 9. Batch manifest (write only)
    if specific.get("batch_manifest"):
        parts.append(specific["batch_manifest"])
        parts.append("---")
    
    # 10. Step-type guidance/examples — now can reference schema above
    if specific.get("guidance"):
        parts.append(specific["guidance"])
        parts.append("---")
    
    # 11. Data section (different label for analyze/generate vs read/write)
    parts.append(common["data_section"])
    parts.append("---")
    
    # 12. Entities in Context (ALWAYS included)
    parts.append(common["entities"])
    parts.append("---")
    
    # 13. Artifacts (write only)
    if specific.get("artifacts"):
        parts.append(specific["artifacts"])
        parts.append("---")
    
    # 14. Conversation context
    parts.append(common["conversation"])
    parts.append("---")
    
    # 15. Decision prompt
    parts.append(common["decision"])
    
    return "\n\n".join(parts)


def _build_common_sections(
    step_type: str,
    step_index: int,
    total_steps: int,
    step_description: str,
    subdomain: str,
    user_message: str,
    entity_context: str,
    conversation_context: str,
    prev_turn_context: str,
    prev_step_results: str,
    current_step_results: str,
    tool_calls_made: int,
    today: str,
) -> dict[str, str]:
    """
    Build sections common to ALL step types.
    
    See docs/prompts/act-prompt-structure.md for the full specification.
    
    These sections are NEVER omitted regardless of step type:
    - status: Step N of M, goal, type, progress, today
    - task: Step description + user's full request
    - data_section: Previous turn + previous steps + current step results
    - entities: Active entity refs + data (from SessionIdRegistry)
    - conversation: Recent exchanges
    - decision: Output instructions (varies by step type)
    
    Returns dict with keys: status, task, data_section, entities, conversation, decision
    """
    # === STATUS table ===
    progress_info = f"{tool_calls_made} tool calls" if step_type in ("read", "write") else ""
    
    status = f"""## STATUS
| Step | {step_index + 1} of {total_steps} |
| Goal | {step_description} |
| Type | {step_type}{' (no db calls)' if step_type in ('analyze', 'generate') else ''} |
| Progress | {progress_info} |
| Today | {today} |""" if step_type in ("read", "write") else f"""## STATUS
| Step | {step_index + 1} of {total_steps} |
| Goal | {step_description} |
| Type | {step_type} (no db calls) |
| Today | {today} |"""
    
    # === Task section ===
    task = f"""## 1. Task

**Your job this step:** {step_description}

*(User's full request: "{user_message}" — other parts handled by later steps)*"""
    
    # === Data section (prev turn + prev steps + current step) ===
    # Different label for analyze/generate vs read/write
    if step_type in ("analyze", "generate"):
        data_label = "## 2. Data Available"
    else:
        data_label = "## 2. Step History"
    
    data_parts = [data_label, ""]
    
    # Previous turn context (if any)
    if prev_turn_context:
        data_parts.append(prev_turn_context)
    
    # Previous step results this turn
    if prev_step_results:
        data_parts.append(prev_step_results)
    else:
        data_parts.append("*No previous step data.*")
    
    # Current step tool results (read/write only)
    if step_type in ("read", "write") and current_step_results:
        data_parts.append("")
        data_parts.append("**This Step:**")
        data_parts.append(current_step_results)
    
    data_section = "\n".join(data_parts)
    
    # === Entities in Context (ALWAYS included) ===
    entities_warning = ""
    if step_type == "analyze":
        entities_warning = "\n\n**Known refs and labels you may reference. Do NOT assume full record data is available unless it appears in Step Results above.**"
    elif step_type == "generate":
        entities_warning = "\n\n**Use these refs when your generated content references existing entities (e.g., recipe_id in meal plans).**"
    
    entities = f"""## {'3' if step_type in ('analyze', 'generate') else '4'}. Entities in Context
{entities_warning}
{entity_context}"""
    
    # === Conversation context ===
    section_num = "4" if step_type in ("analyze", "generate") else "6"
    conversation = f"""## {section_num}. Context

{conversation_context if conversation_context else '*No additional context.*'}"""
    
    # === Decision prompt (varies by step type) ===
    decision = _build_decision_section(step_type)
    
    return {
        "status": status,
        "task": task,
        "data_section": data_section,
        "entities": entities,
        "conversation": conversation,
        "decision": decision,
    }


def _build_step_type_sections(
    step_type: str,
    subdomain: str,
    step_description: str,
    schema: str | None = None,
    profile_section: str | None = None,
    subdomain_guidance: str | None = None,
    batch_manifest_section: str | None = None,
    artifacts_section: str | None = None,
    archive_section: str | None = None,
    prev_step_note: str | None = None,
    prev_subdomain: str | None = None,
) -> dict[str, str]:
    """
    Build step-type-specific sections.
    
    See docs/prompts/act-prompt-structure.md for the full specification.
    
    These sections vary by step type:
    - read: Schema, filter syntax, CRUD examples
    - write: Schema, FK patterns, batch manifest, artifacts
    - analyze: Analysis guidance, data source rules (no schema)
    - generate: Generation guidance, quality principles, subdomain persona (no schema)
    
    Returns dict with keys that vary by step_type:
    - subdomain_header (all) — from domain.get_act_subdomain_header()
    - guidance (all) — from domain.get_examples()
    - schema (read/write) — database schema
    - batch_manifest (write) — batch progress table
    - artifacts (write) — generated content for saving
    - prev_note (read/write) — note from previous step
    """
    from alfred.domain import get_current_domain
    domain = get_current_domain()
    result = {}

    # === Subdomain header (persona) ===
    subdomain_content = domain.get_act_subdomain_header(subdomain, step_type)
    if subdomain_content:
        result["subdomain_header"] = subdomain_content

    # === Step-type guidance/examples ===
    guidance = domain.get_examples(
        subdomain=subdomain,
        step_type=step_type,
        step_description=step_description,
        prev_subdomain=prev_subdomain,
    )
    if guidance:
        result["guidance"] = guidance
    
    # === Schema (read/write/generate) ===
    if step_type in ("read", "write", "generate") and schema:
        result["schema"] = f"""## 3. Schema ({subdomain})

{schema}"""
    
    # === Batch manifest (write only) ===
    if step_type == "write" and batch_manifest_section:
        result["batch_manifest"] = batch_manifest_section
    
    # === Artifacts (write/generate/analyze) ===
    # V9: All step types that reason about generated content need full data
    if step_type in ("write", "generate", "analyze") and artifacts_section:
        result["artifacts"] = f"""## 5. Generated Data

{artifacts_section}"""
    
    # === Previous step note (read/write) ===
    if step_type in ("read", "write") and prev_step_note:
        result["prev_note"] = f"""## Previous Step Note

{prev_step_note}"""
    
    # === Archive section (analyze/generate) ===
    if step_type in ("analyze", "generate") and archive_section:
        # Append to guidance or create new section
        if "guidance" in result:
            result["guidance"] += f"\n\n{archive_section}"
        else:
            result["guidance"] = archive_section
    
    return result


def _build_decision_section(step_type: str) -> str:
    """
    Build the decision prompt for a step type.
    
    See docs/prompts/act-prompt-structure.md for the full specification.
    
    Different step types have different valid actions:
    - analyze: step_complete only (no db calls)
    - generate: step_complete only (no db calls)
    - read/write: tool_call or step_complete
    """
    if step_type == "analyze":
        return """## DECISION

Analyze the data above and complete the step:
`{"action": "step_complete", "result_summary": "Analysis: ...", "data": {"key": "value"}}`"""
    
    elif step_type == "generate":
        return """## DECISION

Generate the requested content and complete the step:
`{"action": "step_complete", "result_summary": "Generated: ...", "data": {"your_content": "here"}}`"""
    
    else:  # read/write
        return """## DECISION

What's next?
- Step done? → `{"action": "step_complete", "result_summary": "...", "data": {...}, "note_for_next_step": "..."}`
- Need data? → `{"action": "tool_call", "tool": "db_read", "params": {"table": "...", "filters": [...], "limit": N}}`
- Need to create? → `{"action": "tool_call", "tool": "db_create", "params": {"table": "...", "data": {...}}}`

**IMPORTANT:** When completing, include a brief note with IDs or key info the next step might need."""




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
    from alfred.domain import get_current_domain
    domain = get_current_domain()

    # === SYSTEM PROMPT: Load Act's prompts, same as Act ===
    prompts_dir = Path(__file__).parent / "templates" / "act"
    
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
    subdomain_intro = domain.get_act_subdomain_header(subdomain, "read")
    subdomain_persona = domain.get_persona(subdomain, "read")
    
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



