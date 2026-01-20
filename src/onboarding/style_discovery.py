"""
Style Discovery - LLM-Guided Preference Extraction.

This module handles Phase 3 of onboarding: discovering user's preferred
output styles for recipes, meal plans, and tasks through conversational
sample generation and feedback synthesis.

The pattern for each domain:
1. LLM generates 2-3 samples in different styles (using user's pantry/cuisines)
2. User picks favorite OR gives natural language feedback
3. LLM synthesizes feedback into subdomain_guidance string

This creates durable personalization that shapes all future Alfred outputs.
"""

from pydantic import BaseModel, Field
from typing import Literal
import logging

from alfred.llm.client import call_llm

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================

class RecipeSample(BaseModel):
    """A generated recipe sample for style discovery."""
    id: str = Field(description="Unique ID like 'quick', 'full', 'chef'")
    style_name: str = Field(description="Human-readable style name")
    style_tags: list[str] = Field(default_factory=list, description="Tags like 'concise', 'detailed', 'chef_tips'")
    recipe_text: str = Field(description="The actual recipe content")
    why_this_style: str = Field(description="Brief explanation of why user might like this")


class RecipeStyleProposal(BaseModel):
    """LLM output for recipe style proposal."""
    dish_name: str = Field(description="Name of the dish being demonstrated")
    intro_message: str = Field(description="Friendly intro like 'Here are three ways I could write recipes...'")
    samples: list[RecipeSample] = Field(description="2-3 recipe samples in different styles")


class MealPlanSample(BaseModel):
    """A generated meal plan sample for style discovery."""
    id: str = Field(description="Unique ID like 'minimal', 'practical', 'detailed'")
    style_name: str = Field(description="Human-readable style name")
    plan_text: str = Field(description="The actual meal plan content")
    why_this_style: str = Field(description="Brief explanation of why user might like this")


class MealPlanStyleProposal(BaseModel):
    """LLM output for meal plan style proposal."""
    intro_message: str = Field(description="Friendly intro")
    samples: list[MealPlanSample] = Field(description="2-3 meal plan samples")


class TaskSample(BaseModel):
    """A generated task reminder sample for style discovery."""
    id: str = Field(description="Unique ID like 'brief', 'timed', 'linked'")
    style_name: str = Field(description="Human-readable style name")
    task_text: str = Field(description="Example task reminder")
    why_this_style: str = Field(description="Brief explanation")


class TaskStyleProposal(BaseModel):
    """LLM output for task style proposal."""
    intro_message: str = Field(description="Friendly intro")
    samples: list[TaskSample] = Field(description="2-3 task samples")


class StyleFeedbackSynthesis(BaseModel):
    """LLM output after user provides feedback."""
    guidance_summary: str = Field(
        description="1-2 sentence guidance for Alfred, e.g., 'Prefers concise recipes with chef tips and timing cues.'"
    )
    acknowledgment: str = Field(
        description="Short acknowledgment to show user, e.g., 'Got it — concise with technique notes.'"
    )
    selected_style_id: str | None = Field(
        default=None,
        description="ID of the style they picked (if they picked one)"
    )


# =============================================================================
# Prompts
# =============================================================================

RECIPE_STYLE_PROMPT = """You are helping a new Alfred user discover their preferred recipe style.

**User Context:**
- Skill level: {skill_level}
- Household: {household_size} people
- Pantry includes: {pantry_items}
- Likes cuisines: {cuisines}
- Dietary: {dietary}
- Equipment: {equipment}

Generate 3 recipe samples for the SAME dish (choose something that uses their pantry items and fits their cuisines).
Each sample should demonstrate a DIFFERENT style:

1. **Quick & Clean** (id: "quick")
   - Minimal steps, just essentials
   - Assumes competence
   - Bullet points, no fluff
   
2. **Full Instructions** (id: "full")
   - Clear step-by-step
   - Timing included
   - No assumptions about technique
   
3. **Chef Mode** (id: "chef")
   - Technique tips and "why" explanations
   - Upgrades and hacks
   - What to do with leftovers

For each, explain briefly (1 sentence) why this style might suit them based on their skill level.

Make the recipes feel PERSONAL — use their actual ingredients and cuisines.
Keep each recipe sample under 200 words."""


