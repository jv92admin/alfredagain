"""Check ingredient_id mapping status in inventory."""
from alfred.db.client import get_client
from dotenv import load_dotenv

load_dotenv()

sb = get_client()

# Check inventory items with and without ingredient_id
r = sb.table('inventory').select('name, ingredient_id, category').order('created_at', desc=True).limit(50).execute()

mapped = 0
unmapped = 0
print('Recent inventory items:')
for item in r.data:
    has_id = item.get('ingredient_id') is not None
    status = 'MAPPED' if has_id else 'UNMAPPED'
    cat = item.get('category') or '-'
    name = item.get('name', '?')
    print(f'  [{status}] {name} (cat: {cat})')
    if has_id:
        mapped += 1
    else:
        unmapped += 1

print(f'\nSummary: {mapped} mapped, {unmapped} unmapped out of {len(r.data)} items')


