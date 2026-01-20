"""
Style Interview - LLM-Guided Preference Discovery.

This module handles the conversational interview phase of onboarding where we
discover user preferences through free-form questions, then synthesize into
structured subdomain_guidance strings.

## How Alfred Uses subdomain_guidance

Alfred is a multi-agent cooking assistant with 5 subdomains:
- recipes: How to write/present recipes
- meal_plans: How to structure meal plans  
- tasks: How to format prep tasks and reminders
- shopping: How to organize shopping lists
- inventory: How to track pantry items

Each subdomain has a `subdomain_guidance` string (~50-200 tokens) that shapes
ALL outputs for that domain. Examples:

    subdomain_guidance["recipes"] = 
        "Concise steps with timing cues. Skip obvious techniques. 
         Include chef tips and why behind key steps. Temperature 
         for proteins, visual cues for vegetables."
    
    subdomain_guidance["meal_plans"] = 
        "Batch cooking orientation - big cook Sunday, assembly weeknights.
         Show leftover transformations. Include shopping list summary.
         Flexible on Thursday for eating out."

## Interview Flow

1. Page 1: Cooking Style (4 questions) → recipe guidance
2. Page 2: Planning & Prep (4 questions) → meal_plans, tasks guidance  
3. Page 3: Exploration & Goals (4 questions) → all domains
4. Page 4: Catch-all (0-4 questions) → fill gaps

Each page: LLM generates questions → user answers free text → next page
Finally: LLM synthesizes all answers → subdomain_guidance strings
"""

from pydantic import BaseModel, Field
from typing import Literal
import logging

from alfred.llm.client import call_llm

logger = logging.getLogger(__name__)


# =============================================================================
# Outcome Framework - What We're Trying to Determine
# =============================================================================

SUBDOMAIN_OUTCOMES = """
## Alfred Subdomain Guidance Framework

Alfred uses `subdomain_guidance` strings to personalize ALL outputs. Your job is
to ask questions that help us write these guidance strings.

### subdomain_guidance["recipes"]
Controls how recipes are written. Key dimensions:
- **Detail level**: Concise bullets ↔ Full step-by-step with explanations
- **Timing info**: Visual cues only ↔ Precise temps + exact times
- **Technique depth**: Skip obvious ↔ Explain why + chef tips
- **Substitutions**: Assume competence ↔ Suggest alternatives
- **Complexity**: Simple one-pot ↔ Multi-component dishes OK

Example outputs:
- Beginner: "Full step-by-step instructions. Explain techniques briefly. Include exact temps and times. Suggest substitutions. Keep to 6-8 steps max."
- Advanced: "Concise steps, skip obvious. Focus on technique nuances and timing. Multi-component dishes OK. Include chef tips and why behind key decisions."

### subdomain_guidance["meal_plans"]  
Controls how meal plans are structured. Key dimensions:
- **Batch orientation**: Cook fresh daily ↔ Heavy batch cooking
- **Leftover strategy**: Same meal ↔ Transform into new dishes
- **Prep scheduling**: Daily cooking ↔ Weekend batch + weekday assembly
- **Freezer usage**: Never ↔ Heavy freezer rotation
- **Detail level**: Just meals ↔ Full calendar with prep tasks

Example outputs:
- Busy parent: "Batch cook Sunday. Show leftover transformations. Assembly meals weeknights (15-20 min). Include prep tasks for day before."
- Food enthusiast: "Fresh cooking preferred. Variety over efficiency. Different cuisine each night. Detailed shopping by store section."

### subdomain_guidance["tasks"]
Controls prep reminders and task formatting. Key dimensions:
- **Timing**: Day-of reminders ↔ 2-3 days ahead
- **Detail**: "Thaw chicken" ↔ "Thaw chicken breast (1.5lb) for Thursday's stir-fry - move to fridge by 6pm Tuesday"
- **Context**: Standalone tasks ↔ Linked to specific meals

### subdomain_guidance["shopping"]
Controls shopping list organization. Key dimensions:
- **Grouping**: By recipe ↔ By store section
- **Detail**: Just items ↔ Quantities + notes + substitutions
- **Frequency**: Single trip ↔ Multi-store strategy

### subdomain_guidance["inventory"]
Controls pantry tracking. Key dimensions:
- **Strictness**: Loose tracking ↔ Precise quantities
- **Staple assumptions**: Assume basics ↔ Track everything
- **Expiry focus**: Relaxed ↔ Strict FIFO
"""

