"""
Test script: Apply onboarding payload to preferences table.

Run: python scripts/test_apply_onboarding.py
"""

import sys
sys.path.insert(0, "src")

from alfred_kitchen.db.client import get_service_client

USER_ID = "ec95ba05-d099-4c4e-aee6-162e80e980d3"


def test_apply():
    client = get_service_client()
    
    # 1. Try onboarding_data first (completed flow)
    result = client.table("onboarding_data").select("payload").eq("user_id", USER_ID).limit(1).execute()
    
    if result.data:
        payload = result.data[0]["payload"]
        print("✅ Found payload in onboarding_data (completed)")
    else:
        # 2. Fall back to onboarding_sessions (in-progress)
        result = client.table("onboarding_sessions").select("state").eq("user_id", USER_ID).limit(1).execute()
        
        if not result.data:
            print("❌ No onboarding data found for user")
            return
        
        print("✅ Found payload in onboarding_sessions (in-progress)")
        state = result.data[0]["state"]
        # Build payload from state
        payload = {
            "constraints": state.get("constraints", {}),
            "cuisine_preferences": state.get("cuisine_selections", []),
            "subdomain_guidance": state.get("payload_draft", {}).get("subdomain_guidance", {}),
        }
    
    constraints = payload.get("constraints", {})
    print(f"   Constraints: {constraints}")
    print(f"   Cuisines: {payload.get('cuisine_preferences', [])}")
    print(f"   Subdomain guidance keys: {list(payload.get('subdomain_guidance', {}).keys())}")
    
    # 3. Build preferences data
    prefs_data = {
        "user_id": USER_ID,
        "dietary_restrictions": constraints.get("dietary_restrictions", []),
        "allergies": constraints.get("allergies", []),
        "cooking_skill_level": constraints.get("cooking_skill_level", "intermediate"),
        "household_size": constraints.get("household_size", 1),
        "available_equipment": constraints.get("available_equipment", []),
        "favorite_cuisines": payload.get("cuisine_preferences", []),
        "subdomain_guidance": payload.get("subdomain_guidance", {}),
    }
    
    print("\n📝 Preferences to apply:")
    for key, value in prefs_data.items():
        if key != "user_id":
            display = value if not isinstance(value, dict) else f"{len(value)} keys"
            print(f"   {key}: {display}")
    
    # 4. UPSERT to preferences
    try:
        client.table("preferences").upsert(
            prefs_data,
            on_conflict="user_id"
        ).execute()
        print("\n✅ Successfully applied to preferences table!")
        
        # 5. Also save to onboarding_data to mark as complete
        from datetime import datetime
        client.table("onboarding_data").upsert({
            "user_id": USER_ID,
            "payload": payload,
            "version": "1.0",
            "completed_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id").execute()
        print("✅ Marked onboarding as complete in onboarding_data table")
        
        # 5. Verify
        verify = client.table("preferences").select("*").eq("user_id", USER_ID).limit(1).execute()
        if verify.data:
            print("\n🔍 Verification - preferences now contains:")
            prefs = verify.data[0]
            print(f"   cooking_skill_level: {prefs.get('cooking_skill_level')}")
            print(f"   household_size: {prefs.get('household_size')}")
            print(f"   dietary_restrictions: {prefs.get('dietary_restrictions')}")
            print(f"   allergies: {prefs.get('allergies')}")
            print(f"   available_equipment: {prefs.get('available_equipment')}")
            print(f"   favorite_cuisines: {prefs.get('favorite_cuisines')}")
            guidance = prefs.get('subdomain_guidance', {})
            print(f"   subdomain_guidance: {list(guidance.keys()) if guidance else 'empty'}")
            
    except Exception as e:
        print(f"\n❌ Failed to apply: {e}")


if __name__ == "__main__":
    test_apply()