MEAL_PLAN_STYLE_PROMPT = """You are helping a new Alfred user discover their preferred meal planning style.

**User Context:**
- Household: {household_size} people
- Skill level: {skill_level}
- Cuisines: {cuisines}
- Pantry has: {pantry_items}
- Dietary: {dietary}

Generate 3 example MEAL PLANS for the same week, each in a different style:

1. **Minimal** (id: "minimal")
   - Just meals and days
   - No logistics
   - User decides the details
   
2. **Practical** (id: "practical")
   - Cooking days marked
   - Batch notes and leftover flow
   - Shopping list summary
   
3. **Detailed** (id: "detailed")
   - Full calendar with prep tasks
   - Thaw reminders
   - Complete shopping list

Use their actual pantry items and cuisines where possible.
Explain why each style might suit them.
Keep each plan sample under 150 words."""


TASK_STYLE_PROMPT = """You are helping a new Alfred user discover their preferred task reminder style.

**User Context:**
- Skill level: {skill_level}
- Household: {household_size} people

Generate 3 example TASK REMINDERS for common cooking prep, each in a different style:

1. **Brief** (id: "brief")
   - Just the task
   - Example: "Thaw chicken"
   
2. **Timed** (id: "timed")
   - Task with timing/deadline
   - Example: "Thaw chicken (move to fridge by 6pm)"
   
3. **Linked** (id: "linked")
   - Task linked to meal context
   - Example: "Thaw chicken for tomorrow's stir-fry — move to fridge by 6pm"

Explain why each style might suit them.
Keep examples brief and practical."""


SYNTHESIS_PROMPT = """The user just completed {domain} style selection.

**Samples shown:**
{samples_shown}

**User's response:**
Selection: {selection}
Feedback: "{feedback}"

Synthesize their preference into:
1. A brief guidance summary (1-2 sentences) that Alfred can use to shape all future {domain}
2. A short acknowledgment to show the user (friendly, confirms understanding)
3. The selected_style_id if they picked one of the samples

Be specific and actionable in the guidance. Examples:
- "Prefers concise recipes with chef tips. Skip obvious steps, include timing cues."
- "Wants practical meal plans with batch cooking notes and shopping lists."
- "Likes task reminders linked to specific meals with timing."

If they gave feedback instead of picking, incorporate their specific requests."""


# =============================================================================
# Generation Functions
# =============================================================================

async def generate_recipe_style_samples(
    payload_draft: dict,
) -> RecipeStyleProposal:
    """
    Generate recipe samples for style discovery.
    
    Uses user's pantry + preferences to make it personal.
    """
    preferences = payload_draft.get("preferences", {})
    pantry = payload_draft.get("initial_inventory", [])
    cuisines = payload_draft.get("cuisine_preferences", [])
    
    # Format pantry items (just names)
    pantry_names = [item.get("name", "") for item in pantry[:10] if item.get("name")]
    
    prompt = RECIPE_STYLE_PROMPT.format(
        skill_level=preferences.get("cooking_skill_level", "intermediate"),
        household_size=preferences.get("household_size", 2),
        pantry_items=", ".join(pantry_names) if pantry_names else "standard pantry staples",
        cuisines=", ".join(cuisines) if cuisines else "various",
        dietary=", ".join(preferences.get("dietary_restrictions", [])) or "none",
        equipment=", ".join(preferences.get("available_equipment", [])) or "standard kitchen",
    )
    
    return await call_llm(
        response_model=RecipeStyleProposal,
        system_prompt=prompt,
        user_prompt="Generate 3 recipe style samples for me to choose from.",
        complexity="medium",
    )


async def generate_meal_plan_style_samples(
    payload_draft: dict,
) -> MealPlanStyleProposal:
    """
    Generate meal plan samples for style discovery.
    """
    preferences = payload_draft.get("preferences", {})
    pantry = payload_draft.get("initial_inventory", [])
    cuisines = payload_draft.get("cuisine_preferences", [])
    
    pantry_names = [item.get("name", "") for item in pantry[:8] if item.get("name")]
    
    prompt = MEAL_PLAN_STYLE_PROMPT.format(
        household_size=preferences.get("household_size", 2),
        skill_level=preferences.get("cooking_skill_level", "intermediate"),
        cuisines=", ".join(cuisines) if cuisines else "various",
        pantry_items=", ".join(pantry_names) if pantry_names else "standard pantry",
        dietary=", ".join(preferences.get("dietary_restrictions", [])) or "none",
    )
    
    return await call_llm(
        response_model=MealPlanStyleProposal,
        system_prompt=prompt,
        user_prompt="Generate 3 meal plan style samples for me to choose from.",
        complexity="medium",
    )


async def generate_task_style_samples(
    payload_draft: dict,
) -> TaskStyleProposal:
    """
    Generate task reminder samples for style discovery.
    """
    preferences = payload_draft.get("preferences", {})
    
    prompt = TASK_STYLE_PROMPT.format(
        skill_level=preferences.get("cooking_skill_level", "intermediate"),
        household_size=preferences.get("household_size", 2),
    )
    
    return await call_llm(
        response_model=TaskStyleProposal,
        system_prompt=prompt,
        user_prompt="Generate 3 task reminder style samples for me to choose from.",
        complexity="low",
    )


