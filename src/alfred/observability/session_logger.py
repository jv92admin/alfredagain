"""
Alfred V3 - Session Logger.

Lightweight observability for debugging and future production use.

Features:
- One JSONL file per session (easy to parse, tail -f friendly)
- Node entry/exit with timing
- Smart truncation of large objects
- Entity lifecycle events
- LLM call summaries (not full prompts)

Usage:
    from alfred.observability.session_logger import SessionLogger
    
    logger = SessionLogger()  # Creates timestamped log file
    logger.node_enter("think", {"goal": "Plan dinner"})
    logger.node_exit("think", {"steps": 3}, duration_ms=150)
    
    # At end of session
    logger.close()

Log format (JSONL):
    {"ts": "2026-01-01T17:30:00", "event": "node_enter", "node": "think", ...}
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any


# =============================================================================
# Configuration
# =============================================================================

# Where to write logs
LOG_DIR = Path("session_logs")

# Max string length before truncation
MAX_STRING_LEN = 200

# Max list items to show
MAX_LIST_ITEMS = 5

# Max dict keys to show
MAX_DICT_KEYS = 10

# Fields to always truncate heavily (contain large content)
HEAVY_FIELDS = {
    "instructions", "description", "content", "data", "prompt",
    "system_prompt", "user_prompt", "response", "full_text",
}


# =============================================================================
# Smart Truncation
# =============================================================================


def _truncate_value(value: Any, depth: int = 0) -> Any:
    """
    Smart truncation of values for logging.
    
    - Strings > MAX_STRING_LEN get truncated with "..."
    - Lists > MAX_LIST_ITEMS show first N + count
    - Dicts > MAX_DICT_KEYS show first N keys + count
    - Nested structures respect depth limit
    """
    if depth > 3:
        return "<nested>"
    
    if value is None:
        return None
    
    if isinstance(value, str):
        if len(value) > MAX_STRING_LEN:
            return value[:MAX_STRING_LEN] + f"... ({len(value)} chars)"
        return value
    
    if isinstance(value, (int, float, bool)):
        return value
    
    if isinstance(value, list):
        if len(value) == 0:
            return []
        if len(value) <= MAX_LIST_ITEMS:
            return [_truncate_value(v, depth + 1) for v in value]
        truncated = [_truncate_value(v, depth + 1) for v in value[:MAX_LIST_ITEMS]]
        return truncated + [f"... +{len(value) - MAX_LIST_ITEMS} more"]
    
    if isinstance(value, dict):
        if len(value) == 0:
            return {}
        result = {}
        keys = list(value.keys())[:MAX_DICT_KEYS]
        for k in keys:
            v = value[k]
            # Extra truncation for known heavy fields
            if k in HEAVY_FIELDS and isinstance(v, str) and len(v) > 50:
                result[k] = v[:50] + f"... ({len(v)} chars)"
            else:
                result[k] = _truncate_value(v, depth + 1)
        if len(value) > MAX_DICT_KEYS:
            result["_truncated"] = f"+{len(value) - MAX_DICT_KEYS} keys"
        return result
    
    # For Pydantic models and other objects
    if hasattr(value, "model_dump"):
        return _truncate_value(value.model_dump(), depth)
    if hasattr(value, "__dict__"):
        return _truncate_value(vars(value), depth)
    
    # Fallback
    return str(value)[:MAX_STRING_LEN]


def _summarize_entities(entities: list[dict] | None) -> dict | None:
    """Summarize entities list to just counts and IDs."""
    if not entities:
        return None
    
    by_type: dict[str, list[str]] = {}
    for e in entities:
        etype = e.get("type", "unknown")
        eid = e.get("id", "?")
        if etype not in by_type:
            by_type[etype] = []
        by_type[etype].append(eid[:8])  # Just first 8 chars of UUID
    
    return {t: {"count": len(ids), "ids": ids[:3]} for t, ids in by_type.items()}


# =============================================================================
# Session Logger
# =============================================================================


class SessionLogger:
    """
    Per-session logger that writes JSONL to a file.
    
    Thread-safe (uses append mode).
    """
    
    def __init__(self, session_id: str | None = None, enabled: bool = True):
        """
        Initialize session logger.
        
        Args:
            session_id: Optional custom session ID. Default: timestamp-based.
            enabled: If False, all logging is no-op.
        """
        self.enabled = enabled
        
        # Always initialize tracking attributes (needed even when disabled)
        self._node_start_times: dict[str, float] = {}
        self._turn_count = 0
        
        if not enabled:
            self.log_file = None
            return
        
        # Create log directory
        LOG_DIR.mkdir(exist_ok=True)
        
        # Generate session ID
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.session_id = session_id
        self.log_path = LOG_DIR / f"session_{session_id}.jsonl"
        self.log_file = open(self.log_path, "a", encoding="utf-8")
        
        # Log session start
        self._write({
            "event": "session_start",
            "session_id": session_id,
            "version": "v3",
        })
    
    def _write(self, data: dict) -> None:
        """Write a log entry."""
        if not self.enabled or self.log_file is None:
            return
        
        entry = {
            "ts": datetime.now().isoformat(),
            **data,
        }
        self.log_file.write(json.dumps(entry, default=str) + "\n")
        self.log_file.flush()  # Ensure it's written for tail -f
    
    # =========================================================================
    # Node Events
    # =========================================================================
    
    def node_enter(self, node: str, inputs: dict | None = None) -> None:
        """Log node entry."""
        self._node_start_times[node] = time.time()
        
        self._write({
            "event": "node_enter",
            "node": node,
            "turn": self._turn_count,
            "inputs": _truncate_value(inputs) if inputs else None,
        })
    
    def node_exit(
        self, 
        node: str, 
        outputs: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Log node exit with duration."""
        start = self._node_start_times.pop(node, None)
        duration_ms = int((time.time() - start) * 1000) if start else None
        
        self._write({
            "event": "node_exit",
            "node": node,
            "turn": self._turn_count,
            "duration_ms": duration_ms,
            "outputs": _truncate_value(outputs) if outputs else None,
            "error": error,
        })
    
    # =========================================================================
    # Turn Events
    # =========================================================================
    
    def turn_start(self, user_message: str, mode: str | None = None) -> None:
        """Log start of a conversation turn."""
        self._turn_count += 1
        
        self._write({
            "event": "turn_start",
            "turn": self._turn_count,
            "user_message": user_message[:200] + "..." if len(user_message) > 200 else user_message,
            "mode": mode,
        })
    
    def turn_end(
        self, 
        response: str,
        entities_created: list[dict] | None = None,
        entities_updated: list[dict] | None = None,
    ) -> None:
        """Log end of a conversation turn."""
        self._write({
            "event": "turn_end",
            "turn": self._turn_count,
            "response_len": len(response),
            "response_preview": response[:150] + "..." if len(response) > 150 else response,
            "entities_created": _summarize_entities(entities_created),
            "entities_updated": _summarize_entities(entities_updated),
        })
    
    # =========================================================================
    # LLM Events
    # =========================================================================
    
    def llm_call(
        self,
        node: str,
        model: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Log LLM call (summary, not full prompt)."""
        self._write({
            "event": "llm_call",
            "node": node,
            "turn": self._turn_count,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "duration_ms": duration_ms,
        })
    
    # =========================================================================
    # Entity Events
    # =========================================================================
    
    def entity_state_change(
        self,
        entity_id: str,
        entity_type: str,
        old_state: str | None,
        new_state: str,
        reason: str | None = None,
    ) -> None:
        """Log entity state transition."""
        self._write({
            "event": "entity_state_change",
            "turn": self._turn_count,
            "entity_id": entity_id[:8],  # Short ID
            "entity_type": entity_type,
            "old_state": old_state,
            "new_state": new_state,
            "reason": reason,
        })
    
    def entity_gc(self, removed_count: int, removed_ids: list[str]) -> None:
        """Log entity garbage collection."""
        self._write({
            "event": "entity_gc",
            "turn": self._turn_count,
            "removed_count": removed_count,
            "removed_ids": [i[:8] for i in removed_ids[:5]],
        })
    
    # =========================================================================
    # Step Events
    # =========================================================================
    
    def step_start(
        self,
        step_index: int,
        step_type: str,
        subdomain: str,
        group: int,
        description: str,
    ) -> None:
        """Log step start."""
        self._write({
            "event": "step_start",
            "turn": self._turn_count,
            "step": step_index,
            "type": step_type,
            "subdomain": subdomain,
            "group": group,
            "description": description[:100],
        })
    
    def step_complete(
        self,
        step_index: int,
        result_summary: str,
        record_count: int | None = None,
        tool_calls: int | None = None,
    ) -> None:
        """Log step completion."""
        self._write({
            "event": "step_complete",
            "turn": self._turn_count,
            "step": step_index,
            "result_summary": result_summary[:150],
            "record_count": record_count,
            "tool_calls": tool_calls,
        })
    
    # =========================================================================
    # Tool Events
    # =========================================================================
    
    def tool_call(
        self,
        tool: str,
        table: str,
        record_count: int | None = None,
        error: str | None = None,
    ) -> None:
        """Log CRUD tool call."""
        self._write({
            "event": "tool_call",
            "turn": self._turn_count,
            "tool": tool,
            "table": table,
            "record_count": record_count,
            "error": error,
        })
    
    # =========================================================================
    # Custom Events
    # =========================================================================
    
    def log(self, event_type: str, **kwargs) -> None:
        """Log custom event."""
        self._write({
            "event": event_type,
            "turn": self._turn_count,
            **_truncate_value(kwargs),
        })
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    def close(self) -> str | None:
        """Close the log file. Returns log path."""
        if self.log_file:
            self._write({"event": "session_end", "total_turns": self._turn_count})
            self.log_file.close()
            return str(self.log_path)
        return None


# =============================================================================
# Global Instance (for convenience)
# =============================================================================

_global_logger: SessionLogger | None = None


def get_session_logger() -> SessionLogger:
    """Get or create the global session logger."""
    global _global_logger
    if _global_logger is None:
        _global_logger = SessionLogger(enabled=False)  # Disabled by default
    return _global_logger


def init_session_logger(session_id: str | None = None) -> SessionLogger:
    """Initialize a new global session logger."""
    global _global_logger
    if _global_logger is not None:
        _global_logger.close()
    _global_logger = SessionLogger(session_id=session_id, enabled=True)
    return _global_logger


def close_session_logger() -> str | None:
    """Close the global session logger."""
    global _global_logger
    if _global_logger is not None:
        path = _global_logger.close()
        _global_logger = None
        return path
    return None

