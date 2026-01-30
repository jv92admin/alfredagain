"""
Style Interview - Structured Preference Discovery.

This module handles the interview phase of onboarding where we discover user
preferences through a mix of labeled chip selections (quick-tap) and focused
text questions, then synthesize into structured subdomain_guidance strings.

## How Alfred Uses subdomain_guidance

Alfred is a multi-agent cooking assistant with 5 subdomains:
- recipes: How to write/present recipes
- meal_plans: How to structure meal plans
- tasks: How to format prep tasks and reminders
- shopping: How to organize shopping lists
- inventory: How to track pantry items

Each subdomain has a `subdomain_guidance` string (~50-200 tokens) that shapes
ALL outputs for that domain.

## Interview Flow

1. Page 1: Recipes & Cooking Style (4 chips + 1 text) → recipes guidance
2. Page 2: Shopping & Ingredients (3 chips + 1 text) → shopping, inventory guidance
3. Page 3: Meal Planning & Prep (3 chips + 1 text) → meal_plans, tasks guidance
4. Page 4: Catch-all (0-3 LLM-generated questions) → fill gaps

Pages 1-3 are STATIC (no LLM call). Page 4 uses LLM to generate follow-ups.
Finally: LLM synthesizes all answers → subdomain_guidance strings.
"""

from pydantic import BaseModel, Field
from typing import Literal
import logging

from alfred.llm.client import call_llm

logger = logging.getLogger(__name__)


# =============================================================================
# Static Page Definitions
# =============================================================================

