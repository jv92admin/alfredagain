# Alfred Roadmap

**Last Updated:** 2026-01-24

---

## Documentation Structure

| File | Purpose | Update Frequency |
|------|---------|------------------|
| [../CLAUDE.md](../CLAUDE.md) | AI assistant entry point | When system behavior changes |
| [architecture_overview.md](architecture_overview.md) | System map, graph flow, node responsibilities | Major architectural changes |
| [context-engineering-architecture.md](context-engineering-architecture.md) | State vs context, three-layer model | Conceptual changes |
| [session-id-registry-spec.md](session-id-registry-spec.md) | SessionIdRegistry implementation | When registry behavior changes |
| [context-api-spec.md](context-api-spec.md) | Context builders, entity snapshots | When context API changes |
| [onboarding-spec.md](onboarding-spec.md) | User onboarding flow | When onboarding changes |

---

## Active Work

| Area | Status | Description | Spec |
|------|--------|-------------|------|
| — | — | — | — |

*No active projects. Add items here when starting new work.*

---

## Recently Completed

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
- **Spec:** [pr-unified-context-api.md](pr-unified-context-api.md) — Full PR documentation

### 2026-01-23: Context API Migration
- Unified naming convention: `build_{node}_context()` for all nodes
- Migrated Understand, Think to use builders.py
- Act uses `build_act_entity_context()` (lives in act.py due to SessionIdRegistry dependencies)
- Removed legacy formatters from id_registry.py
- **Spec:** [context-api-spec.md](context-api-spec.md) — Migration Path section ✅

### 2026-01-22: Onboarding Flow
- Auto-apply preferences during onboarding
- Preferences view for users
- **Spec:** [onboarding-spec.md](onboarding-spec.md)

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