# =============================================================================
# Synthesis Function
# =============================================================================

def _format_samples_for_synthesis(samples: list[dict]) -> str:
    """Format samples shown for the synthesis prompt."""
    lines = []
    for sample in samples:
        style_name = sample.get("style_name", sample.get("id", "Unknown"))
        text = sample.get("recipe_text") or sample.get("plan_text") or sample.get("task_text", "")
        # Truncate long text
        if len(text) > 300:
            text = text[:300] + "..."
        lines.append(f"**{style_name}:**\n{text}\n")
    return "\n".join(lines)


async def synthesize_style_feedback(
    domain: Literal["recipes", "meal_plans", "tasks"],
    samples_shown: list[dict],
    user_selection: str | None,
    user_feedback: str,
) -> StyleFeedbackSynthesis:
    """
    Synthesize user feedback into guidance + acknowledgment.
    
    This is the LLM call that converts the interaction into durable preference.
    
    Args:
        domain: Which domain (recipes, meal_plans, tasks)
        samples_shown: The samples that were shown to user
        user_selection: ID of selected sample (if they picked one)
        user_feedback: Natural language feedback (if any)
    
    Returns:
        StyleFeedbackSynthesis with guidance_summary and acknowledgment
    """
    samples_text = _format_samples_for_synthesis(samples_shown)
    
    prompt = SYNTHESIS_PROMPT.format(
        domain=domain,
        samples_shown=samples_text,
        selection=user_selection or "None - gave feedback instead",
        feedback=user_feedback or "(no additional feedback)",
    )
    
    return await call_llm(
        response_model=StyleFeedbackSynthesis,
        system_prompt=prompt,
        user_prompt=f"Synthesize the user's {domain} style preference.",
        complexity="low",
    )


# =============================================================================
# Habits Extraction
# =============================================================================

class HabitsExtraction(BaseModel):
    """Structured extraction from habits conversation."""
    
    # Cooking habits
    cooking_frequency: str | None = Field(default=None, description="e.g., '2-3x/week', 'daily', 'weekends only'")
    batch_cooking: bool | None = Field(default=None, description="Do they batch cook?")
    cooking_days: list[str] | None = Field(default=None, description="e.g., ['sunday', 'wednesday']")
    
    # Leftover preferences
    leftover_tolerance_days: int | None = Field(default=None, description="How many days is okay?")
    
    # Shopping habits
    shopping_frequency: str | None = Field(default=None, description="e.g., 'weekly', '2x/week'")
    
    # Narrative summaries for subdomain_guidance
    meal_plans_summary: str = Field(
        default="",
        description="Summary for meal_plans subdomain guidance (~50 words)"
    )
    shopping_summary: str = Field(
        default="",
        description="Summary for shopping subdomain guidance (~50 words)"
    )
    inventory_summary: str = Field(
        default="",
        description="Summary for inventory subdomain guidance (~50 words)"
    )


HABITS_PROMPT = """You are helping onboard a new user to Alfred, a cooking assistant.

Based on their response, extract cooking, shopping, and inventory preferences.

**User's household:** {household_size} people
**Dietary restrictions:** {dietary_restrictions}
**Skill level:** {skill_level}

**User said:**
"{user_response}"

Extract concrete details where mentioned. If something wasn't mentioned, leave it null.

Write THREE brief summaries (~30-50 words each):
1. meal_plans_summary: Their cooking rhythm and leftover preferences
2. shopping_summary: How/when they shop
3. inventory_summary: How strictly they track inventory, what staples to assume

Be specific and actionable. These summaries will guide Alfred's behavior.

If the user didn't mention something, make reasonable assumptions based on their household size and skill level, but keep summaries brief."""


async def extract_habits(
    user_response: str,
    constraints: dict,
) -> HabitsExtraction:
    """
    Extract habits from user's free-form response.
    
    This single question covers cooking, shopping, and inventory habits.
    """
    prompt = HABITS_PROMPT.format(
        household_size=constraints.get("household_size", 2),
        dietary_restrictions=", ".join(constraints.get("dietary_restrictions", [])) or "None",
        skill_level=constraints.get("cooking_skill_level", "intermediate"),
        user_response=user_response,
    )
    
    return await call_llm(
        response_model=HabitsExtraction,
        system_prompt=prompt,
        user_prompt=user_response,
        complexity="low",
    )