STATIC_PAGES = {
    "page_1": {
        "title": "Recipes & Cooking Style",
        "subtitle": "Alfred writes and catalogs recipes tailored to how you actually cook — from quick weeknight dinners to weekend projects.",
        "image": "/onboarding/onboarding-recipes.svg",
        "maps_to": ["recipes"],
        "questions": [
            {
                "id": "recipe_competence",
                "type": "chips",
                "multi": False,
                "question": "How much should Alfred assume you know?",
                "options": [
                    {"label": "Assume I know the basics", "value": "assume_basics"},
                    {"label": "Explain key techniques", "value": "explain_techniques"},
                    {"label": "Walk me through everything", "value": "walk_through"},
                ],
            },
            {
                "id": "timing_preference",
                "type": "chips",
                "multi": False,
                "question": "How do you prefer timing info?",
                "options": [
                    {"label": "Visual cues & intuition", "value": "visual_cues"},
                    {"label": "Times + visual cues", "value": "times_and_cues"},
                    {"label": "Exact temps & times", "value": "exact_times"},
                ],
            },
            {
                "id": "weeknight_time",
                "type": "chips",
                "multi": False,
                "question": "How much time do you usually have for weeknight cooking?",
                "options": [
                    {"label": "Under 20 min", "value": "under_20"},
                    {"label": "20-40 min", "value": "20_to_40"},
                    {"label": "40-60 min", "value": "40_to_60"},
                    {"label": "No rush", "value": "no_rush"},
                ],
            },
            {
                "id": "recipe_extras",
                "type": "chips",
                "multi": True,
                "question": "What extras are useful to you?",
                "options": [
                    {"label": "Substitutions when I'm missing something", "value": "substitutions"},
                    {"label": "Chef tips & \"why\" behind techniques", "value": "chef_tips"},
                    {"label": "Troubleshooting if something goes wrong", "value": "troubleshooting"},
                ],
            },
            {
                "id": "recipe_frustration",
                "type": "text",
                "question": "When you're mid-cook and something's not working, what do you wish a recipe told you?",
                "hint": "I wish it explained why I'm doing each step so I can troubleshoot on the fly",
            },
        ],
    },
    "page_2": {
        "title": "Shopping & Ingredients",
        "subtitle": "Alfred maintains your shopping lists and tracks what's in your pantry — so you always know what you have and what you need.",
        "image": "/onboarding/onboarding-pantry.svg",
        "maps_to": ["shopping", "inventory"],
        "questions": [
            {
                "id": "shopping_detail",
                "type": "chips",
                "multi": False,
                "question": "What helps you shop fastest?",
                "options": [
                    {"label": "Quick scan — items, rough amounts", "value": "quick_scan"},
                    {"label": "Full detail — exact quantities, notes", "value": "full_detail"},
                ],
            },
            {
                "id": "shopping_frequency",
                "type": "chips",
                "multi": False,
                "question": "How do you typically shop?",
                "options": [
                    {"label": "One big weekly trip", "value": "weekly_trip"},
                    {"label": "Multiple small trips", "value": "small_trips"},
                    {"label": "Online delivery", "value": "online"},
                    {"label": "Mix of stores", "value": "mix_stores"},
                ],
            },
            {
                "id": "shopping_organization",
                "type": "chips",
                "multi": False,
                "question": "How should Alfred organize your lists?",
                "options": [
                    {"label": "By recipe — \"for the curry: ...\"", "value": "by_recipe"},
                    {"label": "By store section — Produce, Dairy, Meat", "value": "by_section"},
                ],
            },
            {
                "id": "grocery_frustration",
                "type": "text",
                "question": "What's your biggest grocery or ingredient frustration?",
                "hint": "I always forget what I already have and end up with 3 jars of cumin",
            },
        ],
    },
    "page_3": {
        "title": "Meal Planning & Prep",
        "subtitle": "Alfred plans your meals and sends prep reminders — so nothing catches you off guard on a busy Tuesday.",
        "image": "/onboarding/onboarding-mealplan.svg",
        "maps_to": ["meal_plans", "tasks"],
        "questions": [
            {
                "id": "cooking_rhythm",
                "type": "chips",
                "multi": False,
                "question": "What's your cooking rhythm?",
                "options": [
                    {"label": "Cook fresh each day", "value": "fresh_daily"},
                    {"label": "Mix of fresh and batch", "value": "mixed"},
                    {"label": "Weekend batch + weekday assembly", "value": "batch_assembly"},
                ],
            },
            {
                "id": "leftover_strategy",
                "type": "chips",
                "multi": False,
                "question": "How do you handle leftovers?",
                "options": [
                    {"label": "Happy eating the same thing", "value": "same_meal"},
                    {"label": "Transform into new dishes", "value": "transform"},
                    {"label": "Leftovers lose quality, prefer fresh", "value": "prefer_fresh"},
                ],
            },
            {
                "id": "prep_reminder_detail",
                "type": "chips",
                "multi": False,
                "question": "How much context do you want in prep reminders?",
                "options": [
                    {"label": "Just the task — \"thaw chicken\"", "value": "task_only"},
                    {"label": "Include the meal — \"thaw chicken for Thursday's stir-fry\"", "value": "with_meal"},
                    {"label": "Full scheduling — \"thaw 1.5lb chicken (Thursday stir-fry), move to fridge by Tue 6pm\"", "value": "full_context"},
                ],
            },
            {
                "id": "ideal_week",
                "type": "text",
                "question": "What does your ideal cooking week look like?",
                "hint": "Big cook Sunday, quick assembly Mon-Wed, eat out Thursday, something fun Friday",
            },
        ],
    },
}


# =============================================================================
# Label Lookup (for formatting answers as readable text)
# =============================================================================

def _build_label_lookup() -> dict[str, dict[str, str]]:
    """Build a question_id → {value: label} lookup from static pages."""
    lookup: dict[str, dict[str, str]] = {}
    for page in STATIC_PAGES.values():
        for q in page["questions"]:
            if q["type"] == "chips":
                lookup[q["id"]] = {opt["value"]: opt["label"] for opt in q["options"]}
    return lookup


LABEL_LOOKUP = _build_label_lookup()


# =============================================================================
# Response Models
# =============================================================================

