"""Fetch onboarding answers for audit."""
import sys
sys.path.insert(0, "src")
import json

from alfred_kitchen.db.client import get_service_client

sb = get_service_client()
USER_ID = "ec95ba05-d099-4c4e-aee6-162e80e980d3"

# Check onboarding_sessions for in-progress data
print("=== ONBOARDING_SESSIONS ===\n")
sessions = sb.table("onboarding_sessions").select("*").eq("user_id", USER_ID).execute()
if sessions.data:
    state = sessions.data[0].get("state", {})
    print(f"Phase: {state.get('phase')}")
    answers = state.get("payload_draft", {}).get("interview_answers", [])
    print(f"Interview answers in session: {len(answers)}")
    for i, ans in enumerate(answers, 1):
        print(f"  {i}. Q: {ans.get('question', 'N/A')[:60]}...")
        print(f"     A: {ans.get('answer', 'N/A')[:80]}...\n")
else:
    print("No session found")

# Check onboarding_data for completed data
print("\n=== ONBOARDING_DATA (completed) ===\n")
data = sb.table("onboarding_data").select("*").eq("user_id", USER_ID).execute()
if data.data:
    payload = data.data[0].get("payload", {})
    answers = payload.get("interview_answers", [])
    print(f"Interview answers in completed: {len(answers)}")
    
    guidance = payload.get("subdomain_guidance", {})
    print("\nSynthesized guidance:")
    for domain, text in guidance.items():
        print(f"\n**{domain}:** {text[:100]}...")
else:
    print("No completed onboarding found")
