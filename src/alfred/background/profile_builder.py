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
    household_adults: int = 1
    household_kids: int = 0
    household_babies: int = 0
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
    
    # SUBDOMAIN GUIDANCE (narrative preference modules per domain)
    # Keys: inventory, recipes, meal_plans, shopping, tasks
    # Values: ~200 token narrative strings
    subdomain_guidance: dict[str, str] = field(default_factory=dict)
    
    # From cooking_log aggregation
    top_recipes: list[dict] = field(default_factory=list)  # [{name, times_cooked, avg_rating}]
    recent_meals: list[dict] = field(default_factory=list)  # [{name, date, rating}]
    
    # From flavor_preferences
    top_ingredients: list[str] = field(default_factory=list)  # Most used ingredients
    
    # Metadata
    last_updated: datetime | None = None
    
    # Legacy (kept for backwards compatibility, prefer planning_rhythm)
    time_budget_minutes: int = 30


@dataclass
class KitchenDashboard:
    """
    Lightweight kitchen state summary for Think node.
    
    Provides counts and categories (not raw data) so Think can make
    informed decisions about when to plan_direct vs propose vs clarify.
    """
    
    # Inventory summary
    inventory_count: int = 0
    inventory_by_location: dict[str, int] = field(default_factory=dict)  # {"fridge": 12, "pantry": 30}
    
    # Recipe summary
    recipe_count: int = 0
    recipes_by_cuisine: dict[str, int] = field(default_factory=dict)  # {"Italian": 8, "Indian": 6}
    recipe_names_by_cuisine: dict[str, list[str]] = field(default_factory=dict)  # {"Italian": ["Pasta", "Pizza"]}
    
    # Meal plan summary (next 7 days)
    meal_plan_next_7_days: int = 0  # How many slots have meals planned
    meal_plan_days_with_meals: int = 0  # How many distinct days have at least one meal
    
    # Shopping & Tasks
    shopping_list_count: int = 0
    tasks_incomplete: int = 0
    
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
            # Hard constraints
            profile.household_adults = prefs.get("household_adults", 1) or 1
            profile.household_kids = prefs.get("household_kids", 0) or 0
            profile.household_babies = prefs.get("household_babies", 0) or 0
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
            # Subdomain guidance (narrative preference modules)
            profile.subdomain_guidance = prefs.get("subdomain_guidance") or {}
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
    total = profile.household_adults + profile.household_kids + profile.household_babies
    if total >= 1:
        portions = profile.household_adults + profile.household_kids * 0.5
        hh_parts = []
        if profile.household_adults:
            hh_parts.append(f"{profile.household_adults} adult{'s' if profile.household_adults != 1 else ''}")
        if profile.household_kids:
            hh_parts.append(f"{profile.household_kids} kid{'s' if profile.household_kids != 1 else ''}")
        if profile.household_babies:
            hh_parts.append(f"{profile.household_babies} {'babies' if profile.household_babies != 1 else 'baby'}")
        constraints.append(f"Portions: ~{portions:g} ({', '.join(hh_parts)})")
    if constraints:
        lines.append(f"**Constraints:** {' | '.join(constraints)}")

    # CAPABILITY (what they can do)
    # Only show specialty equipment in prompts (basics like oven/stovetop are assumed)
    _basic_ids = {"microwave", "oven", "stovetop", "skillet", "saucepan"}
    capability = []
    specialty_equipment = [e for e in profile.available_equipment if e not in _basic_ids]
    if specialty_equipment:
        capability.append(f"Equipment: {', '.join(specialty_equipment[:4])}")
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
    
    # PLANNING (when they cook, not when they eat)
    if profile.planning_rhythm:
        lines.append(f"**Cooking Schedule:** {'; '.join(profile.planning_rhythm[:3])}")
    
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


# =============================================================================
# Kitchen Dashboard (for Think node)
# =============================================================================