# =============================================================================
# Data Points to Capture
# =============================================================================

INTERVIEW_FRAMEWORK = {
    "page_1": {
        "title": "Cooking Style",
        "focus": "How you approach cooking and what you need from recipes",
        "maps_to": ["recipes"],
        "data_points": [
            {
                "id": "recipe_detail_level",
                "question_goal": "Understand how much hand-holding they need in recipe instructions",
                "outcome_range": "Concise bullets ↔ Full step-by-step with explanations",
                "example_hints": [
                    "I like clear steps but don't need the basics explained - I know how to sauté",
                    "Walk me through everything, I'm still building confidence",
                    "Just key points - I'll figure out the technique"
                ]
            },
            {
                "id": "timing_preference",
                "question_goal": "Do they want precise temps/times or prefer visual cues?",
                "outcome_range": "Visual cues mostly ↔ Exact temperatures and times always",
                "example_hints": [
                    "Precise temps for meat safety, but I go by look for veggies",
                    "I need exact times - I set timers for everything",
                    "I go by smell and color mostly, temps feel clinical"
                ]
            },
            {
                "id": "cooking_help_level",
                "question_goal": "How much guidance during cooking - substitutions, tips, troubleshooting?",
                "outcome_range": "I can improvise ↔ Tell me everything including what could go wrong",
                "example_hints": [
                    "Love knowing substitutions and what I can swap in a pinch",
                    "Just the base recipe - I'll adapt as needed",
                    "Chef tips are gold - tell me the why behind techniques"
                ]
            },
            {
                "id": "weeknight_time",
                "question_goal": "Time constraints for typical weeknight cooking",
                "outcome_range": "15-20 min max ↔ Time is flexible",
                "example_hints": [
                    "30 mins max on weeknights, but I have time on weekends",
                    "Need quick 15-20 min meals, kids are hungry",
                    "I actually enjoy longer cooks, it's my wind-down time"
                ]
            },
        ]
    },
    "page_2": {
        "title": "Planning & Prep", 
        "focus": "How you organize your cooking week and handle meal prep",
        "maps_to": ["meal_plans", "tasks"],
        "data_points": [
            {
                "id": "cooking_rhythm",
                "question_goal": "Do they batch cook, cook daily, or mix?",
                "outcome_range": "Fresh each day ↔ Weekend batch + weekday assembly",
                "example_hints": [
                    "Big cook Sunday, then mostly assembly during the week",
                    "I prefer cooking fresh each night - it's my therapy",
                    "Mix depending on the week - some batch, some fresh"
                ]
            },
            {
                "id": "leftover_strategy",
                "question_goal": "How they feel about and handle leftovers",
                "outcome_range": "Same meal repeated ↔ Transform into completely new dishes",
                "example_hints": [
                    "Love transforming - Sunday roast becomes Monday tacos",
                    "Happy eating the same thing for 2-3 days",
                    "Honestly not a big leftovers person, prefer fresh"
                ]
            },
            {
                "id": "freezer_usage",
                "question_goal": "How much do they use freezer for meal prep strategy?",
                "outcome_range": "Rarely freeze ↔ Heavy freezer rotation",
                "example_hints": [
                    "Freeze sauces, stocks, and extra proteins all the time",
                    "Prefer fresh - freezer is mostly for ice cream",
                    "Some emergency meals frozen, but not my main strategy"
                ]
            },
            {
                "id": "prep_tasks_detail",
                "question_goal": "How detailed should prep reminders be?",
                "outcome_range": "Simple task name ↔ Full context with timing and meal link",
                "example_hints": [
                    "Link it to the meal - 'thaw chicken for Thursday stir-fry'",
                    "Just 'thaw chicken' is fine, I'll remember why",
                    "Include timing - 'move to fridge by 6pm Tuesday'"
                ]
            },
        ]
    },
    "page_3": {
        "title": "Exploration & Goals",
        "focus": "What you want to learn, explore, and your shopping style",
        "maps_to": ["recipes", "meal_plans", "shopping", "inventory"],
        "data_points": [
            {
                "id": "exploration_level", 
                "question_goal": "How adventurous are they with new recipes and cuisines?",
                "outcome_range": "Stick to reliable favorites ↔ Always trying new things",
                "example_hints": [
                    "Love trying new cuisines - surprise me!",
                    "Mostly stick to favorites but open to occasional new thing",
                    "Very adventurous - I get bored cooking the same stuff"
                ]
            },
            {
                "id": "growth_direction",
                "question_goal": "What specific areas do they want to improve or explore?",
                "outcome_range": "Open-ended - capture their interests",
                "example_hints": [
                    "Want to get better at Thai curries and proper wok technique",
                    "Trying to eat more vegetables in interesting ways",
                    "Learning to bake bread and work with doughs"
                ]
            },
            {
                "id": "shopping_style",
                "question_goal": "How and when do they typically shop?",
                "outcome_range": "As-needed trips ↔ Planned weekly with list",
                "example_hints": [
                    "Weekly Costco run plus farmers market on Saturday",
                    "Quick trips as needed - hate big shopping expeditions",
                    "Online delivery for basics, specialty store for fun stuff"
                ]
            },
            {
                "id": "biggest_challenge",
                "question_goal": "What's their main cooking pain point we can help with?",
                "outcome_range": "Open-ended - understand their frustrations",
                "example_hints": [
                    "Running out of weeknight dinner ideas",
                    "Wasting ingredients that go bad before I use them",
                    "Making healthy food that my kids will actually eat"
                ]
            },
        ]
    },
}