class InterviewQuestion(BaseModel):
    """A single interview question generated by LLM (used for catchall page)."""
    id: str = Field(description="Data point ID this captures, e.g., 'clarify_leftovers'")
    question: str = Field(description="The question text, conversational tone")
    hint: str = Field(description="Example answer as placeholder, first person, natural")


class CatchallPage(BaseModel):
    """The catch-all page with follow-up questions."""
    subtitle: str = Field(description="Friendly intro acknowledging their answers")
    questions: list[InterviewQuestion] = Field(
        description="0-3 follow-up questions to fill gaps",
        max_length=3,
    )
    ready_to_proceed: bool = Field(description="True if answers are complete, no questions needed")


class SubdomainGuidance(BaseModel):
    """Synthesized guidance strings for all subdomains."""
    recipes: str = Field(description="~100-200 words on how to write recipes for this user")
    meal_plans: str = Field(description="~100-200 words on how to structure meal plans")
    tasks: str = Field(description="~50-75 words on how to format prep tasks")
    shopping: str = Field(description="~50-75 words on shopping list preferences")
    inventory: str = Field(description="~50-75 words on inventory tracking style")


# =============================================================================
# LLM Prompts
# =============================================================================

SYSTEM_IDENTITY = """You are the Preference Synthesizer for Alfred, an agentic cooking assistant.

## About Alfred

Alfred is a multi-agent AI system that helps users with:
- Recipe discovery and generation
- Meal planning and scheduling
- Prep task management
- Shopping list organization
- Pantry/inventory tracking

Alfred uses `subdomain_guidance` strings to personalize ALL outputs. These are 50-200 word
instruction sets that shape how Alfred writes recipes, structures meal plans, formats tasks, etc.

## What Alfred Actually Does With Your Guidance

Your guidance strings are injected LITERALLY into Alfred's prompts at two points:
- **Think Node**: All 5 guidance strings visible when Alfred plans what to do
- **Act Node**: Domain-specific guidance when Alfred writes/generates content

### Alfred's Data Model (write guidance that maps to these)

- Recipes: name, description, cuisine (italian/mexican/chinese/etc.), difficulty (easy/medium/hard),
  ingredients[] with quantities, steps[] with timing
- Inventory: name, quantity, unit, location (pantry/fridge/freezer/counter/cabinet), expiry_date
- Shopping: name, quantity, unit, checked, grouped by category
- Meal Plans: date, meal_type (breakfast/lunch/dinner/snack), linked recipe
- Tasks: title, description, due_date, category (prep/shopping/cleanup), completed

### Concrete Examples of How Guidance Drives Output

When recipes guidance says "Explain why behind non-obvious steps, skip basics":
→ Alfred writes: "Sear chicken 4 min per side until golden (internal 165°F) —
   the high heat creates a Maillard crust that locks in moisture."

When shopping guidance says "Organize by store section":
→ Alfred groups: Produce: [items], Dairy: [items], Meat: [items]

When tasks guidance says "Include meal connection and timing":
→ Alfred generates: "Thaw salmon for Friday's teriyaki bowl — move to fridge by Thu 6pm"

## Critical: Preferences Shape Output, Never Restrict Capability

Alfred will ALWAYS help when explicitly asked. Guidance shapes HOW, not WHETHER.

❌ WRONG: "You prefer quick meals, so I can't help with this complex dish"
❌ WRONG: "You said basic tracking, so I won't add this item"
✅ RIGHT: Write guidance as "prefer X" and "default to Y", never "never do X"

Every preference is a DEFAULT, not a constraint.
"""


