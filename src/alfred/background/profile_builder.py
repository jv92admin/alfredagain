"""
Alfred V2 - Profile Builder.

Pre-computes user profile artifacts for prompt injection:
- Preferences summary (constraints, household, equipment)
- Top recipes from cooking history
- Top ingredients from flavor preferences
- Recent activity summary

These artifacts are computed asynchronously and cached,
reducing runtime prompt construction overhead.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from alfred.db.client import get_client


@dataclass
class UserProfile:
    """Pre-computed user profile for prompt injection."""
    
    # From preferences table
    household_size: int = 1
    dietary_restrictions: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    cooking_skill_level: str = "intermediate"
    favorite_cuisines: list[str] = field(default_factory=list)
    available_equipment: list[str] = field(default_factory=list)
    time_budget_minutes: int = 30
    nutrition_goals: list[str] = field(default_factory=list)
    
    # From cooking_log aggregation
    top_recipes: list[dict] = field(default_factory=list)  # [{name, times_cooked, avg_rating}]
    recent_meals: list[dict] = field(default_factory=list)  # [{name, date, rating}]
    
    # From flavor_preferences
    top_ingredients: list[str] = field(default_factory=list)  # Most used ingredients
    
    # Metadata
    last_updated: datetime | None = None


async def build_user_profile(user_id: str) -> UserProfile:
    """
    Build a complete user profile by aggregating data from multiple tables.
    
    This is designed to be called:
    - On session start
    - After significant updates (preferences change, cooking log entry)
    - Periodically via background job
    
    Args:
        user_id: The user's UUID
        
    Returns:
        UserProfile with all aggregated data
    """
    client = get_client()
    profile = UserProfile()
    
    # 1. Fetch preferences
    try:
        prefs_result = client.table("preferences").select("*").eq("user_id", user_id).limit(1).execute()
        if prefs_result.data:
            prefs = prefs_result.data[0]
            profile.household_size = prefs.get("household_size", 1) or 1
            profile.dietary_restrictions = prefs.get("dietary_restrictions") or []
            profile.allergies = prefs.get("allergies") or []
            profile.cooking_skill_level = prefs.get("cooking_skill_level") or "intermediate"
            profile.favorite_cuisines = prefs.get("favorite_cuisines") or []
            profile.available_equipment = prefs.get("available_equipment") or []
            profile.time_budget_minutes = prefs.get("time_budget_minutes", 30) or 30
            profile.nutrition_goals = prefs.get("nutrition_goals") or []
    except Exception:
        pass  # Use defaults if preferences not available
    
    # 2. Fetch top recipes (most cooked, highest rated)
    try:
        # Get cooking log with recipe names
        logs_result = client.table("cooking_log").select(
            "recipe_id, rating, recipes(name)"
        ).eq("user_id", user_id).order("cooked_at", desc=True).limit(50).execute()
        
        if logs_result.data:
            # Aggregate by recipe
            recipe_stats: dict[str, dict] = {}
            for log in logs_result.data:
                recipe_id = log.get("recipe_id")
                if not recipe_id:
                    continue
                    
                recipe_name = log.get("recipes", {}).get("name", "Unknown")
                rating = log.get("rating") or 0
                
                if recipe_id not in recipe_stats:
                    recipe_stats[recipe_id] = {
                        "name": recipe_name,
                        "times_cooked": 0,
                        "total_rating": 0,
                        "rated_count": 0,
                    }
                
                recipe_stats[recipe_id]["times_cooked"] += 1
                if rating > 0:
                    recipe_stats[recipe_id]["total_rating"] += rating
                    recipe_stats[recipe_id]["rated_count"] += 1
            
            # Sort by times cooked and compute average rating
            top = sorted(
                recipe_stats.values(),
                key=lambda x: (-x["times_cooked"], -x.get("total_rating", 0))
            )[:5]
            
            profile.top_recipes = [
                {
                    "name": r["name"],
                    "times_cooked": r["times_cooked"],
                    "avg_rating": round(r["total_rating"] / r["rated_count"], 1) if r["rated_count"] > 0 else None,
                }
                for r in top
            ]
    except Exception:
        pass
    
    # 3. Fetch recent meals (last 7 days)
    try:
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        recent_result = client.table("cooking_log").select(
            "cooked_at, rating, recipes(name)"
        ).eq("user_id", user_id).gte("cooked_at", week_ago).order("cooked_at", desc=True).limit(10).execute()
        
        if recent_result.data:
            profile.recent_meals = [
                {
                    "name": log.get("recipes", {}).get("name", "Unknown"),
                    "date": log.get("cooked_at", "")[:10],  # Just the date part
                    "rating": log.get("rating"),
                }
                for log in recent_result.data
                if log.get("recipes")
            ]
    except Exception:
        pass
    
    # 4. Fetch top ingredients from flavor preferences
    try:
        flavor_result = client.table("flavor_preferences").select(
            "times_used, ingredients(name)"
        ).eq("user_id", user_id).order("times_used", desc=True).limit(10).execute()
        
        if flavor_result.data:
            profile.top_ingredients = [
                fp.get("ingredients", {}).get("name", "Unknown")
                for fp in flavor_result.data
                if fp.get("ingredients") and fp.get("times_used", 0) > 0
            ][:5]  # Top 5
    except Exception:
        pass
    
    profile.last_updated = datetime.utcnow()
    return profile


def format_profile_for_prompt(profile: UserProfile) -> str:
    """
    Format the user profile as a compact string for prompt injection.
    
    This goes at the top of Generate/Analyze step prompts.
    
    Args:
        profile: The pre-computed user profile
        
    Returns:
        Markdown-formatted profile string
    """
    lines = ["## USER PROFILE"]
    
    # Basic info
    basic = []
    if profile.household_size > 1:
        basic.append(f"Household: {profile.household_size}")
    if profile.dietary_restrictions:
        basic.append(f"Diet: {', '.join(profile.dietary_restrictions)}")
    if profile.allergies:
        basic.append(f"Allergies: {', '.join(profile.allergies)}")
    if basic:
        lines.append(f"- {' | '.join(basic)}")
    
    # Skill and constraints
    constraints = []
    if profile.cooking_skill_level != "intermediate":
        constraints.append(f"Skill: {profile.cooking_skill_level}")
    if profile.time_budget_minutes != 30:
        constraints.append(f"Time: {profile.time_budget_minutes} min")
    if profile.available_equipment:
        constraints.append(f"Equipment: {', '.join(profile.available_equipment[:3])}")
    if constraints:
        lines.append(f"- {' | '.join(constraints)}")
    
    # Preferences
    if profile.favorite_cuisines:
        lines.append(f"- Top cuisines: {', '.join(profile.favorite_cuisines[:3])}")
    
    if profile.nutrition_goals:
        lines.append(f"- Goals: {', '.join(profile.nutrition_goals[:3])}")
    
    # Top ingredients
    if profile.top_ingredients:
        lines.append(f"- Frequently used: {', '.join(profile.top_ingredients[:5])}")
    
    # Recent activity
    if profile.recent_meals:
        recent_str = ", ".join([
            f"{m['name']}" + (f" (★{m['rating']})" if m.get('rating') else "")
            for m in profile.recent_meals[:3]
        ])
        lines.append(f"- Recent: {recent_str}")
    elif profile.top_recipes:
        top_str = ", ".join([
            f"{r['name']}" + (f" (★{r['avg_rating']})" if r.get('avg_rating') else "")
            for r in profile.top_recipes[:3]
        ])
        lines.append(f"- Top recipes: {top_str}")
    
    return "\n".join(lines) if len(lines) > 1 else ""


# Simple in-memory cache for profiles
_profile_cache: dict[str, tuple[UserProfile, datetime]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


async def get_cached_profile(user_id: str) -> UserProfile:
    """
    Get user profile from cache or build fresh.
    
    Args:
        user_id: The user's UUID
        
    Returns:
        Cached or freshly built UserProfile
    """
    now = datetime.utcnow()
    
    if user_id in _profile_cache:
        profile, cached_at = _profile_cache[user_id]
        if (now - cached_at).total_seconds() < CACHE_TTL_SECONDS:
            return profile
    
    # Build fresh profile
    profile = await build_user_profile(user_id)
    _profile_cache[user_id] = (profile, now)
    return profile


def invalidate_profile_cache(user_id: str) -> None:
    """Invalidate cached profile for a user (call after updates)."""
    _profile_cache.pop(user_id, None)