# =============================================================================
# Response Models
# =============================================================================

class InterviewQuestion(BaseModel):
    """A single interview question generated by LLM."""
    id: str = Field(description="Data point ID this captures, e.g., 'recipe_detail_level'")
    question: str = Field(description="The question text, conversational tone")
    hint: str = Field(description="Example answer as placeholder, first person, natural")


class InterviewPage(BaseModel):
    """One page of the interview."""
    title: str = Field(description="Page title")
    subtitle: str = Field(description="Friendly 1-2 sentence intro for this section")
    questions: list[InterviewQuestion] = Field(description="4 questions for this page")


class CatchallPage(BaseModel):
    """The catch-all page with follow-up questions."""
    subtitle: str = Field(description="Friendly intro acknowledging their answers")
    questions: list[InterviewQuestion] = Field(description="0-4 follow-up questions to fill gaps")
    ready_to_proceed: bool = Field(description="True if answers are complete, no questions needed")


class SubdomainGuidance(BaseModel):
    """Synthesized guidance strings for all subdomains."""
    recipes: str = Field(description="~50-100 words on how to write recipes for this user")
    meal_plans: str = Field(description="~50-100 words on how to structure meal plans")
    tasks: str = Field(description="~30-50 words on how to format prep tasks")
    shopping: str = Field(description="~30-50 words on shopping list preferences")
    inventory: str = Field(description="~30-50 words on inventory tracking style")


# =============================================================================
# LLM Prompts
# =============================================================================

# =============================================================================
# System Prompts with Clear Identity + Success Criteria
# =============================================================================

SYSTEM_IDENTITY = """You are the Preference Curator for Alfred, an agentic cooking assistant.

## About Alfred

Alfred is a multi-agent AI system that helps users with:
- Recipe discovery and generation
- Meal planning and scheduling
- Prep task management
- Shopping list organization
- Pantry/inventory tracking

Alfred uses `subdomain_guidance` strings to personalize ALL outputs. These are 50-150 word 
instruction sets that shape how Alfred writes recipes, structures meal plans, formats tasks, etc.

## Your Role

You are conducting an onboarding interview to discover user preferences. Your questions will 
be synthesized into subdomain_guidance strings that Alfred follows literally.

## Success Criteria

A successful interview:
1. Captures specific, actionable preferences (not vague platitudes)
2. Teases out the user's actual cooking style through natural conversation
3. Provides enough signal to write distinct, personalized guidance
4. Feels conversational and warm, not like a form

Bad: "Do you like detailed recipes?" → "Yes" (useless)
Good: "When you're mid-cook and something's not working, what do you wish recipes told you?"
      → "I wish they'd explain WHY I'm doing each step so I can troubleshoot" (actionable!)
"""


