"""Check Alice's inventory."""
from alfred.db.client import get_client

client = get_client()

# Alice's user ID
alice_id = "00000000-0000-0000-0000-000000000002"

result = client.table('inventory').select('*').eq('user_id', alice_id).execute()

print(f"Alice's inventory ({len(result.data)} items):")
for item in result.data:
    print(f"  - {item['name']}: {item['quantity']} {item.get('unit', '')}")

# Check for duplicates
names = [item['name'] for item in result.data]
duplicates = [name for name in set(names) if names.count(name) > 1]
if duplicates:
    print(f"\n⚠️  DUPLICATES FOUND: {duplicates}")
else:
    print(f"\n✓ No duplicates")

