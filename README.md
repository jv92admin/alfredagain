# Alfred V2

A modern LangGraph-based multi-agent assistant for kitchen, fitness, and wine management.

## Features

- **Pantry Agent** - Kitchen inventory, recipes, meal planning
- **Coach Agent** - Fitness tracking, workout planning (coming soon)
- **Cellar Agent** - Wine collection management (coming soon)

## Architecture

Alfred uses a LangGraph pipeline with four nodes:

```
Router → Think → Act Loop → Reply
```

- **Router**: Classifies intent, picks agent, sets complexity
- **Think**: Domain-specific planning, generates natural language steps
- **Act Loop**: Executes steps via tools with structured actions
- **Reply**: Synthesizes final response with agent persona

## Tech Stack

| Layer | Technology |
|-------|------------|
| Orchestration | LangGraph |
| Structured Output | Instructor |
| Database | Supabase (Postgres + pgvector) |
| Auth | Supabase Auth |
| Models | gpt-4o-mini / gpt-4o / o1 |
| CLI | Typer + Rich |
| Deployment | Railway |
| Observability | LangSmith |

## Setup

### Prerequisites

- Python 3.11+
- Supabase account
- OpenAI API key
- Railway account (for deployment)

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/alfred-v2.git
   cd alfred-v2
   ```

2. Create virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
   ```

3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Copy environment file and fill in values:
   ```bash
   cp .env.example .env
   ```

5. Run the CLI:
   ```bash
   alfred health  # Check configuration
   alfred chat    # Start interactive chat
   ```

### Database Setup

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Enable the `vector` extension in Database → Extensions
3. Run the migration in SQL Editor:
   ```sql
   -- Copy contents of migrations/001_core_tables.sql
   ```

## Development

```bash
# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/

# Format code
ruff format src/
```

## Project Structure

```
alfred-v2/
├── src/alfred/
│   ├── graph/          # LangGraph orchestration
│   ├── agents/         # Domain agents (pantry, coach, cellar)
│   ├── db/             # Supabase integration
│   ├── llm/            # LLM infrastructure
│   ├── tools/          # Tool definitions
│   ├── memory/         # Long-term memory
│   ├── config.py       # Settings
│   ├── main.py         # CLI entry point
│   └── server.py       # Health check server
├── prompts/            # LLM prompts and constitutions
├── migrations/         # SQL migration files
├── tests/              # Test suite
└── docs/               # Documentation
```

## License

MIT

