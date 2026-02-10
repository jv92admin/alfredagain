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

# Configuration
LOG_DIR = Path("prompt_logs")

# These are checked dynamically to pick up env vars set after import
def _is_log_prompts_enabled() -> bool:
    """Check if file logging is enabled (dynamic check)."""
    return os.getenv("ALFRED_LOG_PROMPTS", "0") == "1"

def _is_log_to_db_enabled() -> bool:
    """Check if DB logging is enabled (dynamic check)."""
    return os.getenv("ALFRED_LOG_TO_DB", "0") == "1"

def _get_keep_sessions() -> int:
    """Get number of sessions to keep."""
    return int(os.getenv("ALFRED_LOG_KEEP_SESSIONS", "4"))

# Mutable state for runtime overrides
_log_prompts_override: bool | None = None
_log_to_db_override: bool | None = None

def is_logging_enabled() -> bool:
    """Check if any logging is enabled."""
    prompts = _log_prompts_override if _log_prompts_override is not None else _is_log_prompts_enabled()
    db = _log_to_db_override if _log_to_db_override is not None else _is_log_to_db_enabled()
    return prompts or db

def is_file_logging_enabled() -> bool:
    """Check if file logging is enabled."""
    return _log_prompts_override if _log_prompts_override is not None else _is_log_prompts_enabled()

def is_db_logging_enabled() -> bool:
    """Check if DB logging is enabled."""
    return _log_to_db_override if _log_to_db_override is not None else _is_log_to_db_enabled()

# Session tracking
_session_id: str | None = None
_call_counter: int = 0
_current_user_id: str | None = None


def enable_prompt_logging(enabled: bool = True) -> None:
    """Enable or disable prompt logging to files."""
    global _log_prompts_override
    _log_prompts_override = enabled
    if enabled:
        _ensure_log_dir()
    logger.info(f"Prompt file logging: {'enabled' if enabled else 'disabled'}")


def enable_db_logging(enabled: bool = True) -> None:
    """Enable or disable prompt logging to database."""
    global _log_to_db_override
    _log_to_db_override = enabled
    logger.info(f"Prompt DB logging: {'enabled' if enabled else 'disabled'}")


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
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
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
    
    # Format token usage if available
    token_str = ""
    if prompt_tokens is not None or completion_tokens is not None:
        token_parts = []
        if prompt_tokens is not None:
            token_parts.append(f"input={prompt_tokens:,}")
        if completion_tokens is not None:
            token_parts.append(f"output={completion_tokens:,}")
        total = (prompt_tokens or 0) + (completion_tokens or 0)
        token_parts.append(f"total={total:,}")
        token_str = f"\n**Tokens:** {', '.join(token_parts)}"

    # Format the log content as markdown for readability
    content = f"""# LLM Call: {node}

**Time:** {datetime.now().isoformat()}
**Model:** {model}
**Response Model:** {response_model}{config_str}{token_str}

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

    # Write the file (replace surrogates so logging never crashes)
    filepath.write_text(content, encoding="utf-8", errors="replace")
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
        from alfred_kitchen.db.client import get_client
        
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
    """Delete old sessions, keeping only the configured number of most recent."""
    try:
        from alfred_kitchen.db.client import get_client
        
        client = get_client()
        keep = _get_keep_sessions()
        
        # Call the cleanup function
        result = client.rpc("cleanup_old_prompt_logs", {"keep_sessions": keep}).execute()
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
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
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
        prompt_tokens: Token count for input (from API response)
        completion_tokens: Token count for output (from API response)

    Returns:
        Path to the log file (if file logging enabled), or None
    """
    if not is_logging_enabled():
        return None

    global _call_counter
    _call_counter += 1
    
    file_path = None
    
    # Log to file if enabled
    if is_file_logging_enabled():
        file_path = _log_to_file(
            node=node,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            response=response,
            error=error,
            config=config,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    
    # Log to DB if enabled
    if is_db_logging_enabled():
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
    if not is_file_logging_enabled():
        return None
    return _get_session_dir()


def get_session_id() -> str:
    """Get the current session ID."""
    return _get_session_id()


def reset_session() -> None:
    """Reset the session (for testing or new conversation)."""
    global _session_id, _call_counter, _current_user_id, _log_prompts_override, _log_to_db_override
    old_session = _session_id
    _session_id = None
    _call_counter = 0
    _current_user_id = None
    # Don't reset overrides - they're intentional runtime settings
    logger.info(f"Prompt logger session reset (was: {old_session})")


def get_logging_status() -> dict:
    """Get current logging status for debugging."""
    return {
        "session_id": _session_id,
        "call_counter": _call_counter,
        "user_id": _current_user_id,
        "file_logging": is_file_logging_enabled(),
        "db_logging": is_db_logging_enabled(),
        "env_ALFRED_LOG_PROMPTS": os.getenv("ALFRED_LOG_PROMPTS"),
        "env_ALFRED_LOG_TO_DB": os.getenv("ALFRED_LOG_TO_DB"),
    }