GENERATE_CATCHALL_PROMPT = """{system_identity}

## Your Task: Generate Catch-all Follow-up Questions (Page 4)

You've collected structured preferences and text answers from the first 3 interview pages.
Now review for gaps or contradictions.

### User Context
| Attribute | Value |
|-----------|-------|
| Cooking skill | {skill_level} |
| Household | {household_size} people |
| Dietary | {dietary} |
| Cuisines | {cuisines} |

### All Interview Answers So Far
{all_answers}

## Captured Signal (What We Already Know)

From Pages 1-3, we have user preferences for:
- **Recipe writing**: assumed competence level, timing format, useful extras
- **Time constraints**: weeknight cook time budget
- **Shopping lists**: verbosity style, organization format, shopping frequency
- **Meal planning**: batch vs. daily rhythm, leftover handling
- **Task reminders**: context level (task-only vs. full scheduling)

## Decision Gaps to Probe

The structured chip answers above already cover recipe detail, timing, cook time,
shopping format, cooking rhythm, leftovers, and prep reminder style. Do NOT re-ask
about any of these — they are resolved.

The ONLY gaps worth probing (if text answers don't already cover them):
- Weekend vs. weekday cooking differences (time budget only covers weeknights)
- Cuisine exploration appetite (do they want variety or stick to favorites?)
- Hard exclusions ("never suggest X" — ingredients, cuisines, or styles to avoid)

Do NOT ask questions that:
- Restate or clarify a chip selection (those are definitive)
- Could be interpreted as restricting Alfred's willingness to help

## Success Criteria

1. **Identify gaps**: What preferences are still unclear for subdomain_guidance?
2. **Spot contradictions**: Did they say conflicting things? Clarify.
3. **Don't over-ask**: If answers are clear and complete, return empty questions and set ready_to_proceed=true.

### Good Follow-up Examples
- "You mentioned batch cooking but also said leftovers lose quality - do you mean you batch components and assemble fresh?"
- "Any ingredients or cuisines you'd NEVER want suggested?"
- "You mentioned weeknight time limits - are weekends different?"

### Bad Follow-ups (Don't do these)
- Generic questions that don't reference their answers
- Questions already answered by chip selections
- Asking just to have more questions

## Output Contract

Return a JSON object with:
- subtitle: Friendly 1-2 sentence acknowledging what they've shared
- questions: Array of 0-3 follow-up questions (empty if complete), each with:
  - id: A descriptive ID like "clarify_leftovers" or "weekend_cooking"
  - question: Your question text, referencing their specific answers
  - hint: Example answer
- ready_to_proceed: true if answers are complete (even if questions array is empty)
"""


# =============================================================================
# Subdomain Outcomes Framework
# =============================================================================

SUBDOMAIN_OUTCOMES = """
## Alfred Subdomain Guidance Framework

Alfred uses `subdomain_guidance` strings to personalize ALL outputs.

### subdomain_guidance["recipes"]
Controls how recipes are written. Key dimensions:
- **Assumed competence**: Skip obvious techniques ↔ Explain everything with context
- **Timing info**: Visual cues only ↔ Precise temps + exact times
- **Extras**: Substitutions, chef tips, troubleshooting — include what user selected
- **Complexity**: Weeknight time constraints → filter recipe suggestions accordingly

### subdomain_guidance["meal_plans"]
Controls how meal plans are structured. Key dimensions:
- **Cooking rhythm**: Cook fresh daily ↔ Weekend batch + weekday assembly
- **Leftover strategy**: Same meal ↔ Transform into new dishes ↔ Prefer fresh
- **Prep scheduling**: Based on cooking rhythm and weeknight time constraints
- **Detail level**: Meals only ↔ Full calendar with prep tasks linked

### subdomain_guidance["tasks"]
Controls prep reminders and task formatting. Key dimensions:
- **Context level**: Task-only ↔ Include meal connection ↔ Full scheduling with timing
- **Timing**: Tied to their cooking rhythm (batch = prep days ahead)

### subdomain_guidance["shopping"]
Controls shopping list organization. Key dimensions:
- **Organization**: By recipe ↔ By store section
- **Detail**: Quick scan (item + rough amount) ↔ Full detail (exact quantities, notes)
- **Frequency**: Matches their shopping style (weekly, small trips, online, mixed)

### subdomain_guidance["inventory"]
Controls pantry tracking. Key dimensions:
- **Proactive vs. reactive**: Based on their frustrations (waste, forgetting what they have)
- **Staple assumptions**: Infer from their selected pantry staples during onboarding
"""