async def build_kitchen_dashboard(user_id: str) -> KitchenDashboard:
    """
    Build a lightweight kitchen state summary.
    
    Uses COUNT queries and simple aggregations - no raw data transfer.
    This is designed for Think node to understand data availability.
    
    Args:
        user_id: The user's UUID
        
    Returns:
        KitchenDashboard with counts and categories
    """
    client = get_client()
    dashboard = KitchenDashboard()
    
    # 1. Inventory count and breakdown by location
    try:
        inv_result = client.table("inventory").select("id, location").eq("user_id", user_id).execute()
        if inv_result.data:
            dashboard.inventory_count = len(inv_result.data)
            # Group by location
            location_counts: dict[str, int] = {}
            for item in inv_result.data:
                loc = item.get("location") or "unknown"
                location_counts[loc] = location_counts.get(loc, 0) + 1
            dashboard.inventory_by_location = location_counts
    except Exception:
        pass
    
    # 2. Recipe count and breakdown by cuisine (with names for Think context)
    try:
        recipe_result = client.table("recipes").select("id, name, cuisine").eq("user_id", user_id).execute()
        if recipe_result.data:
            dashboard.recipe_count = len(recipe_result.data)
            # Group by cuisine with counts and names
            cuisine_counts: dict[str, int] = {}
            cuisine_names: dict[str, list[str]] = {}
            for recipe in recipe_result.data:
                cuisine = recipe.get("cuisine") or "Other"
                name = recipe.get("name") or "Unnamed"
                cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
                if cuisine not in cuisine_names:
                    cuisine_names[cuisine] = []
                # Keep up to 3 recipe names per cuisine
                if len(cuisine_names[cuisine]) < 3:
                    cuisine_names[cuisine].append(name)
            dashboard.recipes_by_cuisine = cuisine_counts
            dashboard.recipe_names_by_cuisine = cuisine_names
    except Exception:
        pass
    
    # 3. Meal plan for next 7 days
    try:
        from datetime import date
        today = date.today().isoformat()
        week_later = (date.today() + timedelta(days=7)).isoformat()
        
        meal_result = client.table("meal_plans").select("id, date").eq(
            "user_id", user_id
        ).gte("date", today).lte("date", week_later).execute()
        
        if meal_result.data:
            dashboard.meal_plan_next_7_days = len(meal_result.data)
            # Count distinct days
            unique_dates = set(m.get("date") for m in meal_result.data if m.get("date"))
            dashboard.meal_plan_days_with_meals = len(unique_dates)
    except Exception:
        pass
    
    # 4. Shopping list count (not purchased)
    try:
        shopping_result = client.table("shopping_list").select("id").eq(
            "user_id", user_id
        ).eq("is_purchased", False).execute()
        
        if shopping_result.data:
            dashboard.shopping_list_count = len(shopping_result.data)
    except Exception:
        pass
    
    # 5. Incomplete tasks
    try:
        tasks_result = client.table("tasks").select("id").eq(
            "user_id", user_id
        ).eq("is_complete", False).execute()
        
        if tasks_result.data:
            dashboard.tasks_incomplete = len(tasks_result.data)
    except Exception:
        pass
    
    dashboard.last_updated = datetime.utcnow()
    return dashboard


def format_dashboard_for_prompt(dashboard: KitchenDashboard) -> str:
    """
    Format the kitchen dashboard as a compact string for Think prompt.
    
    Args:
        dashboard: The pre-computed kitchen dashboard
        
    Returns:
        Markdown-formatted dashboard string
    """
    lines = ["## KITCHEN SNAPSHOT"]
    
    # Inventory
    if dashboard.inventory_count > 0:
        loc_parts = []
        for loc, count in sorted(dashboard.inventory_by_location.items(), key=lambda x: -x[1]):
            loc_parts.append(f"{loc}: {count}")
        loc_str = f" ({', '.join(loc_parts[:3])})" if loc_parts else ""
        lines.append(f"- **Inventory:** {dashboard.inventory_count} items{loc_str}")
    else:
        lines.append("- **Inventory:** Empty")
    
    # Recipes (with names for better context)
    if dashboard.recipe_count > 0:
        lines.append(f"- **Recipes:** {dashboard.recipe_count} saved")
        # Show recipe names grouped by cuisine
        for cuisine, names in sorted(dashboard.recipe_names_by_cuisine.items(), key=lambda x: -len(x[1])):
            names_str = ", ".join(names[:3])
            more = f" +{dashboard.recipes_by_cuisine.get(cuisine, 0) - 3} more" if dashboard.recipes_by_cuisine.get(cuisine, 0) > 3 else ""
            lines.append(f"  - {cuisine}: {names_str}{more}")
    else:
        lines.append("- **Recipes:** None saved")
    
    # Meal Plan
    if dashboard.meal_plan_next_7_days > 0:
        lines.append(f"- **Meal Plan:** {dashboard.meal_plan_days_with_meals} of next 7 days planned ({dashboard.meal_plan_next_7_days} meals)")
    else:
        lines.append("- **Meal Plan:** Nothing planned for next 7 days")
    
    # Shopping & Tasks (combine into one line if both exist)
    extras = []
    if dashboard.shopping_list_count > 0:
        extras.append(f"Shopping: {dashboard.shopping_list_count} items")
    if dashboard.tasks_incomplete > 0:
        extras.append(f"Tasks: {dashboard.tasks_incomplete} pending")
    if extras:
        lines.append(f"- {' | '.join(extras)}")
    
    return "\n".join(lines)


# Dashboard cache (separate from profile cache, shorter TTL)
_dashboard_cache: dict[str, tuple[KitchenDashboard, datetime]] = {}
DASHBOARD_CACHE_TTL_SECONDS = 60  # 1 minute (more volatile than profile)


async def get_cached_dashboard(user_id: str) -> KitchenDashboard:
    """
    Get kitchen dashboard from cache or build fresh.
    
    Args:
        user_id: The user's UUID
        
    Returns:
        Cached or freshly built KitchenDashboard
    """
    now = datetime.utcnow()
    
    if user_id in _dashboard_cache:
        dashboard, cached_at = _dashboard_cache[user_id]
        if (now - cached_at).total_seconds() < DASHBOARD_CACHE_TTL_SECONDS:
            return dashboard
    
    # Build fresh dashboard
    dashboard = await build_kitchen_dashboard(user_id)
    _dashboard_cache[user_id] = (dashboard, now)
    return dashboard


def invalidate_dashboard_cache(user_id: str) -> None:
    """Invalidate cached dashboard for a user (call after CRUD operations)."""
    _dashboard_cache.pop(user_id, None)

