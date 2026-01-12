#!/usr/bin/env python3
from supabase import create_client
from dotenv import load_dotenv
import os
load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
sb = create_client(url, key)

# Check for basil
result = sb.table("ingredients").select("name, aliases").ilike("name", "%basil%").execute()
print("Ingredients containing 'basil':")
for r in result.data:
    print(f"  {r['name']} - aliases: {r.get('aliases')}")