SYNTHESIZE_GUIDANCE_PROMPT = """{system_identity}

## Your Task: Synthesize Interview → subdomain_guidance Strings

Convert all interview answers into the subdomain_guidance strings that Alfred will use.

### User Context
| Attribute | Value |
|-----------|-------|
| Cooking skill | {skill_level} |
| Household | {household_size} people |
| Dietary | {dietary} |
| Equipment | {equipment} |
| Cuisines | {cuisines} |
| Liked ingredients | {liked_ingredients} |

### All Interview Answers
{all_answers}

## How Preferences Map to Guidance

Each chip selection translates to an imperative instruction:

| User Selected | → Guidance Fragment |
|---------------|---------------------|
| "Assume I know the basics" | "Skip explanations for basic techniques. Focus on what's non-obvious." |
| "Explain key techniques" | "Briefly explain the why behind key techniques." |
| "Walk me through everything" | "Explain each technique. Include why, not just how. Break complex steps into micro-steps." |
| "Visual cues & intuition" | "Emphasize visual and texture cues for doneness. Skip exact times where possible." |
| "Times + visual cues" | "Include both precise times and visual cues. Times as guidance, visual cues as confirmation." |
| "Exact temps & times" | "Always include exact temperatures and times. Precise measurements for all cooking steps." |
| "Under 20 min" | "Prioritize recipes under 20 min active time for weeknights." |
| "20-40 min" | "Weeknight recipes should target 20-40 min active time." |
| "40-60 min" | "Weeknight recipes can be up to 60 min." |
| "No rush" | "No time constraints — include involved recipes freely." |
| "Quick scan — items, rough amounts" | "Shopping lists: item names with rough quantities. Scannable, not verbose." |
| "Full detail — exact quantities, notes" | "Shopping lists: exact quantities, brief notes, highlight fresh vs. frozen." |
| "By recipe" | "Organize shopping lists by recipe — group items under the dish they're for." |
| "By store section" | "Organize shopping lists by store section (Produce, Dairy, Meat, Pantry)." |
| "Cook fresh each day" | "Plan for daily fresh cooking. Minimize batch prep assumptions." |
| "Mix of fresh and batch" | "Balance batch components (sauces, proteins) with fresh daily cooking." |
| "Weekend batch + weekday assembly" | "Structure around weekend batch cooking, weekday assembly from components." |
| "Happy eating the same thing" | "Leftovers OK as-is. Plan for bulk portions that reheat well." |
| "Transform into new dishes" | "Plan leftover transformations — Sunday roast becomes Monday tacos." |
| "Leftovers lose quality, prefer fresh" | "Minimize leftovers. Plan appropriate portions for fresh cooking." |
| "Just the task" | "Prep reminders: simple task name only." |
| "Include the meal" | "Prep reminders: include which meal the task is for." |
| "Full scheduling" | "Prep reminders: include meal name, quantity, and timing deadline." |

Chip selections give you the WHAT. Text answers give you the HOW and WHY — use both.

## Subdomain Guidance Specification

Each subdomain_guidance string is injected into Alfred's prompts and followed LITERALLY.
Write direct instructions that shape Alfred's behavior.

{subdomain_framework}

## Writing for User Comfort

1. **Match their energy** — If text answers are casual, write conversational guidance
2. **Respect their competence** — If they selected "Assume I know basics", don't add training wheels
3. **Address their frustrations** — If they said "I waste ingredients", make inventory guidance proactive
4. **Default to helpful, not less** — When uncertain, write guidance that helps MORE, not less

## Success Criteria

For each subdomain, write guidance that:
1. **Is specific and actionable** — "Include timing for proteins" not "be helpful"
2. **Maps from their selections** — Chip labels → imperative instructions (see table above)
3. **Incorporates their text answers** — Add specificity and voice from free-text responses
4. **Uses imperative style** — "Do X. Prefer Y. Default to Z."
5. **Uses "prefer/default to" language** — Never "never do X" or "refuse Y"
6. **Respects word limits** — These go into EVERY prompt, keep them tight

### Word Limits
| Subdomain | Words | Focus |
|-----------|-------|-------|
| recipes | 100-200 | Assumed competence, timing format, extras, weeknight constraints |
| meal_plans | 100-200 | Cooking rhythm, leftovers, scheduling, component reuse |
| tasks | 50-75 | Reminder context level, timing, meal linking |
| shopping | 50-75 | Organization, detail level, shopping frequency |
| inventory | 50-75 | Tracking approach, staple assumptions, frustration-driven |

## Output Contract

Return a JSON object with exactly these 5 keys:
- recipes: string (100-200 words)
- meal_plans: string (100-200 words)
- tasks: string (50-75 words)
- shopping: string (50-75 words)
- inventory: string (50-75 words)

### Example Output

```json
{{{{
  "recipes": "Assume intermediate competence — skip explanations for basic techniques like sautéing, dicing, or deglazing. For non-obvious steps, briefly explain the why (e.g., why you rest meat, why you bloom spices in oil). Include both precise times and visual cues: times as guidance, visual cues as confirmation of doneness. Always include exact temperatures for proteins. Weeknight recipes should target 20-40 min active time using skillet or air fryer. Weekends can be more involved. Include substitutions when an ingredient might be hard to find. Add chef tips for technique nuances, especially for Thai and Mexican cuisines.",
  "meal_plans": "Structure meal plans around a mix of batch and fresh cooking. Prep 2-3 batch components on weekends (sauces, marinated proteins), with fresh vegetables and carbs added daily. Plan leftover transformations — roast chicken becomes chicken tacos becomes chicken soup. Weeknight active cooking should stay under 30 min. Include prep task reminders linked to specific meals. Flexible on Thursday for eating out or takeout.",
  "tasks": "Include the meal connection in every prep reminder — 'thaw chicken for Thursday's stir-fry.' Link batch prep tasks to the specific meals they enable. Reminders 1-2 days ahead for thawing and marinating.",
  "shopping": "Organize shopping lists by store section (Produce, Dairy, Meat, Pantry). Include exact quantities and brief notes. Plan for a single weekly trip with a short midweek top-up for fresh produce.",
  "inventory": "Track proteins, sauces, and fresh produce — these drive meal planning decisions. Assume common pantry staples (oil, salt, basic spices) are always available. Flag items approaching expiry when they could be used in upcoming meals."
}}}}
```
"""


