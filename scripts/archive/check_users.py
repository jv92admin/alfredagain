"""Check if test users exist in database."""
from alfred_kitchen.db.client import get_client
import bcrypt

client = get_client()
result = client.table('users').select('id, email, display_name, password_hash').execute()

print("Users in database:")
for u in result.data:
    email = u.get('email', 'no-email')
    pw_hash = u.get('password_hash')
    has_hash = "YES" if pw_hash else "NO"
    print(f"  - {email}: password_hash={has_hash}")
    
    # Test password if hash exists
    if pw_hash:
        try:
            matches = bcrypt.checkpw(b'alfred123', pw_hash.encode())
            print(f"    -> 'alfred123' matches: {matches}")
        except Exception as e:
            print(f"    -> Error checking password: {e}")

print(f"\nTotal users: {len(result.data)}")

