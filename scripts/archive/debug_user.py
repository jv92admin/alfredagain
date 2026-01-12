from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

# Check which user has recipes
recipes = sb.table('recipes').select('id, name, user_id').limit(3).execute()
print('User IDs with recipes:')
for r in recipes.data:
    print(f"  {r['user_id']} - {r['name'][:40]}...")

# Get first user
users = sb.table('users').select('id').limit(1).execute()
print(f"\nFirst user in users table: {users.data[0]['id']}")
