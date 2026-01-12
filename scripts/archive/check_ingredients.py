#!/usr/bin/env python3
from supabase import create_client
from dotenv import load_dotenv
import os
load_dotenv()
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

for name in ['yellow onion', 'russet potato', 'chicken thigh', 'cod', 'atlantic cod']:
    r = sb.table('ingredients').select('name').ilike('name', f'%{name}%').execute()
    matches = [x['name'] for x in r.data][:5]
    print(f'{name}: {matches}')
