# Domain Implementation Guide

Step-by-step guide to creating a new domain for Alfred's orchestration engine. Uses a hypothetical FPL (Fantasy Premier League) domain as a worked example.

---

## 1. Prerequisites

Before implementing a domain, you need:

| Prerequisite | Example (FPL) |
|-------------|---------------|
| **Entity list** | Players, teams, transfers, squads, gameweeks |
| **Database** | Supabase project with tables for each entity |
| **Subdomain grouping** | squad management, transfers, analysis, gameweeks |
| **At least one persona** | "You are an FPL advisor..." per subdomain/step_type |
| **Basic examples** | Example CRUD interactions per subdomain |

You do NOT need: custom CRUD middleware, bypass modes, payload compilers, or full prompt replacement content. These are optional and can be added later.

---

## 2. Scaffold the Package

Create the package structure:

```
src/alfred_fpl/
├── __init__.py          # Registration hook
├── config.py            # FPLSettings (extends CoreSettings)
├── domain/
│   ├── __init__.py      # FPLConfig + FPL_DOMAIN singleton
│   ├── schema.py        # Field enums, fallback schemas
│   ├── formatters.py    # Record formatting
│   └── prompts/
│       └── system.md    # "You are Alfred, an FPL advisor..."
├── db/
│   └── client.py        # Supabase client wrapper
└── main.py              # CLI entry point (optional)
```

### Registration Hook

`src/alfred_fpl/__init__.py`:

```python
from alfred.domain import register_domain

def _register():
    from alfred_fpl.domain import FPL_DOMAIN
    register_domain(FPL_DOMAIN)

_register()
```

This mirrors the kitchen pattern at [alfred_kitchen/__init__.py](src/alfred_kitchen/__init__.py). Importing `alfred_fpl` anywhere in your app registers the domain.

---

## 3. Entity Definitions

