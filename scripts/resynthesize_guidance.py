"""Re-synthesize guidance from existing interview answers."""
import sys
sys.path.insert(0, "src")
import asyncio

from alfred_kitchen.db.client import get_service_client

USER_ID = "ec95ba05-d099-4c4e-aee6-162e80e980d3"


async def resynthesize():
    from onboarding.style_interview import synthesize_guidance
    
    sb = get_service_client()
    
    # 1. Get answers from session
    sessions = sb.table("onboarding_sessions").select("state").eq("user_id", USER_ID).execute()
    if not sessions.data:
        print("[ERROR] No session found")
        return
    
    state = sessions.data[0]["state"]
    answers = state.get("payload_draft", {}).get("interview_answers", [])
    print(f"[OK] Found {len(answers)} answers in session\n")
    
    # 2. Build user context from session
    constraints = state.get("constraints", {})
    user_context = {
        "cooking_skill_level": constraints.get("cooking_skill_level", "intermediate"),
        "household_size": constraints.get("household_size", 2),
        "dietary_restrictions": constraints.get("dietary_restrictions", []),
        "available_equipment": constraints.get("available_equipment", []),
        "cuisines": state.get("cuisine_selections", []),
        "liked_ingredients": [],
    }
    
    print("User context:")
    for k, v in user_context.items():
        print(f"  {k}: {v}")
    print()
    
    # 3. Call synthesis
    print("Calling synthesis LLM...")
    guidance = await synthesize_guidance(user_context, answers)
    
    print("\n=== NEW SYNTHESIZED GUIDANCE ===\n")
    for domain in ["recipes", "meal_plans", "tasks", "shopping", "inventory"]:
        text = getattr(guidance, domain)
        print(f"**{domain}:**\n{text}\n")
    
    # 4. Update onboarding_data
    print("\nUpdating onboarding_data...")
    
    # Get existing payload
    existing = sb.table("onboarding_data").select("payload").eq("user_id", USER_ID).execute()
    if existing.data:
        payload = existing.data[0]["payload"]
    else:
        payload = {}
    
    # Update guidance and add answers
    payload["subdomain_guidance"] = {
        "recipes": guidance.recipes,
        "meal_plans": guidance.meal_plans,
        "tasks": guidance.tasks,
        "shopping": guidance.shopping,
        "inventory": guidance.inventory,
    }
    payload["interview_answers"] = answers
    
    sb.table("onboarding_data").upsert({
        "user_id": USER_ID,
        "payload": payload,
    }).execute()
    
    # 5. Also update preferences table
    print("Updating preferences table...")
    sb.table("preferences").update({
        "subdomain_guidance": payload["subdomain_guidance"]
    }).eq("user_id", USER_ID).execute()
    
    # 6. Update session payload_draft so /complete works correctly
    print("Updating session payload_draft...")
    state["payload_draft"]["subdomain_guidance"] = payload["subdomain_guidance"]
    state["payload_draft"]["interview_answers"] = answers
    sb.table("onboarding_sessions").update({
        "state": state
    }).eq("user_id", USER_ID).execute()
    
    print("\n[OK] Done! New guidance is now active in Alfred and session is updated.")


if __name__ == "__main__":
    asyncio.run(resynthesize())
