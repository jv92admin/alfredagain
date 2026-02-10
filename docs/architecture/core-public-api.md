# Core Public API

What `alfred` (core) provides — entry points, capabilities, extension points, and the path to standalone extraction.

---

## 1. Entry Points

### Primary: `run_alfred_streaming()`

[workflow.py:672](src/alfred/graph/workflow.py#L672) — the main entry point for processing user requests with real-time updates.

```python
async def run_alfred_streaming(
    user_message: str,
    user_id: str,
    conversation_id: str | None = None,
    conversation: dict | None = None,
    mode: str = "plan",
    ui_changes: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
```

Yields 11 typed events as the pipeline executes (thinking, step, step_complete, done, etc.). The `done` event contains the final response and updated conversation state.

### Batch: `run_alfred()`

[workflow.py:530](src/alfred/graph/workflow.py#L530) — returns `(response, conversation)` tuple without streaming. Used by CLI and tests.

### Simple: `run_alfred_simple()`

[workflow.py:657](src/alfred/graph/workflow.py#L657) — returns just the response string. For single-turn interactions.

### Registration: `register_domain()`

[domain/__init__.py:29](src/alfred/domain/__init__.py#L29) — registers a `DomainConfig` implementation. Must be called before any entry point.

```python
from alfred.domain import register_domain
register_domain(my_domain)
```

### Graph Construction: `create_alfred_graph()`

[workflow.py:427](src/alfred/graph/workflow.py#L427) — builds the LangGraph `StateGraph`. Called internally by the entry points above. Not typically called by domains directly.

---

## 2. Capabilities Table

What core gives a domain for free:

| Capability | Module | What You Get |
|-----------|--------|-------------|
| **LLM pipeline** | `graph/workflow.py` | Understand → Think → Act (loop) → Reply → Summarize with conditional routing, 3 entry paths |
| **Entity lifecycle** | `core/id_registry.py` | UUID→human refs (`recipe_1`), detail level tracking, FK enrichment, cross-turn persistence |
| **CRUD execution** | `tools/crud.py` | Filter building (12 operators), ref↔UUID translation, user_id scoping, batch manifests |
| **Conversation memory** | `memory/conversation.py` | Turn history with compression, engagement summaries, context windowing (full vs condensed) |
| **Prompt assembly** | `prompts/injection.py` | 15-section Act prompt builder, quick mode prompts, subdomain guidance injection |
| **Prompt templates** | `prompts/templates/` | 11 structural .md templates (1,635 lines) as fallback when domain doesn't provide full prompts |
| **Mode system** | `core/modes.py` | QUICK/PLAN/CREATE modes with per-mode config (max_steps, skip_think, proposal_required) |
| **Context building** | `context/builders.py` | Think/Act/Understand context assembly from state, entity context tiering |
| **LLM client** | `llm/client.py` | `call_llm()` with structured output via Instructor, model routing by complexity |
| **Model routing** | `llm/model_router.py` | Complexity→model mapping (low→mini, medium→standard, high→premium) |
| **Observability** | `observability/` | LangSmith tracing, session logging, prompt logging |
| **Agent protocol** | `agents/base.py` | `AgentProtocol`, `AgentRouter`, `MultiAgentOrchestrator` (Phase 2.5) |
| **Payload compilation** | `core/payload_compiler.py` | `SubdomainCompiler` protocol, `PayloadCompilerRegistry` for artifact→schema mapping |
| **State model** | `graph/state.py` | `AlfredState` TypedDict with all data models (ThinkStep, ActDecision, BatchManifest, etc.) |
| **Handoff protocol** | `modes/handoff.py` | Bypass mode → graph pipeline handoff with structured summaries |

---

## 3. Extension Points

These are the protocols and hooks a domain implements to customize core behavior:

### DomainConfig (66 methods)

[domain/base.py:156](src/alfred/domain/base.py#L156) — the central protocol. See [core-domain-architecture.md](core-domain-architecture.md) for the full method census.

24 abstract methods define what a domain **is** (entities, subdomains, personas). 42 default methods provide fallbacks that a domain can progressively override.

### DatabaseAdapter

[db/adapter.py:23](src/alfred/db/adapter.py#L23) — how core accesses the database.

```python
class DatabaseAdapter(Protocol):
    def table(self, name: str) -> Any      # query builder
    def rpc(self, function_name: str, params: dict) -> Any
```

Returned by `DomainConfig.get_db_adapter()`. Core's CRUD executor calls `adapter.table(name).select(...).eq(...).execute()` — the query builder must support PostgREST-style fluent methods.

### CRUDMiddleware

[domain/base.py:97](src/alfred/domain/base.py#L97) — optional query intelligence layer.

```python
class CRUDMiddleware:
    async def pre_read(self, params, user_id) -> ReadPreprocessResult
    async def pre_write(self, table, records) -> list[dict]
    def deduplicate_batch(self, table, records) -> list[dict]
```

Returned by `DomainConfig.get_crud_middleware()`. Fires inside `execute_crud()` before database operations. Default: pass-through (no middleware).

### SubdomainCompiler

[core/payload_compiler.py:50](src/alfred/core/payload_compiler.py#L50) — maps generated artifacts to schema-ready payloads.

```python
class SubdomainCompiler(ABC):
    @property
    def subdomain(self) -> str: ...
    def compile(self, artifacts, context) -> CompilationResult: ...
```

Returned by `DomainConfig.get_payload_compilers()`. Runs between Generate and Write steps. Default: no compilers (artifacts pass through raw).

### AgentProtocol

[agents/base.py:50](src/alfred/agents/base.py#L50) — for multi-agent routing (Phase 2.5, not yet active).

```python
class AgentProtocol(ABC):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def capabilities(self) -> list[str]: ...
    async def process(self, state: AgentState) -> dict: ...
    async def process_streaming(self, state: AgentState) -> AsyncIterator[StreamEvent]: ...
```

Returned by `DomainConfig.agents`. Currently unused — kitchen runs in single-agent mode.

### Bypass Modes

`DomainConfig.bypass_modes` — dict mapping mode name to handler function. These skip the LangGraph pipeline entirely. Kitchen registers `cook` and `brainstorm` modes.

The handler function receives the user message and conversation state, yields streaming events directly, and produces a handoff summary for the pipeline to process when the mode completes.

---

## 4. What Domain Does NOT Touch

These are internal to core — domains never import or interact with them directly:

| Component | Why Hands-Off |
|-----------|--------------|
| Graph wiring (`workflow.py:427-512`) | Node connections, conditional edges, routing logic — all domain-agnostic |
| LLM client internals (`llm/client.py`) | `call_llm()` handles model selection, Instructor, retries — domains just call it |
| SessionIdRegistry internals (`core/id_registry.py`) | Ref allocation, detail tracking, FK enrichment — driven by `EntityDefinition` config |
| Conversation compression (`memory/conversation.py`) | Turn summarization, context windowing — generic text operations |
| Prompt template loading/caching | Module-level caches in each node — transparent to domains |
| Entity context tiering | Active/long-term/generated classification — driven by recency and `EntityDefinition` |
| Batch manifest tracking | Per-item status in Write steps — core handles the lifecycle |
| Step execution loop (`act_node()`) | Tool call → execute → cache → loop mechanics — domain provides the intelligence via prompts |
| Filter application (`apply_filter()`) | 12 PostgREST operators — domain provides filters via CRUD middleware |

---

## 5. Multi-Repo Extraction

The codebase is currently a mono-repo with both packages in `src/`. The architecture supports extracting `alfred` into a standalone `pip install alfred` package.

### Current State

Single `pyproject.toml` at repo root builds both packages:

```toml
[project]
name = "alfred"

[tool.hatch.build.targets.wheel]
packages = ["src/alfred", "src/alfred_kitchen", "src/onboarding"]
```

### What Standalone `alfred` Would Need

**Dependencies** (core only — no Supabase, no FastAPI):

```toml
[project]
name = "alfred"
dependencies = [
    "langgraph>=0.2.0",
    "langchain-openai>=0.2.0",
    "langsmith>=0.1.0",
    "instructor>=1.4.0",
    "openai>=1.50.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
]
```

**Not in core:** `supabase`, `fastapi`, `uvicorn`, `recipe-scrapers`, `httpx`, `bcrypt`, `typer`, `rich`

### Backwards-Compat Shims to Remove

Three `__getattr__` shims in core currently import from `alfred_kitchen` for backwards compatibility. These must be removed for standalone extraction:

| File | Shim | What It Redirects |
|------|------|-------------------|
| [db/__init__.py:15](src/alfred/db/__init__.py#L15) | `get_client` → `alfred_kitchen.db.client` | Supabase client access |
| [config.py:84](src/alfred/config.py#L84) | `Settings`, `get_settings`, `settings` → `alfred_kitchen.config` | Kitchen-specific config |
| [tools/schema.py:344](src/alfred/tools/schema.py#L344) | 6 constants → `get_current_domain()` | Already routes through DomainConfig (safe) |

The `tools/schema.py` shim is already clean — it routes through `get_current_domain()`, not a direct kitchen import. The `db/__init__.py` and `config.py` shims are the two that would break standalone core.

### What Breaks When Shims Are Removed

- `from alfred.db import get_client` → must change to `from alfred_kitchen.db.client import get_client`
- `from alfred.config import settings` → must change to `from alfred_kitchen.config import settings` (or use `from alfred.config import core_settings` for core-only fields)

All such callers are already in `alfred_kitchen/` or `scripts/` — core code doesn't use these shims.

### Import Boundary Enforcement

```bash
# Must return zero hits for standalone core:
grep -rn "from alfred_kitchen" src/alfred/ --include="*.py"

# Currently returns hits in __getattr__ shims only
```

### When to Extract

Extraction is deferred to Phase 5+ (after FPL domain validates the protocol). The mono-repo approach works well for now — one commit changes protocol + all consumers. When a second domain is concrete, extraction becomes worthwhile.

---

## Key Files

| File | Lines | Role |
|------|-------|------|
| [src/alfred/graph/workflow.py](src/alfred/graph/workflow.py) | 993 | Entry points: `run_alfred_streaming()`, `run_alfred()`, `create_alfred_graph()` |
| [src/alfred/domain/base.py](src/alfred/domain/base.py) | 1,135 | DomainConfig protocol (66 methods) |
| [src/alfred/domain/__init__.py](src/alfred/domain/__init__.py) | 79 | `register_domain()`, `get_current_domain()` |
| [src/alfred/db/adapter.py](src/alfred/db/adapter.py) | 53 | DatabaseAdapter protocol |
| [src/alfred/core/payload_compiler.py](src/alfred/core/payload_compiler.py) | 174 | SubdomainCompiler, PayloadCompilerRegistry |
| [src/alfred/agents/base.py](src/alfred/agents/base.py) | 319 | AgentProtocol, AgentRouter, MultiAgentOrchestrator |
| [pyproject.toml](pyproject.toml) | 81 | Current mono-repo build config |
