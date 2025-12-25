"""
Alfred V2 - Prompt Logger.

Logs all LLM prompts and responses to files for debugging and analysis.
Enabled via ALFRED_LOG_PROMPTS=1 or --log-prompts CLI flag.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Configuration
LOG_PROMPTS = os.getenv("ALFRED_LOG_PROMPTS", "0") == "1"
LOG_DIR = Path("prompt_logs")

# Session tracking
_session_id: str | None = None
_call_counter: int = 0


def enable_prompt_logging(enabled: bool = True) -> None:
    """Enable or disable prompt logging."""
    global LOG_PROMPTS
    LOG_PROMPTS = enabled
    if enabled:
        _ensure_log_dir()


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
    Log a prompt and response to a file.

    Args:
        node: Which node made this call (router, think, act, reply)
        model: The model used (gpt-5-mini, gpt-5, etc.)
        system_prompt: The system prompt
        user_prompt: The user prompt (includes context)
        response_model: Name of the Pydantic model expected
        response: The parsed response (optional)
        error: Any error that occurred (optional)
        config: Model config (reasoning_effort, verbosity, etc.)

    Returns:
        Path to the log file, or None if logging is disabled
    """
    if not LOG_PROMPTS:
        return None

    global _call_counter
    _call_counter += 1

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

## User Prompt

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


def get_session_log_dir() -> Path | None:
    """Get the current session's log directory, if logging is enabled."""
    if not LOG_PROMPTS:
        return None
    return _get_session_dir()


def reset_session() -> None:
    """Reset the session (for testing or new conversation)."""
    global _session_id, _call_counter
    _session_id = None
    _call_counter = 0

