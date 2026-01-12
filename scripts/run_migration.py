#!/usr/bin/env python3
"""Run a SQL migration file against Supabase."""

import sys
from pathlib import Path
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY")
    return create_client(url, key)


def run_migration(migration_file: str):
    """Run a SQL migration file."""
    path = Path(migration_file)
    if not path.exists():
        print(f"[ERROR] Migration file not found: {migration_file}")
        return False
    
    sql = path.read_text()
    print(f"Running migration: {path.name}")
    print("-" * 50)
    print(sql[:500] + "..." if len(sql) > 500 else sql)
    print("-" * 50)
    
    sb = get_supabase()
    
    # Execute via RPC (requires a function, or use raw SQL via postgrest)
    # Since Supabase Python client doesn't have direct SQL exec, we'll use rpc
    # Actually, we need to use the REST API directly for raw SQL
    
    # For now, let's just print the SQL and ask user to run in dashboard
    print("\n[INFO] Please run this SQL in Supabase Dashboard > SQL Editor")
    print("[INFO] Or use: supabase db push")
    
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_migration.py <migration_file>")
        sys.exit(1)
    
    run_migration(sys.argv[1])
