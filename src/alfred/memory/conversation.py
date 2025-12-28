"""
Alfred V2 - Conversation Memory & Entity Tracking.

Handles:
- Entity extraction from step results
- Context formatting for different nodes (condensed vs full)
- Token estimation for context management
- Step retrieval for Act node
"""

import json
from datetime import datetime
from typing import Any

from alfred.graph.state import (
    ACT_CONTEXT_THRESHOLD,
    FULL_DETAIL_STEPS,
    FULL_DETAIL_TURNS,
    ROUTER_CONTEXT_THRESHOLD,
    AlfredState,
    ConversationContext,
    ConversationTurn,
    EntityRef,
    StepSummary,
)


# =============================================================================
# Token Estimation
# =============================================================================


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate (~4 chars per token for English).
    
    This is a fast heuristic. For precise counting, use tiktoken.
    """
    return len(text) // 4


# =============================================================================
# Assistant Message Summarization (for conversation context)
# =============================================================================

# Threshold for summarizing assistant messages (in characters)
SUMMARIZE_THRESHOLD = 500  # ~125 tokens


def _summarize_assistant_message(message: str) -> str:
    """
    Summarize long assistant messages for conversation context.
    
    Intent: Conversation history conveys WHAT happened, not full data.
    Tool results and step results are the source of truth for specifics.
    
    Patterns detected:
    - Recipe content (ingredients, instructions)
    - Long lists (inventory, shopping items)
    - Generated content
    """
    if len(message) < SUMMARIZE_THRESHOLD:
        return message
    
    lines = message.strip().split("\n")
    
    # Detect recipe content patterns
    if _looks_like_recipe_content(message):
        return _summarize_recipe_content(message)
    
    # Detect long list patterns  
    if _looks_like_item_list(message):
        return _summarize_item_list(message)
    
    # Default: Keep first ~300 chars + note
    if len(message) > 500:
        truncated = message[:400].rsplit(" ", 1)[0]
        return f"{truncated}... [content continues in step results]"
    
    return message


def _looks_like_recipe_content(message: str) -> bool:
    """Detect if message contains recipe-like content."""
    recipe_markers = [
        "**Ingredients:",
        "- Ingredients:",
        "Instructions:",
        "Serve with",
        "tbsp butter",
        "tsp ",
        "cup ",
        "cloves",
        "Preheat",
        "Simmer",
    ]
    marker_count = sum(1 for m in recipe_markers if m.lower() in message.lower())
    return marker_count >= 3


def _summarize_recipe_content(message: str) -> str:
    """Extract recipe names and provide summary."""
    lines = message.split("\n")
    
    # Find recipe names (usually bold headers)
    recipe_names = []
    for line in lines:
        # Look for patterns like "1. **Recipe Name**" or "**Recipe Name**"
        if "**" in line:
            # Extract text between **
            import re
            matches = re.findall(r'\*\*([^*]+)\*\*', line)
            for match in matches:
                # Filter out section headers like "Ingredients:" 
                if not any(x in match.lower() for x in ["ingredient", "instruction", "serve"]):
                    if len(match) > 5:  # Skip short matches
                        recipe_names.append(match.strip())
    
    if recipe_names:
        names_str = ", ".join(recipe_names[:5])  # Max 5 recipes
        return f"Generated recipe(s): {names_str}. [Content archived for later retrieval]"
    
    return "Generated recipe content. [Content archived for later retrieval]"


def _looks_like_item_list(message: str) -> bool:
    """Detect if message is a long list of items."""
    # Count list markers
    list_markers = message.count("\n- ") + message.count("\n* ")
    return list_markers >= 5


def _summarize_item_list(message: str) -> str:
    """Summarize a list by showing count and first few items."""
    lines = message.split("\n")
    
    # Find intro text (before the list)
    intro_lines = []
    list_items = []
    in_list = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            in_list = True
            # Extract item name (first part before any colon/quantity)
            item = stripped[2:].split(":")[0].split("(")[0].strip()
            if item:
                list_items.append(item)
        elif not in_list and stripped:
            intro_lines.append(stripped)
    
    if list_items:
        count = len(list_items)
        preview = ", ".join(list_items[:3])
        more = f" +{count - 3} more" if count > 3 else ""
        intro = " ".join(intro_lines[:1]) if intro_lines else "List"
        return f"{intro} ({count} items: {preview}{more})"
    
    return message[:300] + "..."


def estimate_context_tokens(context: ConversationContext) -> int:
    """Estimate total tokens in a conversation context."""
    total = 0
    
    # Engagement summary
    total += estimate_tokens(context.get("engagement_summary", ""))
    
    # Recent turns (full text)
    for turn in context.get("recent_turns", []):
        total += estimate_tokens(str(turn))
    
    # History summary
    total += estimate_tokens(context.get("history_summary", ""))
    
    # Step summaries
    for summary in context.get("step_summaries", []):
        total += estimate_tokens(str(summary))
    
    # Active entities (small)
    total += estimate_tokens(str(context.get("active_entities", {})))
    
    return total


# =============================================================================
# Entity Extraction
# =============================================================================

# Map table names to entity types
TABLE_TO_ENTITY_TYPE = {
    "inventory": "inventory_item",
    "ingredients": "ingredient",
    "recipes": "recipe",
    "recipe_ingredients": "recipe_ingredient",
    "shopping_list": "shopping_item",
    "meal_plans": "meal_plan",
    "preferences": "preference",
}


def extract_entities_from_result(
    result: Any,
    table: str | None = None,
    step_index: int | None = None,
    source: str = "db_lookup",
) -> list[EntityRef]:
    """
    Extract EntityRefs from a tool result.
    
    Args:
        result: Tool result (usually list of dicts or single dict)
        table: Table name (for entity type inference)
        step_index: Which step this came from
        source: How this entity was obtained
        
    Returns:
        List of EntityRef objects
    """
    entities = []
    entity_type = TABLE_TO_ENTITY_TYPE.get(table or "", "unknown")
    
    if isinstance(result, dict):
        # Check if it's a direct record with ID
        if "id" in result:
            entities.append(EntityRef(
                type=entity_type,
                id=str(result["id"]),
                label=result.get("name", result.get("id", "unnamed")),
                source=source,
                step_index=step_index,
            ))
        else:
            # Check if it's a wrapper dict like {"salad_recipes": [...], "ingredients": [...]}
            # Recursively extract from any list values
            for key, value in result.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "id" in item:
                            # Try to infer entity type from the key
                            inferred_type = TABLE_TO_ENTITY_TYPE.get(key, entity_type)
                            entities.append(EntityRef(
                                type=inferred_type,
                                id=str(item["id"]),
                                label=item.get("name", item.get("id", "unnamed")),
                                source=source,
                                step_index=step_index,
                            ))
    
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and "id" in item:
                entities.append(EntityRef(
                    type=entity_type,
                    id=str(item["id"]),
                    label=item.get("name", item.get("id", "unnamed")),
                    source=source,
                    step_index=step_index,
                ))
    
    return entities


def extract_entities_from_step_results(
    step_results: dict[int, Any],
) -> dict[str, EntityRef]:
    """
    Extract all entities from step results.
    
    Returns dict keyed by entity ID for deduplication.
    """
    all_entities: dict[str, EntityRef] = {}
    
    for step_idx, result in step_results.items():
        # Handle tuple format: [(tool_name, table, result), ...] or [(tool_name, result), ...]
        if isinstance(result, list) and result and isinstance(result[0], tuple):
            for item in result:
                # Handle both (tool, table, result) and (tool, result) formats
                if len(item) == 3:
                    tool_name, table, tool_result = item
                else:
                    tool_name, tool_result = item
                    table = _infer_table_from_result(tool_result)
                entities = extract_entities_from_result(
                    tool_result, table, step_idx, "db_lookup"
                )
                for entity in entities:
                    all_entities[entity.id] = entity
        else:
            # Direct result
            table = _infer_table_from_result(result)
            entities = extract_entities_from_result(
                result, table, step_idx, "db_lookup"
            )
            for entity in entities:
                all_entities[entity.id] = entity
    
    return all_entities


def _infer_table_from_result(result: Any) -> str | None:
    """Try to infer table name from result structure."""
    if isinstance(result, list) and result:
        sample = result[0] if isinstance(result[0], dict) else None
    elif isinstance(result, dict):
        sample = result
    else:
        return None
    
    if not sample:
        return None
    
    # Heuristics based on field names
    if "recipe_id" in sample and "ingredient_id" in sample:
        return "recipe_ingredients"
    if "cuisine" in sample or "instructions" in sample:
        return "recipes"
    if "location" in sample and "expiry_date" in sample:
        return "inventory"
    if "is_purchased" in sample:
        return "shopping_list"
    if "meal_type" in sample and "date" in sample:
        return "meal_plans"
    if "dietary_restrictions" in sample:
        return "preferences"
    if "aliases" in sample or "category" in sample:
        return "ingredients"
    
    return None


def update_active_entities(
    active: dict[str, dict],
    new_entities: list[EntityRef],
) -> dict[str, dict]:
    """
    Update active entities with new ones.
    
    Keeps the most recent entity of each type for "that recipe" resolution.
    """
    updated = active.copy()
    
    for entity in new_entities:
        # Store by type - most recent wins
        updated[entity.type] = entity.model_dump()
    
    return updated


# =============================================================================
# Context Formatting
# =============================================================================


def format_condensed_context(
    conversation: ConversationContext,
    max_tokens: int = ROUTER_CONTEXT_THRESHOLD,
) -> str:
    """
    Format condensed context for Router and Think.
    
    Prioritizes:
    1. Active entities (for reference resolution)
    2. Engagement summary
    3. Last 1-2 turns (condensed)
    4. History summary (if space)
    """
    parts = []
    tokens_used = 0
    
    # 1. Engagement summary (always include, small)
    engagement = conversation.get("engagement_summary", "")
    if engagement:
        section = f"**Current session**: {engagement}"
        parts.append(section)
        tokens_used += estimate_tokens(section)
    
    # 2. Active entities (critical for reference resolution)
    active = conversation.get("active_entities", {})
    if active:
        entity_lines = ["**Recent items**:"]
        for entity_type, entity_data in active.items():
            label = entity_data.get("label", "unknown")
            entity_lines.append(f"  - {entity_type}: {label}")
        section = "\n".join(entity_lines)
        parts.append(section)
        tokens_used += estimate_tokens(section)
    
    # 3. Recent turns (last 1-2, condensed format)
    recent = conversation.get("recent_turns", [])
    if recent:
        # Take last 2 max
        for turn in recent[-2:]:
            user_msg = turn.get("user", "")[:300]  # Truncate long user messages
            # Use LLM-generated summary if available, else fall back to regex-based
            asst_msg = turn.get("assistant_summary") or _summarize_assistant_message(turn.get("assistant", ""))
            section = f"User: {user_msg}\nAlfred: {asst_msg}"
            
            if tokens_used + estimate_tokens(section) < max_tokens:
                parts.append(section)
                tokens_used += estimate_tokens(section)
            else:
                break
    
    # 4. History summary (if space remains)
    history = conversation.get("history_summary", "")
    if history and tokens_used + estimate_tokens(history) < max_tokens:
        parts.append(f"**Earlier**: {history}")
    
    if not parts:
        return "*No conversation context yet.*"
    
    return "\n\n".join(parts)


def format_full_context(
    conversation: ConversationContext,
    step_results: dict[int, Any],
    current_step_index: int,
    max_tokens: int = ACT_CONTEXT_THRESHOLD,
) -> str:
    """
    Format full context for Act node.
    
    Includes:
    1. Last FULL_DETAIL_TURNS conversation turns (full text)
    2. Last FULL_DETAIL_STEPS step results (full data)
    3. Older step summaries (for reference)
    4. Active entities
    5. Engagement summary
    """
    parts = []
    tokens_used = 0
    
    # 1. Engagement summary
    engagement = conversation.get("engagement_summary", "")
    if engagement:
        section = f"### Session Context\n{engagement}"
        parts.append(section)
        tokens_used += estimate_tokens(section)
    
    # 2. Active entities
    active = conversation.get("active_entities", {})
    if active:
        entity_lines = ["### Active Entities (for reference resolution)"]
        for entity_type, entity_data in active.items():
            label = entity_data.get("label", "unknown")
            entity_id = entity_data.get("id", "?")
            entity_lines.append(f"- **{entity_type}**: {label} (id: `{entity_id}`)")
        section = "\n".join(entity_lines)
        parts.append(section)
        tokens_used += estimate_tokens(section)
    
    # 3. Recent conversation turns (use LLM-generated summaries when available)
    recent = conversation.get("recent_turns", [])
    if recent:
        turn_lines = ["### Recent Conversation"]
        for turn in recent[-FULL_DETAIL_TURNS:]:
            user_msg = turn.get("user", "")
            # Use LLM-generated summary if available, else fall back to regex-based
            asst_msg = turn.get("assistant_summary") or _summarize_assistant_message(turn.get("assistant", ""))
            # User messages: keep full (they convey intent)
            turn_lines.append(f"**User**: {user_msg}")
            # Assistant messages: use summary (data is in step results)
            turn_lines.append(f"**Alfred**: {asst_msg}")
            turn_lines.append("")
        section = "\n".join(turn_lines)
        
        if tokens_used + estimate_tokens(section) < max_tokens:
            parts.append(section)
            tokens_used += estimate_tokens(section)
    
    # 4. History summary (older turns)
    history = conversation.get("history_summary", "")
    if history:
        section = f"### Earlier in Conversation\n{history}"
        if tokens_used + estimate_tokens(section) < max_tokens:
            parts.append(section)
            tokens_used += estimate_tokens(section)
    
    # 5. Older step summaries (before FULL_DETAIL_STEPS)
    step_summaries = conversation.get("step_summaries", [])
    if step_summaries:
        summary_lines = ["### Previous Steps (summaries)"]
        for summary in step_summaries:
            idx = summary.get("step_index", "?")
            desc = summary.get("description", "")
            outcome = summary.get("outcome", "")
            count = summary.get("record_count", 0)
            summary_lines.append(f"- Step {idx + 1}: {desc} → {outcome} ({count} records)")
        section = "\n".join(summary_lines)
        
        if tokens_used + estimate_tokens(section) < max_tokens:
            parts.append(section)
            tokens_used += estimate_tokens(section)
    
    if not parts:
        return "*No conversation context yet.*"
    
    return "\n\n".join(parts)


def format_step_results_for_context(
    step_results: dict[int, Any],
    current_step_index: int,
) -> tuple[str, list[dict]]:
    """
    Format step results, keeping last FULL_DETAIL_STEPS in full,
    summarizing older ones.
    
    Returns:
        Tuple of (formatted_recent_steps, list_of_summaries_for_older)
    """
    if not step_results:
        return "*No previous steps completed.*", []
    
    recent_lines = ["### Recent Step Results"]
    summaries = []
    
    for idx in sorted(step_results.keys()):
        result = step_results[idx]
        step_num = idx + 1
        
        # Check if this is a recent step (full detail) or older (summary)
        if idx >= current_step_index - FULL_DETAIL_STEPS:
            # Full detail
            recent_lines.append(f"\n**Step {step_num}**:")
            recent_lines.append(_format_result_full(result))
        else:
            # Create summary for older step
            summary = StepSummary(
                step_index=idx,
                description=f"Step {step_num}",
                subdomain="unknown",
                outcome=_summarize_result(result),
                entity_ids=_extract_ids(result),
                record_count=_count_records(result),
            )
            summaries.append(summary.model_dump())
    
    return "\n".join(recent_lines), summaries


def _format_result_full(result: Any) -> str:
    """Format a result in full detail."""
    if isinstance(result, list) and result and isinstance(result[0], tuple):
        # Tool result format - handle both 2-tuple and 3-tuple
        lines = []
        for item in result:
            if len(item) == 3:
                tool_name, _table, tool_result = item
            else:
                tool_name, tool_result = item
            lines.append(f"  - `{tool_name}`: {_describe_tool_result(tool_result)}")
        return "\n".join(lines)
    elif isinstance(result, list):
        if len(result) == 0:
            return "  0 records"
        else:
            return f"  {len(result)} records: {json.dumps(result, default=str)}"
    elif isinstance(result, dict):
        return f"  {json.dumps(result, default=str)}"
    else:
        return f"  {result}"


def _describe_tool_result(result: Any) -> str:
    """Describe a tool result."""
    if isinstance(result, list):
        if len(result) == 0:
            return "0 records"
        return f"{len(result)} records: {json.dumps(result, default=str)}"
    elif isinstance(result, dict):
        return json.dumps(result, default=str)
    return str(result)


def _summarize_result(result: Any) -> str:
    """Create one-line summary of a result."""
    if isinstance(result, list):
        if len(result) == 0:
            return "No records found"
        return f"Found {len(result)} records"
    elif isinstance(result, dict):
        return f"Processed 1 record"
    return "Completed"


def _extract_ids(result: Any) -> list[str]:
    """Extract IDs from a result for retrieval."""
    ids = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and "id" in item:
                ids.append(str(item["id"]))
            elif isinstance(item, tuple) and len(item) == 2:
                _, tool_result = item
                ids.extend(_extract_ids(tool_result))
    elif isinstance(result, dict) and "id" in result:
        ids.append(str(result["id"]))
    return ids


def _count_records(result: Any) -> int:
    """Count records in a result."""
    if isinstance(result, list):
        if result and isinstance(result[0], tuple):
            # Handle both (tool, result) and (tool, table, result) formats
            return sum(_count_records(item[-1]) for item in result)
        return len(result)
    elif isinstance(result, dict):
        return 1
    return 0


# =============================================================================
# Step Retrieval (for Act to fetch older steps)
# =============================================================================


def get_step_data(
    step_results: dict[int, Any],
    step_index: int,
) -> Any:
    """
    Retrieve full data for a specific step.
    
    This is called when Act needs data from an older step
    (beyond FULL_DETAIL_STEPS).
    """
    return step_results.get(step_index)


def get_entity_data(
    all_entities: dict[str, dict],
    entity_id: str,
) -> dict | None:
    """
    Retrieve entity data by ID.
    
    Returns EntityRef dict or None if not found.
    """
    return all_entities.get(entity_id)


# =============================================================================
# Conversation Management
# =============================================================================


def create_conversation_turn(
    user_message: str,
    assistant_response: str,
    assistant_summary: str | None = None,
    routing: dict[str, Any] | None = None,
    entities: list[EntityRef] | None = None,
) -> dict:
    """Create a new conversation turn.
    
    Args:
        user_message: The user's message
        assistant_response: Full assistant response (for Reply/display)
        assistant_summary: LLM-condensed summary (for context in Act/Think)
        routing: Router decision for this turn
        entities: Entities mentioned in this turn
    """
    return ConversationTurn(
        user=user_message,
        assistant=assistant_response,
        assistant_summary=assistant_summary,
        timestamp=datetime.utcnow().isoformat(),
        routing=routing,
        entities_mentioned=[e.id for e in (entities or [])],
    ).model_dump()


def add_turn_to_context(
    conversation: ConversationContext,
    turn: dict,
) -> ConversationContext:
    """
    Add a turn to conversation context.
    
    If we exceed FULL_DETAIL_TURNS, the oldest gets summarized.
    """
    updated = dict(conversation)
    recent = list(updated.get("recent_turns", []))
    
    recent.append(turn)
    
    # Keep only last FULL_DETAIL_TURNS in full
    # Note: Actual summarization happens in the Summarize node
    updated["recent_turns"] = recent
    
    return updated


def initialize_conversation() -> ConversationContext:
    """Create an empty conversation context."""
    return {
        "engagement_summary": "",
        "recent_turns": [],
        "history_summary": "",
        "step_summaries": [],
        "active_entities": {},
        "all_entities": {},
    }

