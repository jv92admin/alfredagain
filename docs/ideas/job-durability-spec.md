# Job Durability: Background Agent Execution

> Making Alfred's reasoning loops survive real-world usage patterns.

**Status:** Phase 2.5 In Progress
**Depends on:** Phase 2 (Session DB Persistence) ✅ Complete
**Priority:** High - foundational for mobile usability

---

## The Problem

Alfred's Think → Act → Reply loop currently runs **inside a single HTTP request**. This means:

| User Action | What Happens | Result |
|-------------|--------------|--------|
| Phone screen locks | OS suspends browser, SSE drops | Agent dies mid-think |
| Switch to another app | Connection may drop | Agent dies |
| Close laptop lid | Browser freezes | Agent dies |
| Poor network | Request times out | Agent dies |

**The user experience:**
- Start a 5-step recipe generation
- Lock phone to check a text
- Come back to... nothing
- "Did it work? Do I send again? Will I get duplicates?"

This isn't an edge case. It's the **primary mobile usage pattern**.

---

## Why This Matters

### The 15-Second Problem

A typical Alfred request:
- Think: 3-5 seconds (planning steps)
- Act: 5-10 seconds (executing CRUD, generating content)
- Reply: 2-3 seconds (formatting response)

**Total: 10-18 seconds** for a moderately complex request.

Nobody holds their phone perfectly still for 18 seconds. They:
- Glance at notifications
- Check the time
- Lock the screen out of habit
- Switch apps briefly

**If any of these kills the agent, Alfred feels broken.**

### The Expectation Gap

Users expect Alfred to behave like:
- ChatGPT (close tab, reopen, response is there)
- Uber (request ride, lock phone, driver still coming)
- DoorDash (order food, do other things, food still arrives)

Not like:
- A fragile AJAX form that dies if you blink

---

## Current Architecture (Request-Bound)

```
┌─────────────────────────────────────────────────────────────┐
│                         CLIENT                               │
│                                                              │
│   POST /api/chat/stream ──────────────────────┐             │
│                                                │             │
│   ┌──────────────────────────────────────────┐│             │
│   │  SSE Connection (must stay alive)        ││             │
│   │                                          ││             │
│   │  ← phase: think                          ││             │
│   │  ← step: 1 of 3                          ││             │
│   │  ← step: 2 of 3     ← PHONE LOCKS HERE   ││             │
│   │  ✗ connection dies                       ││             │
│   │  ✗ server aborts                         ││             │
│   └──────────────────────────────────────────┘│             │
└─────────────────────────────────────────────────────────────┘
```

**Problem:** The SSE connection IS the job. No connection = no job.

---

## Target Architecture (Job-Based)

```
┌─────────────────────────────────────────────────────────────┐
│                         CLIENT                               │
│                                                              │
│   POST /api/chat ──→ { job_id: "abc123" }                   │
│                                                              │
│   GET /api/jobs/abc123/stream (SSE) ──┐                     │
│                                        │                     │
│   ← phase: think                       │                     │
│   ← step: 1 of 3                       │                     │
│   ✗ connection drops (phone locks)     │                     │
│                                        │                     │
│   ... time passes ...                  │                     │
│                                        │                     │
│   GET /api/jobs/abc123/stream (SSE) ──┐  ← RECONNECT        │
│   ← step: 3 of 3 (already done!)       │                     │
│   ← phase: complete                    │                     │
│   ← response: "Here's your recipe..."  │                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                         SERVER                               │
│                                                              │
│   Job abc123 created ──→ status: pending                    │
│                                                              │
│   Background worker picks up job                            │
│   ├── Think (checkpoint to DB)                              │
│   ├── Act step 1 (checkpoint to DB)                         │
│   ├── Act step 2 (checkpoint to DB)    ← client gone, who   │
│   ├── Act step 3 (checkpoint to DB)      cares, keep going  │
│   └── Reply (checkpoint to DB)                              │
│                                                              │
│   Job abc123 ──→ status: complete                           │
│   Result stored in DB                                       │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** The client is just a **viewer**. The job runs to completion regardless.

---

## Implementation Phases

### Phase 2 ✅ Complete: Session Persistence
- Conversation state survives restarts via `conversations` table
- `commit_conversation()` as single point of mutation
- Foundation for job state

### Phase 2.5 🚧 In Progress: Job Wrapper
**Goal:** Jobs complete even if client disconnects, but no fancy checkpointing yet.

```python
# New table
CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  conversation_id UUID REFERENCES conversations(id),
  status TEXT DEFAULT 'pending',  -- pending, running, complete, failed
  input JSONB,                    -- the chat request
  output JSONB,                   -- the final response
  error TEXT,
  created_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

