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
│  PHASE 2: Database Persistence + Chat History UI             📋 PLANNED    │
│  "Messages survive restarts, UI shows prior conversation"                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  PHASE 3: Multi-Conversation Support                         🔮 FUTURE     │
│  "Sidebar with conversation list, pins, cross-conversation recall"          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Current State Comparison

| Capability | Phase 1 (Now) | Phase 2 | Phase 3 |
|------------|---------------|---------|---------|
| Backend context | ✅ Preserved (in-memory) | ✅ DB-persisted | ✅ DB-persisted |
| UI messages | ❌ Fresh on reload | ✅ Loaded from DB | ✅ Loaded from DB |
| Resume prompt | ✅ Shows after 30 min | ✅ Same | ✅ Same |
| Server restart | ⚠️ Session lost | ✅ Survives | ✅ Survives |
| Multiple conversations | ❌ | ❌ | ✅ Sidebar + history |

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
| `src/alfred/web/app.py` | Added `/api/conversation/status`, `touch_session()` calls |
| `frontend/src/types/session.ts` | **NEW** - TypeScript types |
| `frontend/src/components/Chat/ResumePrompt.tsx` | **NEW** - Resume modal |
| `frontend/src/App.tsx` | Session check + resume flow, fixed `handleNewChat` |

---

## Phase 2: Database Persistence + Chat History UI 📋

**Status:** Planned

### Goal

When user returns and clicks "Resume":
- UI shows their actual previous messages (not just welcome)
- Conversation survives server restarts

### Database Schema

**Table:** `conversations`

```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,

  -- Session metadata
  created_at TIMESTAMPTZ DEFAULT now(),
  last_active_at TIMESTAMPTZ DEFAULT now(),

  -- Conversation state (JSON blob, same as in-memory structure)
  state JSONB NOT NULL DEFAULT '{}',

  -- For future Phase 3: titles and organization
  title TEXT,  -- Auto-generated from first message
  is_archived BOOLEAN DEFAULT false  -- Set when user clicks "Start Fresh"
);

-- RLS: Users can only access their own conversations
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY conversations_user_policy ON conversations
  FOR ALL USING (auth.uid() = user_id);

-- Index for quick lookup of active (non-archived) conversation
CREATE INDEX conversations_user_active_idx
  ON conversations(user_id, last_active_at DESC)
  WHERE is_archived = false;
```

**Archive behavior:**
- When user clicks "Start Fresh", the current conversation is marked `is_archived = true`
- A new conversation row is created for the fresh session
- Archived conversations remain queryable for Phase 3 history features

### API Changes

**New endpoint:**
```
GET /api/conversation/messages
```

Returns chat messages for UI display:
```json
{
  "messages": [
    {"id": "1", "role": "user", "content": "What's in my pantry?"},
    {"id": "2", "role": "assistant", "content": "Looking at your inventory..."}
  ]
}
```

**Modified endpoints:**
- `POST /api/chat` - Persist conversation state to DB after each turn
- `POST /api/chat/reset` - Create new conversation row, archive old one

### Frontend Changes

**File:** `frontend/src/App.tsx`

On resume:
```typescript
const handleResumeSession = async () => {
  // Load prior messages from backend
  const { messages } = await apiRequest<{messages: Message[]}>('/api/conversation/messages')
  setChatMessages(messages.length > 0 ? messages : [INITIAL_MESSAGE])
  setShowResumePrompt(false)
}
```

### Migration Strategy

1. Add `conversations` table (migration file)
2. Update `app.py` to read/write from DB instead of in-memory dict
3. Add `/api/conversation/messages` endpoint
4. Update frontend to load messages on resume
5. Backfill: On first request from existing user, migrate in-memory state to DB

---

## Phase 3: Multi-Conversation Support 🔮

**Status:** Future

### Features

| Feature | Description |
|---------|-------------|
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

### Phase 2 (Future)

- [ ] Server restart: Conversation state survives
- [ ] Resume: UI shows actual prior messages
- [ ] Multiple browser tabs: Same conversation state
- [ ] Concurrent users: No state leakage (RLS enforced)

### Phase 3 (Future)

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
| Resume behavior | UI fresh, backend preserved | Phase 1 simplicity; Phase 2 adds message loading |
| Dismiss = Resume | Yes | Matches user mental model (came back = wants to continue) |
| 30 min threshold | Configurable via config.py | Can tune based on usage patterns |
| 24h expiration | Auto-clear | Prevents unbounded memory growth |

---

## Known Issues / Future Work

| Issue | Description | Phase |
|-------|-------------|-------|
| Prompt logging session leak | `_session_id` in prompt_logger is module-level, shared across concurrent users. Each user should have isolated logging sessions. | Phase 2 |
| In-memory state lost on restart | Current Phase 1 stores conversation in dict; server restart loses all sessions. | Phase 2 |
| No message history UI | Resume shows fresh UI even though backend has context. User can't see prior conversation. | Phase 2 |

---

*Session management ensures Alfred remembers context while respecting user intent to start fresh.*
