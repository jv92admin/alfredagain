# Session Persistence Specification

**Date:** 2026-01-26
**Purpose:** Define session timeout, resume flow, and conversation persistence

---

## Overview

Alfred needs session management to handle:
1. Users returning after brief absence (resume seamlessly)
2. Users returning after longer absence (offer choice to resume or start fresh)
3. Conversation persistence across server restarts
4. Eventually: multiple conversation history

---

## Phase Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SESSION PERSISTENCE ROADMAP                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  PHASE 1: Session Timeout + Resume Prompt                    ✅ COMPLETE    │
│  "Return within 30 min = seamless, after 30 min = prompt"                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  PHASE 2: Database Persistence                               ✅ COMPLETE    │
│  "Conversation state survives restarts via commit_conversation()"           │
├─────────────────────────────────────────────────────────────────────────────┤
│  PHASE 2.5: Job Durability                                   📋 PLANNED    │
│  "Agent completes even if client disconnects, response recoverable"         │
├─────────────────────────────────────────────────────────────────────────────┤
│  PHASE 3: Multi-Conversation Support + Chat History UI       🔮 FUTURE     │
│  "Sidebar with conversation list, message history, pins"                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Current State Comparison

| Capability | Phase 1 | Phase 2 (Now) | Phase 2.5 | Phase 3 |
|------------|---------------|---------|---------|
| Backend context | ✅ Preserved (in-memory) | ✅ DB-persisted | ✅ DB-persisted | ✅ DB-persisted |
| UI messages | ❌ Fresh on reload | ❌ Fresh on reload | ❌ Fresh on reload | ✅ Loaded from DB |
| Resume prompt | ✅ Shows after 30 min | ✅ Same | ✅ Same | ✅ Same |
| Server restart | ⚠️ Session lost | ✅ Survives | ✅ Survives | ✅ Survives |
| Disconnect recovery | ❌ | ❌ | ✅ Jobs table | ✅ Jobs table |
| Multiple conversations | ❌ | ❌ | ❌ | ✅ Sidebar + history |

---

## Phase 1: Session Timeout + Resume Prompt ✅

**Status:** Complete

### Configuration

**File:** `src/alfred/config.py`

```python
class Settings:
    session_active_timeout_minutes: int = 30  # Prompt to resume after this
    session_expire_hours: int = 24  # Auto-clear session after this
```

### Session States

```
┌─────────────────────────────────────────────────────────────────┐
│                      SESSION STATE MACHINE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐    activity    ┌──────────┐                      │
│   │   none   │ ──────────────>│  active  │<─────┐               │
│   └──────────┘                └──────────┘      │               │
│        ^                           │            │ activity      │
│        │                           │ 30 min     │               │
│        │ 24h expire                v            │               │
│        │                     ┌──────────┐       │               │
│        └─────────────────────│  stale   │───────┘               │
│                              └──────────┘                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

| State | Condition | Frontend Behavior |
|-------|-----------|-------------------|
| `none` | No session exists | Show welcome message |
| `active` | Last activity < 30 min | Continue seamlessly |
| `stale` | 30 min < last activity < 24h | Show resume prompt |
| (expired) | Last activity > 24h | Auto-clear, treat as `none` |

### Backend Implementation

**File:** `src/alfred/web/session.py`

```python
SessionStatus = Literal["active", "stale", "none"]

class SessionStatusResponse(TypedDict):
    status: SessionStatus
    last_active_at: str | None
    preview: SessionPreview | None

class SessionPreview(TypedDict):
    last_message: str  # Truncated to 50 chars
    message_count: int  # Computed from len(recent_turns)

def get_session_status(conv_state: dict | None) -> SessionStatusResponse:
    """Check session status based on timestamps."""

def touch_session(conv_state: dict) -> dict:
    """Update last_active_at on each chat request."""

def ensure_session_metadata(conv_state: dict) -> dict:
    """Backfill created_at/last_active_at for existing sessions."""

def create_fresh_session() -> dict:
    """Create new conversation with session metadata."""

def is_session_expired(conv_state: dict | None) -> bool:
    """Check if session is beyond 24h expiration."""