Define your entities using `EntityDefinition` ([base.py:26](src/alfred/domain/base.py#L26)):

```python
from alfred.domain.base import EntityDefinition

FPL_ENTITIES = {
    "players": EntityDefinition(
        type_name="player",          # Refs: player_1, player_2, ...
        table="players",
        primary_field="web_name",    # Display name
        complexity="high",           # Think node prioritizes
        label_fields=["web_name"],
        detail_tracking=True,        # Track summary vs full reads
    ),
    "teams": EntityDefinition(
        type_name="team",
        table="teams",
        primary_field="name",
    ),
    "transfers": EntityDefinition(
        type_name="transfer",
        table="transfers",
        primary_field="player_id",
        fk_fields=["player_id", "team_id"],
        complexity="medium",
        label_fields=["player_id"],   # FK-based — enriched by registry
    ),
    "squads": EntityDefinition(
        type_name="squad",
        table="squad_selections",
        primary_field="gameweek",
        fk_fields=["player_id"],
        label_fields=["gameweek"],
    ),
    "gameweeks": EntityDefinition(
        type_name="gw",
        table="gameweeks",
        primary_field="number",
        label_fields=["number"],
    ),
}
```

### Key Fields

| Field | What It Controls |
|-------|-----------------|
| `type_name` | Ref prefix — `"player"` produces `player_1`, `player_2` |
| `table` | Database table name — used by CRUD executor |
| `primary_field` | Default display field for labels |
| `fk_fields` | Foreign keys — used for ref↔UUID translation and FK enrichment |
| `complexity` | Think node hint: `"high"` = stronger model, `"medium"` = standard, `None` = basic |
| `nested_relations` | Auto-include in reads (e.g., `["squad_players"]`) |
| `detail_tracking` | Track whether entity was read as summary or full detail |
| `label_fields` | Fields used to compute human-readable labels |

---

## 4. Subdomain Definitions

Group tables into logical subdomains using `SubdomainDefinition` ([base.py:54](src/alfred/domain/base.py#L54)):

```python
from alfred.domain.base import SubdomainDefinition

FPL_SUBDOMAINS = {
    "squad": SubdomainDefinition(
        name="squad",
        primary_table="squad_selections",
        related_tables=["players", "teams"],
        description="Squad management. Select 15 players within budget.",
    ),
    "transfers": SubdomainDefinition(
        name="transfers",
        primary_table="transfers",
        related_tables=["players", "teams"],
        description="Transfer operations. Buy/sell players, manage free transfers.",
    ),
    "analysis": SubdomainDefinition(
        name="analysis",
        primary_table="players",
        related_tables=["teams", "gameweeks"],
        description="Player and team analysis. Stats, fixtures, form.",
    ),
    "gameweeks": SubdomainDefinition(
        name="gameweeks",
        primary_table="gameweeks",
        related_tables=["squad_selections"],
        description="Gameweek planning. Captaincy, bench, chip usage.",
    ),
}
```

The `description` field is injected into Think prompts — it helps the LLM understand what each subdomain handles.

---

## 5. Implement DomainConfig

Create `FPLConfig` implementing all 24 abstract methods. Start with the required ones and use defaults for everything else.

```python
# src/alfred_fpl/domain/__init__.py

from typing import Any, Callable
from alfred.domain.base import DomainConfig, EntityDefinition, SubdomainDefinition


class FPLConfig(DomainConfig):

    # === Core Properties (3 abstract) ===

    @property
    def name(self) -> str:
        return "fpl"

    @property
    def entities(self) -> dict[str, EntityDefinition]:
        return FPL_ENTITIES  # defined above

    @property
    def subdomains(self) -> dict[str, SubdomainDefinition]:
        return FPL_SUBDOMAINS  # defined above

    # === Prompt/Persona (2 abstract) ===

    def get_persona(self, subdomain: str, step_type: str) -> str:
        personas = {
            "squad": "You are an FPL squad advisor. Focus on value picks and team balance.",
            "transfers": "You are an FPL transfer expert. Consider price changes and fixtures.",
            "analysis": "You are an FPL data analyst. Use stats, form, and fixtures.",
            "gameweeks": "You are an FPL gameweek planner. Optimize captaincy and bench.",
        }
        return personas.get(subdomain, "You are an FPL advisor.")

    def get_examples(self, subdomain: str, step_type: str,
                     step_description: str = "", prev_subdomain: str | None = None) -> str:
        # Start with minimal examples, expand as needed
        if step_type == "read" and subdomain == "squad":
            return '''## Examples
- Read current squad: `{"tool": "db_read", "params": {"table": "squad_selections", "filters": [{"field": "gameweek", "op": "eq", "value": 25}]}}`'''
        return ""

    # === Schema/FK (11 abstract) ===

    def get_table_format(self, table: str) -> dict[str, Any]:
        return {}  # Start with no custom formatting

    def get_empty_response(self, subdomain: str) -> str:
        return {
            "squad": "No squad selection found for this gameweek.",
            "transfers": "No transfers recorded.",
            "analysis": "No player data found.",
            "gameweeks": "No gameweek data available.",
        }.get(subdomain, "No data found.")

    def get_fk_enrich_map(self) -> dict[str, tuple[str, str]]:
        return {
            "player_id": ("players", "web_name"),
            "team_id": ("teams", "name"),
        }

    def get_field_enums(self) -> dict[str, dict[str, list[str]]]:
        return {
            "squad": {"position": ["GKP", "DEF", "MID", "FWD"]},
            "analysis": {"position": ["GKP", "DEF", "MID", "FWD"]},
        }

    def get_semantic_notes(self) -> dict[str, str]:
        return {
            "squad": "Squad has exactly 15 players: 2 GKP, 5 DEF, 5 MID, 3 FWD",
            "transfers": "Free transfers reset each gameweek. Hits cost 4 points.",
        }

    def get_fallback_schemas(self) -> dict[str, str]:
        return {}  # Use DB introspection; add fallbacks if it fails

    def get_scope_config(self) -> dict[str, dict]:
        return {
            "squad": {"can_access": ["analysis"]},
            "transfers": {"can_access": ["squad", "analysis"]},
        }

    def get_user_owned_tables(self) -> set[str]:
        return {"squad_selections", "transfers"}

    def get_uuid_fields(self) -> set[str]:
        return {"player_id", "team_id", "gameweek_id"}

    def get_subdomain_registry(self) -> dict[str, dict]:
        return {
            name: {"tables": [sd.primary_table] + sd.related_tables}
            for name, sd in FPL_SUBDOMAINS.items()
        }

    def get_subdomain_examples(self) -> dict[str, list[str]]:
        return {
            "squad": ["show my squad", "who's in my team"],
            "transfers": ["buy Salah", "sell my worst defender"],
            "analysis": ["compare strikers", "best midfielders under 8m"],
        }

    # === Entity Processing (4 abstract) ===

    def infer_entity_type_from_artifact(self, artifact: dict) -> str:
        if "web_name" in artifact or "position" in artifact:
            return "player"
        if "gameweek" in artifact and "player_id" in artifact:
            return "squad"
        return "transfer"

    def compute_entity_label(self, record: dict, entity_type: str, ref: str) -> str:
        if entity_type == "player":
            return record.get("web_name") or ref
        if entity_type == "team":
            return record.get("name") or ref
        if entity_type == "transfer":
            return f"Transfer {ref}"
        return record.get("name") or record.get("title") or ref

    def get_subdomain_aliases(self) -> dict[str, str]:
        return {
            "team": "squad",
            "my team": "squad",
            "buy": "transfers",
            "sell": "transfers",
            "stats": "analysis",
            "fixtures": "analysis",
            "captain": "gameweeks",
            "bench": "gameweeks",
        }

    def get_subdomain_formatters(self) -> dict[str, Callable]:
        return {}  # Start with no custom formatters — use generic

    # === Mode/Agent (2 abstract) ===

    @property
    def bypass_modes(self) -> dict[str, type]:
        return {}  # No bypass modes initially

    @property
    def default_agent(self) -> str:
        return "main"

    # === Handoff (1 abstract) ===

    def get_handoff_result_model(self) -> type:
        from alfred.modes.handoff import HandoffResult
        return HandoffResult  # Use base model — no domain-specific fields

    # === Database (1 abstract) ===

    def get_db_adapter(self):
        from alfred_fpl.db.client import get_client
        return get_client()


# Singleton
FPL_DOMAIN = FPLConfig()
```

### What You Get for Free

By implementing just these 24 methods, core provides:

- Full Understand → Think → Act → Reply → Summarize pipeline
- Entity refs: `player_1`, `team_3`, `transfer_2` (auto-generated from `type_name`)
- FK enrichment: `player_id: "abc-123"` → `player_id: "abc-123" (Salah)` in prompts
- CRUD execution with ref↔UUID translation
- Mode system (QUICK/PLAN/CREATE)
- Conversation memory with compression
- Prompt assembly with core templates as fallback

---

## 6. Database Adapter

Implement the `DatabaseAdapter` protocol ([db/adapter.py:23](src/alfred/db/adapter.py#L23)):

```python
# src/alfred_fpl/db/client.py

from supabase import create_client

_client = None

def get_client():
    """Return Supabase client (matches DatabaseAdapter protocol)."""
    global _client
    if _client is None:
        from alfred_fpl.config import settings
        _client = create_client(settings.supabase_url, settings.supabase_anon_key)
    return _client
```

The Supabase client already satisfies `DatabaseAdapter` — it has `.table()` and `.rpc()` methods. No wrapper needed.

---

## 7. CRUD Middleware (Optional)

If your domain needs query intelligence beyond raw CRUD, implement `CRUDMiddleware` ([base.py:97](src/alfred/domain/base.py#L97)):

```python
from alfred.domain.base import CRUDMiddleware, ReadPreprocessResult

class FPLCRUDMiddleware(CRUDMiddleware):

    async def pre_read(self, params, user_id) -> ReadPreprocessResult:
        # Example: auto-include current gameweek for squad reads
        if params.table == "squad_selections" and not any(
            f.field == "gameweek" for f in (params.filters or [])
        ):
            # Add current gameweek filter
            from alfred_fpl.db.client import get_current_gameweek
            gw = await get_current_gameweek()
            params.filters = (params.filters or []) + [
                FilterClause(field="gameweek", op="eq", value=gw)
            ]
        return ReadPreprocessResult(params=params)
```

Then wire it in `FPLConfig`:

```python
def get_crud_middleware(self):
    return FPLCRUDMiddleware()
```

---

## 8. Prompts

### Minimum: System Prompt

Create `src/alfred_fpl/domain/prompts/system.md`:

```markdown
You are Alfred, a Fantasy Premier League assistant.

You help managers make smart FPL decisions: squad selection, transfers,
captaincy, chip usage, and player analysis.

You have access to player stats, fixture data, and the manager's squad.
```

Wire it in `FPLConfig`:

```python
def get_system_prompt(self) -> str:
    path = Path(__file__).parent / "prompts" / "system.md"
    return path.read_text(encoding="utf-8")
```

### Progressive Enhancement

Start with core templates as fallback (they work generically). Override as you tune prompts:

| Priority | Method | What It Does |
|----------|--------|-------------|
| 1st | `get_system_prompt()` | Domain identity |
| 2nd | `get_persona()` + `get_examples()` | Per-subdomain guidance in Act prompts |
| 3rd | `get_think_prompt_content()` | Full Think prompt with FPL-specific planning examples |
| 4th | `get_act_prompt_content(step_type)` | Full Act prompt per step type with FPL examples |
| 5th | `get_reply_prompt_content()` | Reply formatting rules (stat tables, squad displays) |
| 6th | `get_understand_prompt_content()` | Reference resolution patterns for FPL entities |

Each override replaces the core template entirely for that node. See [prompt-assembly.md](prompt-assembly.md) for the full fallback chain.

---

## 9. Bypass Modes (Optional)

If your domain has interactive modes that skip the pipeline (like kitchen's cook mode):

```python
# src/alfred_fpl/domain/modes/draft.py

async def run_draft_session(user_message, conversation, user_id):
    """Interactive draft assistant — guides squad building."""
    yield {"type": "chunk", "content": "Let's build your squad..."}
    # ... interactive logic ...
    yield {"type": "done", "response": "Squad complete!", "conversation": conversation}
```

Wire it:

```python
@property
def bypass_modes(self) -> dict[str, type]:
    from alfred_fpl.domain.modes.draft import run_draft_session
    return {"draft": run_draft_session}
```

---

## 10. Testing

### With StubDomainConfig (Core Tests)

Test core behavior without your domain:

```python
from alfred.domain import register_domain
from alfred.domain.base import DomainConfig, EntityDefinition

class StubConfig(DomainConfig):
    # Minimal implementation — 2 entities, 1 subdomain
    ...

register_domain(StubConfig())
```

### With Your Domain (Integration Tests)

```python
import alfred_fpl  # triggers registration

async def test_squad_read():
    from alfred.graph.workflow import run_alfred
    response, conversation = await run_alfred(
        user_message="show my squad",
        user_id="test-user",
    )
    assert "squad" in response.lower() or "player" in response.lower()
```

### What to Test First

| Test | What It Validates |
|------|-------------------|
| Entity registration | `domain.entities` has expected keys, `table_to_type` maps correctly |
| FK enrichment | `get_fk_enrich_map()` returns valid table/column pairs |
| Persona loading | `get_persona("squad", "read")` returns non-empty string |
| CRUD round-trip | `db_read` on a known table returns data with refs |
| Quick mode | "show my squad" → QUICK mode → single CRUD call → formatted response |

---

## Checklist

Steps to go from zero to working domain:

- [ ] Create `src/alfred_{name}/` package
- [ ] Implement `__init__.py` with `_register()` hook
- [ ] Define `EntityDefinition` instances for each entity type
- [ ] Define `SubdomainDefinition` instances for each subdomain group
- [ ] Implement all 24 abstract methods in `DomainConfig`
- [ ] Create `db/client.py` returning a `DatabaseAdapter`-compatible client
- [ ] Create `prompts/system.md` with domain identity
- [ ] Write `get_persona()` for each subdomain
- [ ] Write basic `get_examples()` for common CRUD patterns
- [ ] Register in entry point (`main.py`, `server.py`, or test conftest)
- [ ] Test: entity refs appear correctly (`player_1`, `team_2`)
- [ ] Test: basic CRUD works (read, create)
- [ ] Test: quick mode produces formatted responses

### Optional Enhancements (Add Later)

- [ ] `CRUDMiddleware` for query intelligence
- [ ] Full prompt replacement content (Think, Act, Reply, Understand)
- [ ] `SubdomainCompiler` for artifact→schema mapping
- [ ] Bypass modes for interactive features
- [ ] Custom `format_entity_for_context()` for rich entity display
- [ ] Custom `format_records_for_reply()` for user-facing formatting