# Flow
1. POST /api/chat → create job → return job_id immediately
2. Background task runs Think → Act → Reply
3. On completion, store result in jobs.output
4. Client polls GET /api/jobs/{id} or reconnects to stream
5. If client was disconnected, they get the result on reconnect
```

**What this fixes:**
- ✅ Phone screen lock → result still available
- ✅ Brief disconnections → can resume
- ✅ "Did it work?" anxiety → check job status

**What this doesn't fix yet:**
- ❌ Long-running jobs (multi-minute) → no progress visibility on reconnect
- ❌ Partial failures → no checkpoint to resume from

### Phase 3: Step Checkpointing
**Goal:** Save progress after each step. Reconnecting client sees where we are.

```python
# Add to jobs table
steps JSONB DEFAULT '[]',  -- array of completed steps

# Each step gets checkpointed
{
  "steps": [
    {"phase": "think", "output": {...}, "completed_at": "..."},
    {"phase": "act", "step": 1, "output": {...}, "completed_at": "..."},
    {"phase": "act", "step": 2, "output": {...}, "completed_at": "..."}
  ]
}

# Client reconnects → streams from where job currently is
# Can show: "Step 2 of 3 complete, working on step 3..."
```

### Phase 4: Resumable Execution
**Goal:** If job fails mid-execution, resume from last checkpoint (not restart).

This is complex and probably overkill for Alfred's use case. Defer unless we see actual need.

---

## API Changes

### Current
```
POST /api/chat/stream
  → SSE stream (tied to request lifecycle)
```

### Proposed
```
POST /api/chat
  → { job_id: "abc123", status: "pending" }

GET /api/jobs/{job_id}
  → { status: "complete", output: {...} }

GET /api/jobs/{job_id}/stream
  → SSE stream of progress events
  → Can reconnect anytime
  → Replays completed steps, then streams live
```

---

## Frontend Changes

### Current
```typescript
const response = await fetch('/api/chat/stream', { method: 'POST', body: ... })
const reader = response.body.getReader()
// If this dies, everything dies
```

### Proposed
```typescript
// 1. Start job
const { job_id } = await fetch('/api/chat', { method: 'POST', body: ... })

// 2. Watch progress (reconnectable)
function watchJob(jobId: string) {
  const eventSource = new EventSource(`/api/jobs/${jobId}/stream`)
  
  eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data)
    if (data.status === 'complete') {
      // Show final response
    } else {
      // Update progress UI
    }
  }
  
  eventSource.onerror = () => {
    // Reconnect after delay
    setTimeout(() => watchJob(jobId), 1000)
  }
}

// 3. On page load, check for pending jobs
const pendingJobs = await fetch('/api/jobs?status=running')
if (pendingJobs.length > 0) {
  // Resume watching
  watchJob(pendingJobs[0].id)
}
```

---

## UI Considerations

### Job Status Indicator
When user returns to a running job:
```
┌─────────────────────────────────────────┐
│  🔄 Alfred is still working...          │
│                                         │
│  ▓▓▓▓▓▓▓▓░░░░░░░  Step 2 of 3          │
│                                         │
│  [Cancel]                               │
└─────────────────────────────────────────┘
```

### Completed Job Recovery
When user returns to a completed job:
```
┌─────────────────────────────────────────┐
│  ✅ Alfred finished while you were away │
│                                         │
│  "Here are 3 recipes using chicken..."  │
│                                         │
│  [Got it]                               │
└─────────────────────────────────────────┘
```

---

## Why This Ordering Makes Sense

```
Phase 2: Session Persistence (doing now)
    │
    │  "Conversation survives restarts"
    │
    ▼
Phase 2.5: Simple Job Wrapper
    │
    │  "Agent completes even if you disconnect"
    │  Builds on: conversations table for storing job context
    │
    ▼
Phase 3: Step Checkpointing
    │
    │  "Reconnect and see exactly where Alfred is"
    │  Builds on: job infrastructure from 2.5
    │
    ▼
Phase 4: Resumable Execution (maybe never)
    │
    │  "Resume failed jobs from checkpoint"
    │  Only if we see actual failures that warrant it
```

Each phase unlocks real user value. Phase 2.5 alone would fix the "phone lock" problem.

---

## Estimated Effort

| Phase | Effort | Impact |
|-------|--------|--------|
| Phase 2 (in progress) | 2-3 hours | Sessions survive deploys |
| Phase 2.5 | 4-6 hours | Jobs complete independently |
| Phase 3 | 8-12 hours | Full progress visibility |
| Phase 4 | Unknown | Probably not needed |

---

## The Bottom Line

> "Who tf wants to wait 15 sec for a recipe without being able to look away?"

Nobody. And they shouldn't have to.

The current architecture treats Alfred like a synchronous API call. But Alfred is an **agent** that thinks, plans, and executes. That takes time. Users need to be able to live their lives while Alfred works.

Phase 2.5 is the minimum viable fix. It's not glamorous infrastructure — it's **table stakes for a usable mobile experience**.

---

*This spec builds on the Phase 2 session persistence work currently in progress.*