GENERATE_PAGE_PROMPT = """{system_identity}

## Your Task: Generate Interview Page {page_number} - "{page_title}"

**Page Focus:** {page_focus}
**Maps to subdomains:** {maps_to}

### User Context
| Attribute | Value |
|-----------|-------|
| Cooking skill | {skill_level} |
| Household | {household_size} people |
| Dietary | {dietary} |
| Equipment | {equipment} |
| Cuisines | {cuisines} |
| Liked ingredients | {liked_ingredients} |

### Prior Answers
{prior_answers}

### Data Points to Capture This Page

{data_points_json}

## Success Criteria for This Page

Generate 4 questions that:
1. **Capture each data point** - One question per data point ID
2. **Tease out specifics** - Avoid yes/no questions, ask for their actual behavior
3. **Adapt to skill level** - Beginner = encouraging, advanced = peer-to-peer
4. **Reference their context** - Mention their cuisines, equipment, ingredients where natural
5. **Build on prior answers** - If they mentioned batch cooking, reference it

For each question provide a **hint** (example answer):
- First person voice ("I usually...", "For me...")
- Shows the DEPTH of answer we want
- Feels like a real person wrote it

## Output Contract

Return a JSON object with:
- title: Page title (use "{page_title}")
- subtitle: 1-2 sentence friendly intro for this section
- questions: Array of 4 objects, each with:
  - id: The data point ID (e.g., "recipe_detail_level")
  - question: Your question text
  - hint: Example answer as placeholder
"""


GENERATE_CATCHALL_PROMPT = """{system_identity}

## Your Task: Generate Catch-all Follow-up Questions (Page 4)

You've collected answers from the first 3 interview pages. Now review for gaps or contradictions.

### User Context
| Attribute | Value |
|-----------|-------|
| Cooking skill | {skill_level} |
| Household | {household_size} people |
| Dietary | {dietary} |
| Cuisines | {cuisines} |

### All Interview Answers So Far
{all_answers}

## Success Criteria

1. **Identify gaps**: What preferences are still unclear for subdomain_guidance?
2. **Spot contradictions**: Did they say conflicting things? Clarify.
3. **Fill holes**: Any major cooking style aspects we missed?
4. **Don't over-ask**: If answers are clear and complete, return empty questions.

### Good Follow-up Examples
- "You mentioned batch cooking but also said you don't love leftovers - do you mean transforming them into new dishes?"
- "Any ingredients or cuisines you'd NEVER want suggested?"
- "You mentioned weeknight time limits - are weekends different?"

### Bad Follow-ups (Don't do these)
- Generic questions that don't reference their answers
- Questions already answered implicitly
- Asking just to have more questions

## Output Contract

Return a JSON object with:
- subtitle: Friendly 1-2 sentence acknowledging what they've shared
- questions: Array of 0-4 follow-up questions (empty if complete), each with:
  - id: A descriptive ID like "clarify_leftovers" or "weekend_cooking"
  - question: Your question text, referencing their specific answers
  - hint: Example answer
- ready_to_proceed: true if answers are complete (even if questions array is empty)
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

## Subdomain Guidance Specification

Each subdomain_guidance string is injected into Alfred's prompts and followed LITERALLY.
Write direct instructions that shape Alfred's behavior.

{subdomain_framework}

## Success Criteria

For each subdomain, write guidance that:
1. **Is specific and actionable** - "Include timing for proteins" not "be helpful"
2. **References their actual answers** - If they said "visual cues for veggies", include it
3. **Uses imperative style** - "Do X. Skip Y. Include Z."
4. **Respects word limits** - These go into EVERY prompt, keep them tight

### Word Limits
| Subdomain | Words | Focus |
|-----------|-------|-------|
| recipes | 50-100 | Instruction detail, timing, technique, substitutions |
| meal_plans | 50-100 | Batch style, leftovers, scheduling, detail level |
| tasks | 30-50 | Reminder timing, detail, meal linking |
| shopping | 30-50 | Grouping, frequency, detail level |
| inventory | 30-50 | Tracking strictness, staple assumptions |

## Output Contract

Return a JSON object with exactly these 5 keys:
- recipes: string (50-100 words)
- meal_plans: string (50-100 words)
- tasks: string (30-50 words)
- shopping: string (30-50 words)
- inventory: string (30-50 words)

### Example Output

```json
{{
  "recipes": "Concise steps with timing for proteins, visual cues for vegetables. Skip basic techniques - user is intermediate. Include chef tips and the 'why' behind key decisions. Substitutions welcome. Multi-component dishes OK for weekends, simple one-pot for weeknights.",
  "meal_plans": "Batch cooking orientation - big cook Sunday, assembly weeknights. Show leftover transformations (roast chicken → tacos → soup). Max 30 min active time weeknights. Include prep task reminders day-before. Shopping list at end.",
  "tasks": "Day-before reminders linked to specific meals. Include timing: 'Thaw chicken for Thursday stir-fry - move to fridge by Tuesday 6pm.'",
  "shopping": "Group by store section. Weekly Costco + farmers market pattern. Note which items are flexible/substitutable.",
  "inventory": "Loose tracking - proteins and produce only. Assume standard pantry staples always available."
}}
```
"""