# =============================================================================
# Helper Functions
# =============================================================================

def get_static_page(page_number: int) -> dict:
    """
    Return the static page definition for pages 1-3.

    Args:
        page_number: 1, 2, or 3

    Returns:
        Dict with title, subtitle, image, questions (ready to send to frontend)
    """
    page_key = f"page_{page_number}"
    if page_key not in STATIC_PAGES:
        raise ValueError(f"Invalid static page number: {page_number}. Must be 1-3.")

    page = STATIC_PAGES[page_key]
    return {
        "page_number": page_number,
        "title": page["title"],
        "subtitle": page["subtitle"],
        "image": page["image"],
        "questions": page["questions"],
        "is_catchall": False,
    }


def _format_prior_answers(answers: list[dict]) -> str:
    """Format prior answers for prompt context, handling typed inputs."""
    if not answers:
        return "(No answers yet)"

    lines = []
    for ans in answers:
        q_id = ans.get("question_id", ans.get("id", "unknown"))
        ans_type = ans.get("type", "text")

        if ans_type == "chips":
            # Multi-select chips
            if "values" in ans:
                value_ids = ans["values"]
                labels = [
                    LABEL_LOOKUP.get(q_id, {}).get(v, v)
                    for v in value_ids
                ]
                lines.append(f"{q_id}: {', '.join(labels)}")
            # Single-select chip
            elif "value" in ans:
                value_id = ans["value"]
                label = LABEL_LOOKUP.get(q_id, {}).get(value_id, value_id)
                lines.append(f"{q_id}: {label}")
        elif ans_type == "text":
            answer_text = ans.get("answer", "")
            if answer_text.strip():
                # Find the question text from static pages
                question_text = _find_question_text(q_id)
                if question_text:
                    lines.append(f"Q: {question_text}")
                    lines.append(f"A: {answer_text}")
                else:
                    # Catchall page questions (not in static pages)
                    q_text = ans.get("question", q_id)
                    lines.append(f"Q: {q_text}")
                    lines.append(f"A: {answer_text}")
        else:
            # Legacy format: plain Q/A from catchall page
            question = ans.get("question", "")
            answer = ans.get("answer", "")
            if question and answer:
                lines.append(f"Q: {question}")
                lines.append(f"A: {answer}")

        lines.append("")

    return "\n".join(lines).strip()


