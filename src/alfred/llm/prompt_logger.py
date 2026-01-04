"""
Alfred V2 - Prompt Logger.

Logs all LLM prompts and responses for debugging and analysis.

Modes:
- Local files: ALFRED_LOG_PROMPTS=1 (writes to prompt_logs/ directory)
- Supabase DB: ALFRED_LOG_TO_DB=1 (writes to prompt_logs table, auto-cleans old sessions)

Both can be enabled simultaneously.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Configuration - check both env vars and pydantic settings
def _get_config():
    """Get logging config from settings or env vars."""
    try:
        from alfred.config import settings
        return {
            "log_prompts": settings.alfred_log_prompts or os.getenv("ALFRED_LOG_PROMPTS", "0") == "1",
            "log_to_db": settings.alfred_log_to_db or os.getenv("ALFRED_LOG_TO_DB", "0") == "1",
            "keep_sessions": settings.alfred_log_keep_sessions,
        }
    except Exception:
        # Fallback to env vars if settings not available
        return {
            "log_prompts": os.getenv("ALFRED_LOG_PROMPTS", "0") == "1",
            "log_to_db": os.getenv("ALFRED_LOG_TO_DB", "0") == "1",
            "keep_sessions": int(os.getenv("ALFRED_LOG_KEEP_SESSIONS", "4")),
        }

_config = _get_config()
LOG_PROMPTS = _config["log_prompts"]
LOG_TO_DB = _config["log_to_db"]
LOG_DIR = Path("prompt_logs")
KEEP_SESSIONS = _config["keep_sessions"]

# Session tracking
_session_id: str | None = None
_call_counter: int = 0
_current_user_id: str | None = None


def enable_prompt_logging(enabled: bool = True) -> None:
    """Enable or disable prompt logging to files."""
    global LOG_PROMPTS
    LOG_PROMPTS = enabled
    if enabled:
        _ensure_log_dir()


def enable_db_logging(enabled: bool = True) -> None:
    """Enable or disable prompt logging to database."""
    global LOG_TO_DB
    LOG_TO_DB = enabled


def set_user_id(user_id: str | None) -> None:
    """Set the current user ID for logging context."""
    global _current_user_id
    _current_user_id = user_id


def _ensure_log_dir() -> None:
    """Create the log directory if it doesn't exist."""
    LOG_DIR.mkdir(exist_ok=True)


def _get_session_id() -> str:
    """Get or create a session ID for this run."""
    global _session_id
    if _session_id is None:
        _session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _session_id


def _get_session_dir() -> Path:
    """Get the directory for this session's logs."""
    session_dir = LOG_DIR / _get_session_id()
    session_dir.mkdir(exist_ok=True)
    return session_dir


def _log_to_file(
    *,
    node: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: str,
    response: Any = None,
    error: str | None = None,
    config: dict | None = None,
) -> Path | None:
    """Log to local file."""
    global _call_counter
    
    _ensure_log_dir()
    session_dir = _get_session_dir()

    # Create filename with order and node
    filename = f"{_call_counter:02d}_{node}.md"
    filepath = session_dir / filename

    # Format config info if available
    config_str = ""
    if config:
        config_parts = []
        if "reasoning_effort" in config:
            config_parts.append(f"reasoning={config['reasoning_effort']}")
        if "verbosity" in config:
            config_parts.append(f"verbosity={config['verbosity']}")
        if config_parts:
            config_str = f"\n**Config:** {', '.join(config_parts)}"

    # Format the log content as markdown for readability
    content = f"""# LLM Call: {node}

**Time:** {datetime.now().isoformat()}
**Model:** {model}
**Response Model:** {response_model}{config_str}

---

## System Prompt

```
{system_prompt}
```

---

```
{user_prompt}
```

---

## Response

"""

    if error:
        content += f"**ERROR:** {error}\n"
    elif response:
        # Try to serialize response nicely
        try:
            if hasattr(response, "model_dump"):
                response_dict = response.model_dump()
            else:
                response_dict = response
            content += f"```json\n{json.dumps(response_dict, indent=2, default=str)}\n```\n"
        except Exception as e:
            content += f"```\n{response}\n```\n\n(Serialization error: {e})\n"
    else:
        content += "(No response yet)\n"

    # Write the file
    filepath.write_text(content, encoding="utf-8")
    return filepath


def _log_to_db(
    *,
    node: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: str,
    response: Any = None,
    error: str | None = None,
    config: dict | None = None,
) -> bool:
    """Log to Supabase database."""
    try:
        from alfred.db.client import get_client
        
        client = get_client()
        session_id = _get_session_id()
        
        # Serialize response
        response_json = None
        if response:
            try:
                if hasattr(response, "model_dump"):
                    response_json = response.model_dump()
                else:
                    response_json = response
            except Exception:
                response_json = {"raw": str(response)}
        
        # Insert log entry
        data = {
            "session_id": session_id,
            "user_id": _current_user_id,
            "call_number": _call_counter,
            "node": node,
            "model": model,
            "response_model": response_model,
            "config": config,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": response_json,
            "error": error,
        }
        
        client.table("prompt_logs").insert(data).execute()
        return True
        
    except Exception as e:
        logger.warning(f"Failed to log prompt to DB: {e}")
        return False


def _cleanup_old_sessions() -> int:
    """Delete old sessions, keeping only KEEP_SESSIONS most recent."""
    try:
        from alfred.db.client import get_client
        
        client = get_client()
        
        # Call the cleanup function
        result = client.rpc("cleanup_old_prompt_logs", {"keep_sessions": KEEP_SESSIONS}).execute()
        deleted = result.data if result.data else 0
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old prompt log entries")
        
        return deleted
        
    except Exception as e:
        logger.warning(f"Failed to cleanup old prompt logs: {e}")
        return 0


def log_prompt(
    *,
    node: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: str,
    response: Any = None,
    error: str | None = None,
    config: dict | None = None,
) -> Path | None:
    """
    Log a prompt and response.

    Args:
        node: Which node made this call (router, think, act, reply)
        model: The model used (gpt-4.1-mini, gpt-4.1, etc.)
        system_prompt: The system prompt
        user_prompt: The user prompt (includes context)
        response_model: Name of the Pydantic model expected
        response: The parsed response (optional)
        error: Any error that occurred (optional)
        config: Model config (reasoning_effort, verbosity, etc.)

    Returns:
        Path to the log file (if file logging enabled), or None
    """
    if not LOG_PROMPTS and not LOG_TO_DB:
        return None

    global _call_counter
    _call_counter += 1
    
    file_path = None
    
    # Log to file if enabled
    if LOG_PROMPTS:
        file_path = _log_to_file(
            node=node,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            response=response,
            error=error,
            config=config,
        )
    
    # Log to DB if enabled
    if LOG_TO_DB:
        _log_to_db(
            node=node,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            response=response,
            error=error,
            config=config,
        )
        
        # Cleanup old sessions on first call of each session
        if _call_counter == 1:
            _cleanup_old_sessions()

    return file_path


def get_session_log_dir() -> Path | None:
    """Get the current session's log directory, if file logging is enabled."""
    if not LOG_PROMPTS:
        return None
    return _get_session_dir()


def get_session_id() -> str:
    """Get the current session ID."""
    return _get_session_id()


def reset_session() -> None:
    """Reset the session (for testing or new conversation)."""
    global _session_id, _call_counter, _current_user_id
    _session_id = None
    _call_counter = 0
    _current_user_id = None
