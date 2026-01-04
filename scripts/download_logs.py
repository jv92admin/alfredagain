#!/usr/bin/env python3
"""
Download prompt logs from Supabase and create readable markdown files.

Usage:
    python scripts/download_logs.py                    # List available sessions
    python scripts/download_logs.py SESSION_ID        # Download specific session
    python scripts/download_logs.py --latest          # Download most recent session
    python scripts/download_logs.py --latest 3        # Download 3 most recent sessions
    python scripts/download_logs.py --user USER_ID    # Filter by user
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alfred.db.client import get_client

OUTPUT_DIR = Path("prompt_logs_downloaded")


def list_sessions(user_id: str | None = None, limit: int = 20):
    """List available sessions."""
    client = get_client()
    
    query = client.table("prompt_logs").select(
        "session_id, user_id, created_at"
    )
    
    if user_id:
        query = query.eq("user_id", user_id)
    
    # Get distinct sessions with their first call time
    response = query.order("created_at", desc=True).execute()
    
    # Group by session
    sessions = {}
    for row in response.data:
        sid = row["session_id"]
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "user_id": row["user_id"],
                "started_at": row["created_at"],
                "call_count": 0,
            }
        sessions[sid]["call_count"] += 1
    
    # Sort by start time descending
    sorted_sessions = sorted(
        sessions.values(), 
        key=lambda x: x["started_at"], 
        reverse=True
    )[:limit]
    
    print(f"\n📋 Available Sessions ({len(sorted_sessions)} shown):\n")
    print(f"{'Session ID':<20} {'User ID':<40} {'Calls':<8} {'Started'}")
    print("-" * 90)
    
    for s in sorted_sessions:
        user_short = s["user_id"][:8] + "..." if s["user_id"] else "N/A"
        started = s["started_at"][:19].replace("T", " ")
        print(f"{s['session_id']:<20} {user_short:<40} {s['call_count']:<8} {started}")
    
    print(f"\nTo download: python scripts/download_logs.py SESSION_ID")
    return sorted_sessions


def download_session(session_id: str, output_dir: Path | None = None):
    """Download a session and create markdown files."""
    client = get_client()
    
    # Fetch all logs for this session
    response = client.table("prompt_logs").select("*").eq(
        "session_id", session_id
    ).order("call_number").execute()
    
    if not response.data:
        print(f"❌ No logs found for session: {session_id}")
        return False
    
    logs = response.data
    print(f"\n📥 Downloading {len(logs)} logs from session {session_id}...")
    
    # Create output directory
    if output_dir is None:
        output_dir = OUTPUT_DIR / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for log in logs:
        filename = f"{log['call_number']:02d}_{log['node']}.md"
        filepath = output_dir / filename
        
        # Format config
        config_str = ""
        if log.get("config"):
            config_parts = []
            config = log["config"]
            if "reasoning_effort" in config:
                config_parts.append(f"reasoning={config['reasoning_effort']}")
            if "verbosity" in config:
                config_parts.append(f"verbosity={config['verbosity']}")
            if config_parts:
                config_str = f"\n**Config:** {', '.join(config_parts)}"
        
        # Format response
        response_content = ""
        if log.get("error"):
            response_content = f"**ERROR:** {log['error']}\n"
        elif log.get("response"):
            try:
                response_content = f"```json\n{json.dumps(log['response'], indent=2, default=str)}\n```\n"
            except Exception as e:
                response_content = f"```\n{log['response']}\n```\n\n(Serialization error: {e})\n"
        else:
            response_content = "(No response)\n"
        
        # Build markdown content
        content = f"""# LLM Call: {log['node']}

**Time:** {log['created_at']}
**Model:** {log['model']}
**Response Model:** {log.get('response_model', 'N/A')}{config_str}
**Session:** {session_id}
**User:** {log.get('user_id', 'N/A')}

---

## System Prompt

```
{log.get('system_prompt', '(none)')}
```

---

## User Prompt

```
{log.get('user_prompt', '(none)')}
```

---

## Response

{response_content}
"""
        
        filepath.write_text(content, encoding="utf-8")
        print(f"  ✅ {filename}")
    
    print(f"\n✨ Downloaded to: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Download prompt logs from Supabase"
    )
    parser.add_argument(
        "session_id", 
        nargs="?", 
        help="Session ID to download (e.g., 20260104_160725)"
    )
    parser.add_argument(
        "--latest", 
        nargs="?",
        const=1,
        type=int,
        metavar="N",
        help="Download N most recent sessions (default: 1)"
    )
    parser.add_argument(
        "--user", 
        help="Filter by user ID"
    )
    parser.add_argument(
        "--list", 
        action="store_true",
        help="List available sessions"
    )
    
    args = parser.parse_args()
    
    # If no args, list sessions
    if not args.session_id and not args.latest and not args.list:
        list_sessions(user_id=args.user)
        return
    
    # List sessions
    if args.list:
        list_sessions(user_id=args.user)
        return
    
    # Download specific session
    if args.session_id:
        download_session(args.session_id)
        return
    
    # Download latest N sessions
    if args.latest:
        sessions = list_sessions(user_id=args.user, limit=args.latest)
        for s in sessions[:args.latest]:
            download_session(s["session_id"])


if __name__ == "__main__":
    main()

