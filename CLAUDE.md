# CLAUDE.md

This file defines Alfred's stable boundaries and non-negotiable constraints.
For implementation details, see `docs/` and `skills/`.

## What Alfred Is

Alfred is a LangGraph-based multi-agent assistant, split into two Python packages:

- **`alfred`** (core) — Domain-agnostic orchestration engine: pipeline, entity tracking, CRUD execution, prompt assembly, conversation memory
- **`alfred_kitchen`** (domain) — Kitchen-specific implementation: entities, subdomains, prompts, database adapter, bypass modes

Core never imports kitchen. Kitchen imports core freely. New domains implement `DomainConfig` and call `register_domain()`.

**Core Principle:** Deterministic systems manage state. LLMs interpret and decide. The CRUD layer + SessionIdRegistry own entity lifecycle; LLMs reason over that state.

---

## System Boundaries

### Data Integrity Guarantees

- All entity lifecycle changes are deterministic (CRUD layer owns state)
- LLMs never see UUIDs (SessionIdRegistry translates to simple refs like `recipe_1`)
- Generated content (`gen_*` refs) requires explicit user approval before persistence
- Database-enforced RLS via Supabase Auth (no application-level trust)

### Public API Surface

- `POST /api/chat` — Main conversational endpoint
- `GET/POST/PUT/DELETE /api/{entity_type}/*` — Schema-driven CRUD
- `POST /api/onboarding/*` — User setup flow

All endpoints require valid JWT in `Authorization: Bearer <token>` header.

### Non-Negotiable Constraints

- Never expose UUIDs to LLM prompts
- Never auto-save generated content without user confirmation
- Never bypass RLS (always use `get_client()`, never raw DB access)
- Never commit secrets (.env, credentials) to version control
- Never duplicate state mutation logic — use single commit functions (`commit_conversation()`, `save_session()`)
- Never write directly to shared caches — always go through the owning function
- Review `skills/code-review-checklist.md` before proposing changes to state management or API contracts

---

## Development Commands

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# Run
alfred health     # Check configuration
alfred chat       # Interactive CLI
alfred serve      # FastAPI server on :8000

# Frontend
cd frontend
npm install
npm run dev       # Vite dev server

# Quality
pytest            # All tests
ruff check src/   # Lint
ruff format src/  # Format
mypy src/         # Type check
```

---

## Migration & Breaking Changes

Before making changes that affect:

| Area | Action |
|------|--------|
| Database schema | Create numbered migration in `migrations/` |
| API contracts | Update `docs/architecture/capabilities.md` |
| Prompt structure | Update relevant `docs/prompts/*.md` |
| Entity lifecycle | Update `docs/architecture/sessions-context-entities.md` |

---

## Documentation Hierarchy

| Path | Purpose | Audience |
|------|---------|----------|
| `docs/architecture/overview.md` | Architecture index + pipeline diagram | All agents |
| `docs/architecture/core-domain-architecture.md` | Two-package split, DomainConfig protocol | All agents |
| `docs/architecture/core-public-api.md` | Entry points, extension protocols, extraction path | Implementers |
| `docs/architecture/domain-implementation-guide.md` | How to build a new domain | Implementers |
| `docs/architecture/` (4 internals docs) | CRUD, sessions, pipeline, prompts | Deep-dive |
| `skills/frontend/` | UI development context | Frontend agents |
| `skills/backend/` | CRUD, database patterns | Backend agents |
| `skills/orchestration/` | LLM node behavior | Orchestration agents |
| `docs/specs/` | Feature specifications | Implementers |
| `docs/ideas/` | Brainstorming, vision | Designers |
| `docs/ROADMAP.md` | Active work, backlog | All |
