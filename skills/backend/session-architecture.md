# Session & State Architecture

> **Scope:** How Alfred manages user state across sessions — conversation persistence, onboarding lifecycle, and the boundary between them.

This document defines the contracts and patterns for any code that touches user session state. **Read this before modifying `app.py`, `session.py`, or any onboarding state code.**

---

## The Golden Rule

**One function. One mutation. No exceptions.**

Every state change goes through a single commit function. Never directly write to the memory cache, never call the DB save function independently, never stamp timestamps manually. If you find yourself doing any of those things, you're introducing a bug.

---

## Two State Systems

Alfred has two independent state systems. They share no state and should never be coupled.

### 1. Onboarding State (the good example)

**Files:** `src/onboarding/state.py`, `src/onboarding/api.py`

| Property | Implementation |
|----------|---------------|
| State container | `OnboardingState` dataclass with `to_dict()`/`from_dict()` |
| Mutation point | `save_session(state)` — called at end of every endpoint |
| Lifecycle | Explicit phases: CONSTRAINTS → CUISINES → STAPLES → STYLE → COMPLETE |
| DB tables | `onboarding_sessions` (in-progress), `onboarding_data` (completed) |
| Cleanup | Session row deleted on completion |

**Why it works:** Typed state class, single save function, explicit lifecycle, separation of in-progress vs completed data.

### 2. Conversation State (the refactored system)

**Files:** `src/alfred/web/session.py`, `src/alfred/web/app.py`

| Property | Implementation |
|----------|---------------|
| State container | `dict[str, Any]` (conversation context) |
| Mutation point | `commit_conversation(user_id, access_token, conv_state, cache)` |
| Lifecycle | Open-ended, expires after 24h inactivity |
| DB table | `conversations` (single table, upsert on every turn) |
| Cleanup | Replaced on next chat after expiration |

---

## `commit_conversation()` Contract

**Location:** `src/alfred/web/session.py`

```python
def commit_conversation(user_id, access_token, conv_state, cache) -> None:
```

This function:
1. Stamps `last_active_at` with current UTC time
2. Ensures `created_at` exists
3. Updates the in-memory cache
4. Persists to database via upsert

**Rules:**
- Every code path that modifies conversation state MUST call this
- No code should directly write to `conversations[user_id]`
- No code should call `_save_to_db()` directly (it's private for a reason)
- Pre-workflow timestamp stamping is intentionally removed — failed requests should not count as activity

**Call sites in `app.py`:**
- `POST /api/chat` — after `run_alfred()` returns
- `POST /api/chat/stream` — on `done` event (preliminary conversation)
- `POST /api/chat/stream` — on `context_updated` event (final conversation after summarization)

---

## What the Workflow Returns

`run_alfred()` and `run_alfred_streaming()` return conversation dicts that contain **content only** — turns, entities, summaries, id_registry. They do NOT contain session metadata (timestamps).

This is by design. The workflow handles conversation intelligence. The web layer handles session lifecycle. `commit_conversation()` is the bridge.

**Never expect the workflow to preserve `created_at` or `last_active_at`.** That's `commit_conversation()`'s job.

---

## Timestamp Storage

Timestamps exist in two places (for different reasons):

| Location | Purpose | Who writes it |
|----------|---------|---------------|
| DB column `last_active_at` | SQL queries (find stale sessions) | DB trigger on UPDATE |
| Dict key `last_active_at` | In-memory expiry checks | `commit_conversation()` |

On load from DB, `load_conversation_from_db()` merges the column value into the dict. This ensures the dict always has the authoritative timestamp.

**`_ensure_metadata()`** is a private read-path helper that backfills timestamps for legacy rows. It will be removed after one deploy cycle confirms all sessions have metadata.

---

## Onboarding → Chat Transition

The frontend checks `/api/onboarding/state` on startup:
- If `phase !== 'complete'` → render `OnboardingFlow`
- If complete → check `/api/conversation/status` → render chat UI

Onboarding writes to `preferences` table on completion. Chat reads from `preferences` via `profile_builder.py`. There is no direct state sharing between the two systems.

---

## Common Mistakes (and why they're wrong)

| Mistake | Why it's wrong | What to do instead |
|---------|----------------|-------------------|
| `conversations[user.id] = updated_conv` | Skips timestamp stamp and DB save | Call `commit_conversation()` |
| `touch_session(conv)` before workflow | Stamps activity for potentially failed request | Remove — `commit_conversation()` stamps after success |
| `save_conversation_to_db()` directly | Skips cache update and timestamp stamp | Call `commit_conversation()` |
| Adding `last_active_at` to workflow code | Workflow shouldn't know about session lifecycle | Let `commit_conversation()` handle it |
| Checking `conv.get("last_active_at")` after DB load without merge | DB stores it as a column, not in JSONB | `load_conversation_from_db()` already merges — trust it |

---

## Background Execution (Phase 3)

The streaming chat endpoint (`POST /api/chat/stream`) decouples the workflow from the request lifecycle:

1. **SSE endpoint** creates a job, an `asyncio.Queue`, and launches the workflow via `asyncio.create_task`
2. **Background worker** (`background_worker.py`) runs `run_alfred_streaming()`, relays events to the queue, and stores the result in the jobs table
3. **SSE generator** reads from the queue and yields events to the client
4. **On client disconnect**: `CancelledError` is caught, background task continues, result stored in jobs table
5. **On reconnect**: Frontend calls `GET /api/jobs/active` to recover the missed response

**Key invariant:** The background worker calls `commit_conversation()` and `complete_job()` regardless of client connection state.

---

## Key Files

| File | Purpose |
|------|---------|
| `src/alfred/web/session.py` | All session functions: commit, load, delete, status, expiry |
| `src/alfred/web/jobs.py` | Job lifecycle: create, start, complete, fail, acknowledge, get |
| `src/alfred/web/background_worker.py` | Background workflow execution, event queue relay |
| `src/alfred/web/app.py` | Chat endpoints, `get_user_conversation()`, `conversations` cache |
| `src/onboarding/state.py` | `OnboardingState` dataclass and phase logic |
| `src/onboarding/api.py` | Onboarding endpoints and `save_session()` |
| `migrations/026_onboarding_tables.sql` | Onboarding DB schema |
| `migrations/029_conversations_table.sql` | Conversation DB schema |
| `migrations/030_jobs_table.sql` | Jobs table for background execution |
