# Alfred Roadmap

**Last Updated:** 2026-01-26

---

## Documentation Structure

| Path | Purpose | Update Frequency |
|------|---------|------------------|
| [../CLAUDE.md](../CLAUDE.md) | System constitution (stable) | Rarely |
| [../skills/](../skills/) | Agent-scoped context | When patterns change |
| [architecture/overview.md](architecture/overview.md) | System map, graph flow | Major changes |
| [architecture/context-and-session.md](architecture/context-and-session.md) | Context engineering, registry | Conceptual changes |
| [architecture/capabilities.md](architecture/capabilities.md) | User-facing capabilities | Feature changes |
| [specs/context-api-spec.md](specs/context-api-spec.md) | Context builders | API changes |
| [specs/onboarding-spec.md](specs/onboarding-spec.md) | User onboarding | Onboarding changes |
| [specs/session-persistence-spec.md](specs/session-persistence-spec.md) | Session timeout, resume flow | Session changes |

---

## Active Work

| Area | Status | Description | Spec |
|------|--------|-------------|------|
| — | — | — | — |

*No active projects. Add items here when starting new work.*

---

## Recently Completed

### 2026-01-26: Session Management Phase 1 - Timeout + Resume Prompt

Session timeout and resume flow for returning users.

- **Backend: Session Module** (`src/alfred/web/session.py`)
  - `get_session_status()` - Returns active/stale/none based on timestamps
  - `touch_session()` - Updates last_active_at on each chat request
  - `create_fresh_session()` - Initializes conversation with session metadata
  - `is_session_expired()` - Checks 24h expiration threshold

- **Backend: New Endpoint**
  - `GET /api/conversation/status` - Returns session status with preview
  - Auto-clears expired sessions (>24h)

- **Frontend: ResumePrompt Component**
  - Dismissible modal shown after 30 min inactivity
  - Shows last message preview and relative time
  - [Resume] continues with backend context, [Start Fresh] resets

- **Bug Fix: New Chat Button**
  - `handleNewChat` now calls `/api/chat/reset` (was only clearing frontend)

- **Configurable Timeouts** (`config.py`)
  - `session_active_timeout_minutes: 30`
  - `session_expire_hours: 24`

- **Spec:** [specs/session-persistence-spec.md](specs/session-persistence-spec.md)

### 2026-01-25: Streaming Architecture Phase A - Active Context Events

Rich entity metadata now flows from SessionIdRegistry to frontend via streaming events.

- **Backend: SessionIdRegistry**
  - `get_active_context_for_frontend()` - Returns active entities with full metadata
  - `_last_snapshot_refs` field enables "+N new" change tracking between events
  - Metadata includes: ref, type, label, action, turnCreated, turnLastRef, isGenerated, retentionReason

- **Backend: Streaming Events**
  - `active_context` event emitted after Understand, Act steps, Act Quick, Reply
  - `done` event includes final `active_context` payload
  - Change tracking shows which entities were added since last event

- **Frontend: ActiveContextDisplay Component**
  - Collapsible inline display showing "AI Context (Turn N)"
  - Action-aware badges: read (gray), created (green), generated (amber), linked (blue), updated (cyan)
  - User action styles: mentioned:user, created:user, updated:user
  - "+N new" indicator with pulse animation for entities added this phase
  - Clickable entities navigate to relevant views

- **Shared Types**
  - `types/chat.ts` - ActiveContext, ActiveContextEntity interfaces

- **Spec:** [../CLAUDE.plans/fluffy-mixing-sun.md](../CLAUDE.plans/fluffy-mixing-sun.md)

### 2026-01-25: Streaming Architecture Phase B - Inline Progress Display

Full visibility into Alfred's execution with inline progress, tool calls, and context updates.

- **Backend: New Events**
  - `think_complete` event with goal and step count
  - `step_complete` now includes `tool_calls` array (tool, table, count)
  - `_extract_tool_calls()` helper in workflow.py

- **Frontend: StreamingProgress Component**
  - Replaces ProgressTrail with phase-aware display
  - Shows: Understanding → Planning (goal + steps) → Act steps → Response
  - Inline tool call display: `read(inventory) → 12 items`
  - Inline ActiveContextDisplay after each phase
  - State machine pattern (`createInitialPhaseState`, `updatePhaseState`)

- **ChatView Refactor**
  - Phase-based state tracking instead of simple progress array
  - All events routed through `updatePhaseState`
  - Quick Mode vs Plan Mode rendering

- **Legacy Cleanup**
  - Removed EntityCard component (replaced by ActiveContextDisplay)
  - Removed legacy entity tracking from ChatView

- **Spec:** [../CLAUDE.plans/fluffy-mixing-sun.md](../CLAUDE.plans/fluffy-mixing-sun.md)

