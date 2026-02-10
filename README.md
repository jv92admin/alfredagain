# Alfred

A LangGraph-based multi-agent assistant with a domain-agnostic core and pluggable domain implementations.

## Architecture

Alfred is split into two Python packages:

- **`alfred`** — Core orchestration engine: LangGraph pipeline, entity tracking, CRUD execution, prompt assembly, conversation memory
- **`alfred_kitchen`** — Kitchen domain: pantry, recipes, meal planning, shopping lists, tasks

The core runs a 5-node pipeline:

```
Understand → Think → Act (loop) → Reply → Summarize
```

- **Understand** — Entity resolution, context curation, quick mode detection
- **Think** — Plans execution steps (read, write, analyze, generate)
- **Act** — Executes steps via CRUD tools or LLM generation
- **Reply** — Synthesizes natural language response from execution results
- **Summarize** — Compresses context and persists entity registry for next turn

Quick mode bypasses Think for simple single-table lookups.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Orchestration | LangGraph |
| LLM | OpenAI (gpt-4.1 / gpt-4.1-mini) |
| Structured Output | Instructor |
| Database | Supabase (Postgres + pgvector) |
| Auth | Supabase Auth (Google OAuth) |
| API | FastAPI + SSE streaming |
| Frontend | React + TypeScript + Vite |
| CLI | Typer + Rich |
| Observability | LangSmith |
| Deployment | Railway |

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- Supabase project
- OpenAI API key

### Local Development

```bash
# Clone and setup
git clone <repo-url>
cd alfredagain
python -m venv .venv
.venv\Scripts\activate  # Windows (or source .venv/bin/activate on Unix)
pip install -e ".[dev]"

# Backend
alfred health     # Check configuration
alfred chat       # Interactive CLI
alfred serve      # FastAPI server on :8000

# Frontend
cd frontend
npm install
npm run dev       # Vite dev server
```

### Environment

Copy `.env.example` to `.env` and fill in:
- `OPENAI_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- Optional: `LANGCHAIN_API_KEY` for LangSmith tracing

## Project Structure

```
alfredagain/
├── src/
│   ├── alfred/                    # Core orchestration (domain-agnostic)
│   │   ├── graph/                 # LangGraph nodes, state, workflow
│   │   ├── core/                  # SessionIdRegistry, modes, payload compiler
│   │   ├── context/               # Context builders, entity tiers
│   │   ├── memory/                # Conversation compression
│   │   ├── tools/                 # CRUD executor, schema, filters
│   │   ├── llm/                   # LLM client, model routing
│   │   ├── prompts/               # injection.py + templates/
│   │   ├── domain/                # DomainConfig protocol + registration
│   │   └── agents/                # Agent protocol (extension point)
│   │
│   ├── alfred_kitchen/            # Kitchen domain implementation
│   │   ├── domain/                # KitchenConfig, schema, formatters
│   │   ├── modes/                 # Cook mode, brainstorm mode
│   │   ├── tools/                 # Ingredient lookup, CRUD middleware
│   │   ├── web/                   # FastAPI app, routes, auth
│   │   ├── db/                    # Supabase client, adapter
│   │   ├── background/            # Profile builder, dashboard
│   │   ├── models/                # Pydantic entities
│   │   └── recipe_import/         # URL scraping, LLM parsing
│   │
│   └── onboarding/                # User onboarding flow
│
├── frontend/                      # React + TypeScript SPA
├── migrations/                    # SQL migration files
├── tests/                         # Test suite
└── docs/                          # Architecture documentation
```

## Development

```bash
pytest              # Run tests
ruff check src/     # Lint
ruff format src/    # Format
mypy src/           # Type check
```

## Documentation

See [docs/architecture/overview.md](docs/architecture/overview.md) for the full documentation index.

## License

MIT
