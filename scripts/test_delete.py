"""Test delete operation directly."""
from alfred.db.client import get_client

c = get_client()
alice_id = "00000000-0000-0000-0000-000000000002"
older_id = "eb5445e1-5276-4226-844c-74e167189378"

print(f"Deleting recipe {older_id}")
print(f"With user_id filter: {alice_id}")

try:
    result = c.table("recipes").delete().eq("id", older_id).eq("user_id", alice_id).execute()
    print(f"Result data: {result.data}")
    print(f"Count attr: {getattr(result, 'count', None)}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

# Check if it's still there
remaining = c.table("recipes").select("id, name").eq("user_id", alice_id).execute()
print(f"\nRemaining recipes for Alice:")
for r in remaining.data:
    print(f"  {r['id']} - {r['name']}")