```

### API Endpoint

**File:** `src/alfred/web/app.py`

```
GET /api/conversation/status
```

**Response:**
```json
{
  "status": "stale",
  "last_active_at": "2026-01-26T10:30:00Z",
  "preview": {
    "last_message": "I found 3 recipes that match your...",
    "message_count": 5
  }
}
```

### Frontend Implementation

**File:** `frontend/src/components/Chat/ResumePrompt.tsx`

Modal component with:
- Last message preview (truncated)
- Relative time ("2 hours ago")
- [Resume] and [Start Fresh] buttons
- Dismissible (click outside or Escape = implicit Resume)

**File:** `frontend/src/App.tsx`

```typescript
// Check session status after auth + onboarding
useEffect(() => {
  if (user && needsOnboarding === false) {
    checkSessionStatus()
  }
}, [user, needsOnboarding])

const checkSessionStatus = async () => {
  const status = await apiRequest<SessionStatusResponse>('/api/conversation/status')
  if (status.status === 'stale') {
    setShowResumePrompt(true)
  }
}
```

### Bug Fix: New Chat Button

**Before:** `handleNewChat` only cleared frontend state, leaving backend context intact.

**After:** `handleNewChat` now calls `/api/chat/reset` to clear both frontend and backend:

```typescript
const handleNewChat = async () => {
  try {
    await apiRequest('/api/chat/reset', { method: 'POST' })
  } catch (error) {
    console.error('Failed to reset backend session:', error)
  }
  setChatMessages([INITIAL_MESSAGE])
}
```

### Files Changed (Phase 1)

| File | Change |
|------|--------|
| `src/alfred/config.py` | Added timeout constants |
| `src/alfred/web/session.py` | **NEW** - Session logic module |
| `src/alfred/web/app.py` | Added `/api/conversation/status`, `commit_conversation()` calls |
| `frontend/src/types/session.ts` | **NEW** - TypeScript types |
| `frontend/src/components/Chat/ResumePrompt.tsx` | **NEW** - Resume modal |
| `frontend/src/App.tsx` | Session check + resume flow, fixed `handleNewChat` |

---

## Phase 2: Database Persistence ✅

**Status:** Complete

### Goal

Conversation state survives server restarts via database persistence.

### What Was Built

- **`conversations` table** (`migrations/029_conversations_table.sql`) with JSONB state, timestamp columns, RLS, auto-update trigger
- **`commit_conversation()`** — single point of mutation for all conversation state (timestamps + cache + DB save)
- **`load_conversation_from_db()`** — loads state from DB, merges column timestamps into dict
- **All chat endpoints** use `commit_conversation()` exclusively (no scattered mutations)

### Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mutation pattern | Single `commit_conversation()` function | Prevents scattered mutation bugs (see post-mortem in `skills/code-review-checklist.md`) |
| Timestamp storage | DB columns + dict keys, merged on load | SQL queries use columns, in-memory checks use dict |
| `touch_session()` | Removed entirely | Absorbed into `commit_conversation()` — failed requests shouldn't count as activity |
| `_save_to_db()` | Private (underscore prefix) | Only `commit_conversation()` should call it |
| Chat History UI | Deferred to Phase 3 | Separate concern from state persistence |

### Files Changed (Phase 2)

| File | Change |
|------|--------|
| `migrations/029_conversations_table.sql` | **NEW** - Conversations table with RLS |
| `src/alfred/web/session.py` | Added `commit_conversation()`, `load_conversation_from_db()`. Removed `touch_session()`. Made `_save_to_db()` and `_ensure_metadata()` private. |
| `src/alfred/web/app.py` | All chat endpoints use `commit_conversation()`. Removed scattered touch/save calls. |
| `skills/backend/session-architecture.md` | **NEW** - Documents commit contract and common mistakes |
| `skills/code-review-checklist.md` | **NEW** - Engineering checklist (DRY, single point of mutation, etc.) |

---

## Phase 3: Multi-Conversation Support + Chat History UI 🔮

**Status:** Future

### Features

| Feature | Description |
|---------|-------------|
| Chat History UI | Resume shows actual prior messages (not fresh UI) |
| `/api/conversation/messages` | Endpoint to load chat messages for display |
| Conversation sidebar | List of past conversations with titles |
| Auto-titles | Generate title from first user message or goal |
| Pins/favorites | Star important conversations for quick access |
| Archive | Hide old conversations without deleting |
| Cross-conversation recall | "What was that recipe we discussed last week?" |

### UI Concept

```
┌────────────────────────────────────────────────────────────┐
│ ☰  Alfred                                    [+ New Chat]  │
├──────────────┬─────────────────────────────────────────────┤
│              │                                             │
│ Today        │   [Current conversation...]                 │
│ ├─ Meal plan │                                             │
│              │                                             │
│ Yesterday    │                                             │
│ ├─ ⭐ Pasta  │                                             │
│ ├─ Shopping  │                                             │
│              │                                             │
│ Last week    │                                             │
│ ├─ Pantry    │                                             │
│              │                                             │
└──────────────┴─────────────────────────────────────────────┘
```

### Database Changes

```sql
-- Add to conversations table
ALTER TABLE conversations ADD COLUMN is_pinned BOOLEAN DEFAULT false;
ALTER TABLE conversations ADD COLUMN archived_at TIMESTAMPTZ;

