"""Audit the full onboarding flow for correctness."""
import sys
sys.path.insert(0, "src")

from alfred_kitchen.db.client import get_service_client
from onboarding.payload import build_payload_from_state, OnboardingPayload
from onboarding.state import OnboardingState

USER_ID = "ec95ba05-d099-4c4e-aee6-162e80e980d3"


def audit():
    sb = get_service_client()
    
    print("=" * 60)
    print("ONBOARDING FLOW AUDIT")
    print("=" * 60)
    
    # 1. Check session state
    print("\n[1] SESSION STATE (onboarding_sessions)")
    sessions = sb.table("onboarding_sessions").select("state").eq("user_id", USER_ID).execute()
    if not sessions.data:
        print("   - No session found")
        return
    
    state_dict = sessions.data[0]["state"]
    state = OnboardingState.from_dict(state_dict)
    
    print(f"   - Phase: {state.current_phase}")
    print(f"   - Constraints: {state.constraints}")
    print(f"   - Cuisines: {len(state.cuisine_selections)} selected")
    print(f"   - Interview answers in payload_draft: {len(state.payload_draft.get('interview_answers', []))}")
    print(f"   - Guidance in payload_draft: {list(state.payload_draft.get('subdomain_guidance', {}).keys())}")
    
    # 2. Build payload from state (simulates /complete endpoint)
    print("\n[2] BUILD PAYLOAD FROM STATE")
    payload = build_payload_from_state(state)
    payload_dict = payload.to_dict()
    
    print(f"   - preferences key: {list(payload_dict.get('preferences', {}).keys())}")
    print(f"   - subdomain_guidance keys: {list(payload_dict.get('subdomain_guidance', {}).keys())}")
    print(f"   - interview_answers count: {len(payload_dict.get('interview_answers', []))}")
    print(f"   - cuisine_preferences count: {len(payload_dict.get('cuisine_preferences', []))}")
    
    # 3. Check what would be written to preferences table
    print("\n[3] PREFERENCES TABLE DATA (what /complete would write)")
    prefs = payload_dict.get("preferences", {})
    prefs_data = {
        "dietary_restrictions": prefs.get("dietary_restrictions", []),
        "allergies": prefs.get("allergies", []),
        "cooking_skill_level": prefs.get("cooking_skill_level", "intermediate"),
        "household_size": prefs.get("household_size", 1),
        "available_equipment": prefs.get("available_equipment", []),
        "favorite_cuisines": payload_dict.get("cuisine_preferences", []),
        "subdomain_guidance": payload_dict.get("subdomain_guidance", {}),
    }
    
    for key, value in prefs_data.items():
        if key == "subdomain_guidance":
            print(f"   - {key}: {list(value.keys())}")
            for domain, text in value.items():
                preview = text[:50] + "..." if len(text) > 50 else text
                print(f"       {domain}: {preview}")
        else:
            print(f"   - {key}: {value}")
    
    # 4. Check current preferences table
    print("\n[4] CURRENT PREFERENCES TABLE")
    existing = sb.table("preferences").select("*").eq("user_id", USER_ID).execute()
    if existing.data:
        current = existing.data[0]
        print(f"   - household_size: {current.get('household_size')}")
        print(f"   - cooking_skill_level: {current.get('cooking_skill_level')}")
        print(f"   - available_equipment: {current.get('available_equipment')}")
        print(f"   - subdomain_guidance keys: {list(current.get('subdomain_guidance', {}).keys())}")
    else:
        print("   - No preferences found")
    
    # 5. Validate flow
    print("\n[5] VALIDATION")
    issues = []
    
    if not state.payload_draft.get("interview_answers"):
        issues.append("No interview_answers in session payload_draft")
    
    if not state.payload_draft.get("subdomain_guidance"):
        issues.append("No subdomain_guidance in session payload_draft")
    
    if not payload_dict.get("interview_answers"):
        issues.append("interview_answers NOT copied to final payload")
    
    if not payload_dict.get("subdomain_guidance"):
        issues.append("subdomain_guidance NOT in final payload")
    
    guidance = payload_dict.get("subdomain_guidance", {})
    recipes_text = guidance.get("recipes", "")
    # Check for personalization markers (equipment, dislikes, etc.)
    personalization_markers = ["air fryer", "brussels", "anchovies", "Instant Pot", "rice cooker"]
    has_personalization = any(marker.lower() in recipes_text.lower() for marker in personalization_markers)
    if not has_personalization:
        issues.append("recipes guidance missing personalization markers (equipment, dislikes)")
    
    if issues:
        print("   ISSUES FOUND:")
        for issue in issues:
            print(f"   [!] {issue}")
    else:
        print("   [OK] All checks passed!")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    audit()
