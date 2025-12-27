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
    
    # HARD CONSTRAINTS (never violated)
    household_size: int = 1
    dietary_restrictions: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    
    # CAPABILITY (what they can do)
    cooking_skill_level: str = "intermediate"
    available_equipment: list[str] = field(default_factory=list)
    
    # TASTE (what they like)
    favorite_cuisines: list[str] = field(default_factory=list)
    nutrition_goals: list[str] = field(default_factory=list)
    
    # PLANNING (how they want to cook - freeform, 2-3 tags)
    planning_rhythm: list[str] = field(default_factory=list)
    
    # VIBES (current interests - freeform, up to 5 tags)
    current_vibes: list[str] = field(default_factory=list)
    
    # From cooking_log aggregation
    top_recipes: list[dict] = field(default_factory=list)  # [{name, times_cooked, avg_rating}]
    recent_meals: list[dict] = field(default_factory=list)  # [{name, date, rating}]
    
    # From flavor_preferences
    top_ingredients: list[str] = field(default_factory=list)  # Most used ingredients
    
    # Metadata
    last_updated: datetime | None = None
    
    # Legacy (kept for backwards compatibility, prefer planning_rhythm)
    time_budget_minutes: int = 30


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
            # Hard constraints
            profile.household_size = prefs.get("household_size", 1) or 1
            profile.dietary_restrictions = prefs.get("dietary_restrictions") or []
            profile.allergies = prefs.get("allergies") or []
            # Capability
            profile.cooking_skill_level = prefs.get("cooking_skill_level") or "intermediate"
            profile.available_equipment = prefs.get("available_equipment") or []
            # Taste
            profile.favorite_cuisines = prefs.get("favorite_cuisines") or []
            profile.nutrition_goals = prefs.get("nutrition_goals") or []
            # Planning & Vibes (new flexible fields)
            profile.planning_rhythm = prefs.get("planning_rhythm") or []
            profile.current_vibes = prefs.get("current_vibes") or []
            # Legacy
            profile.time_budget_minutes = prefs.get("time_budget_minutes", 30) or 30
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
    
    # HARD CONSTRAINTS (always show, these are non-negotiable)
    constraints = []
    if profile.dietary_restrictions:
        constraints.append(f"Diet: {', '.join(profile.dietary_restrictions)}")
    if profile.allergies:
        constraints.append(f"Allergies: {', '.join(profile.allergies)}")
    if profile.household_size > 1:
        constraints.append(f"Portions: {profile.household_size}")
    if constraints:
        lines.append(f"**Constraints:** {' | '.join(constraints)}")
    
    # CAPABILITY (what they can do)
    capability = []
    if profile.available_equipment:
        capability.append(f"Equipment: {', '.join(profile.available_equipment[:4])}")
    if profile.cooking_skill_level != "intermediate":
        capability.append(f"Skill: {profile.cooking_skill_level}")
    if capability:
        lines.append(f"**Has:** {' | '.join(capability)}")
    
    # TASTE (what they like)
    tastes = []
    if profile.favorite_cuisines:
        tastes.append(f"Cuisines: {', '.join(profile.favorite_cuisines[:4])}")
    if profile.nutrition_goals:
        tastes.append(f"Goals: {', '.join(profile.nutrition_goals[:3])}")
    if tastes:
        lines.append(f"**Likes:** {' | '.join(tastes)}")
    
    # PLANNING (how they want to cook right now)
    if profile.planning_rhythm:
        lines.append(f"**Planning:** {'; '.join(profile.planning_rhythm[:3])}")
    
    # VIBES (current culinary interests)
    if profile.current_vibes:
        lines.append(f"**Vibes:** {'; '.join(profile.current_vibes[:5])}")
    
    # Recent activity (context from cooking history)
    if profile.recent_meals:
        recent_str = ", ".join([
            f"{m['name']}" + (f" (★{m['rating']})" if m.get('rating') else "")
            for m in profile.recent_meals[:3]
        ])
        lines.append(f"**Recent:** {recent_str}")
    elif profile.top_recipes:
        top_str = ", ".join([
            f"{r['name']}" + (f" (★{r['avg_rating']})" if r.get('avg_rating') else "")
            for r in profile.top_recipes[:3]
        ])
        lines.append(f"**Favorites:** {top_str}")
    
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