def _find_question_text(question_id: str) -> str | None:
    """Find the question text for a given question_id from static pages."""
    for page in STATIC_PAGES.values():
        for q in page["questions"]:
            if q["id"] == question_id:
                return q["question"]
    return None


# =============================================================================
# LLM Functions
# =============================================================================

async def generate_catchall_page(
    user_context: dict,
    all_answers: list[dict],
) -> CatchallPage:
    """
    Generate the catch-all page with follow-up questions if needed.

    Args:
        user_context: Dict with user preferences
        all_answers: All answers from pages 1-3

    Returns:
        CatchallPage with 0-3 follow-up questions
    """
    prompt = GENERATE_CATCHALL_PROMPT.format(
        system_identity=SYSTEM_IDENTITY,
        skill_level=user_context.get("cooking_skill_level", "intermediate"),
        household_size=user_context.get("household_size", 2),
        dietary=", ".join(user_context.get("dietary_restrictions", [])) or "None",
        cuisines=", ".join(user_context.get("cuisines", [])) or "Various",
        all_answers=_format_prior_answers(all_answers),
    )

    return await call_llm(
        response_model=CatchallPage,
        system_prompt=prompt,
        user_prompt="Review the interview answers and generate follow-up questions if any gaps or contradictions exist.",
        complexity="medium",
    )


async def synthesize_guidance(
    user_context: dict,
    all_answers: list[dict],
) -> SubdomainGuidance:
    """
    Synthesize all interview answers into subdomain_guidance strings.

    Args:
        user_context: Dict with user preferences
        all_answers: All answers from interview (pages 1-4)

    Returns:
        SubdomainGuidance with strings for all 5 subdomains
    """
    prompt = SYNTHESIZE_GUIDANCE_PROMPT.format(
        system_identity=SYSTEM_IDENTITY,
        subdomain_framework=SUBDOMAIN_OUTCOMES,
        skill_level=user_context.get("cooking_skill_level", "intermediate"),
        household_size=user_context.get("household_size", 2),
        dietary=", ".join(user_context.get("dietary_restrictions", [])) or "None",
        equipment=", ".join(user_context.get("available_equipment", [])) or "Standard kitchen",
        cuisines=", ".join(user_context.get("cuisines", [])) or "Various",
        liked_ingredients=", ".join(user_context.get("liked_ingredients", [])[:10]) or "Not specified",
        all_answers=_format_prior_answers(all_answers),
    )

    return await call_llm(
        response_model=SubdomainGuidance,
        system_prompt=prompt,
        user_prompt="Synthesize all interview answers into subdomain_guidance strings that Alfred will follow literally.",
        complexity="medium",
    )