# =============================================================================
# Generation Functions
# =============================================================================

def _format_data_points(page_key: str) -> str:
    """Format data points for a page into structured format for LLM."""
    page = INTERVIEW_FRAMEWORK[page_key]
    lines = []
    for i, dp in enumerate(page["data_points"], 1):
        lines.append(f"""
**Data Point {i}: `{dp['id']}`**
- Goal: {dp['question_goal']}
- Outcome range: {dp['outcome_range']}
- Example hint styles: {dp['example_hints']}
""")
    return "\n".join(lines)


def _format_prior_answers(answers: list[dict]) -> str:
    """Format prior answers for prompt context."""
    if not answers:
        return "(No prior answers yet - this is the first page)"
    
    lines = []
    for ans in answers:
        lines.append(f"Q: {ans.get('question', 'Unknown')}")
        lines.append(f"A: {ans.get('answer', 'No answer')}")
        lines.append("")
    return "\n".join(lines)


async def generate_interview_page(
    page_number: int,
    user_context: dict,
    prior_answers: list[dict],
) -> InterviewPage:
    """
    Generate an interview page with questions tailored to user context.
    
    Args:
        page_number: 1, 2, or 3
        user_context: Dict with skill_level, household_size, dietary, equipment, cuisines, liked_ingredients
        prior_answers: List of {question, answer} dicts from previous pages
    
    Returns:
        InterviewPage with title, subtitle, and 4 questions
    """
    page_key = f"page_{page_number}"
    if page_key not in INTERVIEW_FRAMEWORK:
        raise ValueError(f"Invalid page number: {page_number}")
    
    page_info = INTERVIEW_FRAMEWORK[page_key]
    
    prompt = GENERATE_PAGE_PROMPT.format(
        system_identity=SYSTEM_IDENTITY,
        page_number=page_number,
        page_title=page_info["title"],
        page_focus=page_info["focus"],
        maps_to=", ".join(page_info["maps_to"]),
        skill_level=user_context.get("cooking_skill_level", "intermediate"),
        household_size=user_context.get("household_size", 2),
        dietary=", ".join(user_context.get("dietary_restrictions", [])) or "None",
        equipment=", ".join(user_context.get("available_equipment", [])) or "Standard kitchen",
        cuisines=", ".join(user_context.get("cuisines", [])) or "Various",
        liked_ingredients=", ".join(user_context.get("liked_ingredients", [])[:10]) or "Not specified",
        prior_answers=_format_prior_answers(prior_answers),
        data_points_json=_format_data_points(page_key),
    )
    
    return await call_llm(
        response_model=InterviewPage,
        system_prompt=prompt,
        user_prompt=f"Generate the '{page_info['title']}' interview page (page {page_number} of 4).",
        complexity="medium",
    )


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
        CatchallPage with 0-4 follow-up questions
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