-- Conversation search (for recall)
CREATE INDEX conversations_state_gin ON conversations USING gin(state jsonb_path_ops);
```

### API Changes

```
GET /api/conversations              -- List all conversations
GET /api/conversations/:id          -- Get specific conversation
POST /api/conversations/:id/pin     -- Toggle pin
POST /api/conversations/:id/archive -- Archive conversation
```

---

## Verification Checklist

### Phase 1 ✅

- [x] Fresh user: Login → no resume prompt → welcome message
- [x] Within 30 min: Reload → session continues seamlessly
- [x] After 30 min: Reload → resume prompt shown with preview
- [x] Resume clicked: Dismiss prompt → backend context preserved
- [x] Start Fresh clicked: Backend reset → fresh welcome
- [x] New Chat button: Calls `/api/chat/reset` → clears both frontend and backend
- [x] After 24 hours: Session auto-cleared → treated as fresh user
- [x] Dismiss modal (click outside/Escape): Implicit resume

### Phase 2 ✅

- [x] Server restart: Conversation state survives
- [x] Single point of mutation: `commit_conversation()` handles all state writes
- [x] Multiple browser tabs: Same conversation state (DB-backed)
- [x] Concurrent users: No state leakage (RLS enforced)

### Phase 2.5 (Planned)

- [ ] Jobs table created with RLS
- [ ] Chat endpoints wrapped with job lifecycle
- [ ] Disconnect recovery: `GET /api/jobs/active` returns missed response
- [ ] Frontend polls running jobs on reconnect
- [ ] Frontend acknowledges received responses

### Phase 3 (Future)

- [ ] Resume shows actual prior messages in UI
- [ ] Sidebar shows conversation list
- [ ] Can switch between conversations
- [ ] Pins persist across sessions
- [ ] Search across conversation history

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Timeout storage | In conversation state | No new fields needed, works with existing structure |
| Preview source | `recent_turns[-1]["assistant"]` | Most relevant context for user |
| message_count | Computed from `len(recent_turns)` | No new field, always accurate |
| Resume behavior | UI fresh, backend preserved | Phase 2 simplicity; Phase 3 adds message loading |
| Dismiss = Resume | Yes | Matches user mental model (came back = wants to continue) |
| 30 min threshold | Configurable via config.py | Can tune based on usage patterns |
| 24h expiration | Auto-clear | Prevents unbounded memory growth |
| State mutation | Single `commit_conversation()` | Prevents scattered mutation bugs (Phase 2 lesson) |
| `touch_session()` | Removed | Absorbed into `commit_conversation()` |

---

## Known Issues / Future Work

| Issue | Description | Phase |
|-------|-------------|-------|
| Prompt logging session leak | `_session_id` in prompt_logger is module-level, shared across concurrent users. Each user should have isolated logging sessions. | Future |
| ~~In-memory state lost on restart~~ | ~~Current Phase 1 stores conversation in dict; server restart loses all sessions.~~ | ✅ Phase 2 |
| No message history UI | Resume shows fresh UI even though backend has context. User can't see prior conversation. | Phase 3 |
| Response lost on disconnect | Phone lock or network blip during SSE stream loses the response forever. | Phase 2.5 |

---

*Session management ensures Alfred remembers context while respecting user intent to start fresh.*