### 2026-01-25: Schema-Driven CRUD + User Context Integration

Full CRUD across all subdomains with AI context awareness.

- **Phase 1-2: Schema-Driven UI Infrastructure**
  - Backend: Schema API (`/api/schema/*`), Entity CRUD (`/api/entities/*`)
  - Frontend: `useSchema` hooks, `FieldRenderer`, `EntityForm`, `EntityFormModal`
  - Custom editors: `IngredientsEditor`, `StepsEditor`, `RecipePicker`, `MealPlanPicker`

- **Full CRUD for All Subdomains**
  | View | Create | Update | Delete |
  |------|--------|--------|--------|
  | Inventory | ✅ | ✅ | ✅ |
  | Shopping | ✅ | ✅ | ✅ |
  | Tasks | ✅ | ✅ | ✅ |
  | Recipes | ✅ | ✅ | ✅ |
  | Meal Plans | ✅ | ✅ | ✅ |

- **Phase 3a: UI Changes → SessionIdRegistry**
  - `ChatContext` with `pushUIChange()` tracks frontend CRUD
  - `register_from_ui()` method registers UI-created entities
  - UI changes sent with next chat message, injected into `turn_step_results`

- **Phase 3b: @-Mention Autocomplete**
  - `/api/context/entities` search endpoint
  - Frontend autocomplete dropdown in `ChatInput`
  - Format: `@[Label](type:uuid)` → AI receives full entity data

- **Phase 3d: Prompt Optimization**
  - Action tags: `[created:user]`, `[updated:user]`, `[mentioned:user]`, `[read]`, `[linked]`
  - Turn numbers in entity context (e.g., `T5` for turn 5)
  - 5-line legend added to Act/Think/Understand prompts

- **Spec:** [ideas/vision-feasibility-assessment.md](ideas/vision-feasibility-assessment.md) — Implementation plan

### 2026-01-24: V9 Unified Context API for Generated Entities
- **Tier 1:** Generated entities treated like DB entities
  - `get_entity_data(ref)` — single source of truth for entity data availability
  - `update_entity_data(ref, content)` — unified modification API
  - Read rerouting uses unified method (removed `startswith("gen_")` checks)
- **Tier 2:** Centralized history/turn logic
  - Entity tier logic unified in entity.py
  - ThinkContext aligned with entity.py patterns
- **Tier 2b:** Reply bug fix → true unification
  - Reply now has access to `pending_artifacts` (same view as Think/Act)
  - All nodes see same generated content
- **Tier 3:** Act injection fix
  - `injection.py` now injects `## 5. Generated Data` for write/generate/analyze (was write-only)
  - Fixes "No data to analyze" bug when Act tries to reason about generated content
- **Tier 4:** Think prompt - multi-entity operations
  - Added guidance for compare/match/diff operations requiring multiple data sources
  - Think must verify ALL sources are in context before planning `analyze`
- **Spec:** [archive/pr-unified-context-api.md](archive/pr-unified-context-api.md) — Full PR documentation

### 2026-01-23: Context API Migration
- Unified naming convention: `build_{node}_context()` for all nodes
- Migrated Understand, Think to use builders.py
- Act uses `build_act_entity_context()` (lives in act.py due to SessionIdRegistry dependencies)
- Removed legacy formatters from id_registry.py
- **Spec:** [specs/context-api-spec.md](specs/context-api-spec.md) — Migration Path section

### 2026-01-22: Onboarding Flow
- Auto-apply preferences during onboarding
- Preferences view for users
- **Spec:** [specs/onboarding-spec.md](specs/onboarding-spec.md)

### Earlier: V8 Architecture
- Google OAuth + Supabase Auth
- Database-enforced RLS
- SessionIdRegistry as single source of truth
- Three-layer context model (Entity, Conversation, Reasoning)

---

## Backlog

### High Priority
- [ ] Observability: structured logging, metrics, prompt cost tracking
- [ ] Recipe scaling (multiply servings, adjust ingredients)
- [ ] Meal plan templates (weekly patterns)

### Medium Priority
- [ ] Shopping list grouping by store section
- [ ] Ingredient substitution suggestions
- [ ] Recipe import from URL (parse external recipes)

### Low Priority / Ideas
- [ ] Voice input support
- [ ] Multi-user households (shared pantry)
- [ ] Nutritional information integration

---

## How to Use This File

**Starting new work:**
1. Move item from Backlog → Active Work
2. Create spec in `docs/` if needed
3. Update status as you progress

**Completing work:**
1. Move from Active Work → Recently Completed with date
2. Update relevant spec's status section
3. Update CLAUDE.md if system behavior changed

**Session handoff:**
- This file is the entry point for "what's happening"
- Specs have implementation details
- CLAUDE.md has operational knowledge
