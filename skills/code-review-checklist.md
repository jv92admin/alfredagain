# Code Review Checklist

> **Scope:** Foundational engineering hygiene for any change to the Alfred codebase. Review this before proposing changes, not just after.

These are not advanced practices. They are basic expectations. If a change violates any of these, stop and fix the design before writing more code.

---

## 1. Single Source of Truth

**Every piece of data lives in exactly one place.**

- If a value is stored in the database, don't also store it in a separate column AND a JSON blob unless there's a documented reason (and a merge function on load)
- If state is managed by a function, all mutations go through that function
- If a type is defined in the backend, the frontend type must be generated from or mirror it — not independently maintained

**Red flags:**
- Same field name appearing in multiple storage locations
- Multiple functions that each write to the same destination
- Frontend and backend types that look similar but are maintained separately

**Alfred-specific:** `commit_conversation()` is the single mutation point for conversation state. Onboarding uses `save_session()`. Don't introduce parallel paths.

---

## 2. DRY — Don't Repeat Yourself

**If the same logic appears in more than one place, extract it.**

This is not about reducing line count. It's about ensuring that a bug fix in one place doesn't need to be duplicated in three others.

- If 3+ endpoints do the same 3-step sequence, that's a function
- If the same validation logic exists in frontend and backend, document which is authoritative
- If you're copy-pasting a code block, stop and ask why

**Red flags:**
- "I'll just add these same 3 lines here too"
- Multiple files importing the same set of helpers to do the same thing
- Changing one endpoint but forgetting to change the identical code in another

**Alfred-specific:** The session persistence bug came from copy-pasting `touch_session()` + cache write + DB save across 4 endpoints. Each copy had slightly different bugs.

---

## 3. Single Point of Mutation

**Shared mutable state must have exactly one write path.**

If multiple code paths can modify the same state, you will eventually have a consistency bug. The fix is not "be more careful" — it's to make the wrong thing impossible.

- Wrap mutations in a function that handles all side effects atomically
- Make internal helpers private (underscore prefix) so they can't be called directly
- If a function exists to do X, no other code should do X inline

**Red flags:**
- Direct writes to a cache/dict that has a dedicated save function
- Public functions that should only be called by one other function
- State that gets modified before and after an operation (pre- and post- hooks scattered across files)

**Alfred-specific:** `_save_to_db()` is private. Only `commit_conversation()` calls it. `conversations[user.id] = ...` should only appear inside `commit_conversation()`.

---

## 4. Clear Ownership

**Every endpoint, table, and state object has one owner.**

- Who creates it? Who reads it? Who updates it? Who deletes it?
- If multiple modules can write to the same table, document who owns what
- API endpoints should have clear input/output contracts

**Red flags:**
- Two different modules both writing to the same database table without coordination
- Endpoints that return different shapes depending on internal state
- "I'm not sure which function is supposed to handle this"

**Alfred-specific ownership:**

| Resource | Owner | Read by |
|----------|-------|---------|
| `conversations` table | `session.py` via `commit_conversation()` | `app.py` via `get_user_conversation()` |
| `onboarding_sessions` table | `onboarding/api.py` via `save_session()` | `onboarding/api.py` endpoints |
| `preferences` table | `onboarding/api.py` on complete | `profile_builder.py` for prompts |
| `conversations` memory cache | `commit_conversation()` | `get_user_conversation()`, status endpoint |

---

## 5. Schema Sync (Frontend ↔ Backend)

**Types that cross the API boundary must stay in sync.**

- Backend Pydantic models define the contract
- Frontend TypeScript types must match
- When a backend model changes, the frontend type must be updated in the same PR

**Red flags:**
- Frontend type has fields the backend doesn't send
- Backend adds a new field but frontend doesn't handle it
- Different naming conventions (snake_case vs camelCase) without a documented mapping

**Alfred-specific:** Session status response, onboarding state, entity schemas — all cross the boundary. Changes to `SessionStatusResponse` in `session.py` must be reflected in `frontend/src/types/session.ts`.

---

## 6. Fail Fast, Don't Fail Silently

**Errors should be visible, not swallowed.**

- Don't catch exceptions just to return `None` unless that's the documented contract
- Log at the appropriate level: `warning` for recoverable, `error` for data loss risk
- If a save fails, the caller should know

**Red flags:**
- `except Exception: pass`
- Functions that return `True`/`False` for success but callers never check
- Silent fallbacks that hide configuration errors

---

## 7. Before You Commit, Ask These Questions

1. **Did I introduce a new write path for shared state?** If yes, should it go through an existing mutation function?
2. **Did I duplicate logic that exists elsewhere?** If yes, extract a shared function.
3. **Is there a single source of truth for every piece of data I touched?** If not, which one is authoritative?
4. **Did I change a type that crosses the API boundary?** If yes, update both sides.
5. **Would a new team member understand where to make changes?** If not, the ownership isn't clear enough.
6. **If I grep for the same pattern, does it appear in multiple places?** If yes, consider consolidation.

---

## Post-Mortem Reference

This checklist was created after a session persistence bug that required 4 separate fixes because the same mutation logic was scattered across 4 code paths. See `skills/backend/session-architecture.md` for the full architectural context.
