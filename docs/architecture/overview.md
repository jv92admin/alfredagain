# Alfred Architecture Overview

> Entry point for understanding Alfred's technical architecture.

---

## Two-Package Structure

Alfred is split into two Python packages:

- **`alfred`** (core) — Domain-agnostic orchestration engine: LangGraph pipeline, entity tracking, CRUD execution, prompt assembly, conversation memory
- **`alfred_kitchen`** (domain) — Kitchen-specific implementation: entities, subdomains, prompts, database adapter, CRUD middleware, bypass modes

Core never imports kitchen. Kitchen imports core freely. See [core-domain-architecture.md](core-domain-architecture.md) for the full protocol.

---

## Pipeline

```
                              ┌─────────────┐
                              │  ACT QUICK  │ ← Single tool call
                              └──────┬──────┘
                                     │
┌────────────┐   quick_mode?   ┌─────▼─────┐   ┌───────────┐
│ UNDERSTAND │───────────────▶│   REPLY   │──▶│ SUMMARIZE │
└─────┬──────┘                 └───────────┘   └───────────┘
      │
      │ !quick_mode
      ▼
┌───────┐   ┌─────────────────┐   ┌───────┐   ┌───────────┐
│ THINK │──▶│    ACT LOOP     │──▶│ REPLY │──▶│ SUMMARIZE │
└───────┘   └─────────────────┘   └───────┘   └───────────┘
```

---

## Documentation Index

### Internals (how it works)

| Doc | Covers |
|-----|--------|
| [crud-and-database.md](crud-and-database.md) | CRUD executor, DatabaseAdapter, middleware hooks, filter system, ref translation |
| [sessions-context-entities.md](sessions-context-entities.md) | SessionIdRegistry, entity lifecycle, context builders, conversation memory |
| [pipeline-stages.md](pipeline-stages.md) | Graph nodes, routing, state shape, input/output contracts per stage |
| [prompt-assembly.md](prompt-assembly.md) | Template loading, injection.py composition, domain prompt overrides |

### Architecture (how it's structured)

| Doc | Covers |
|-----|--------|
| [core-domain-architecture.md](core-domain-architecture.md) | Two-package split, DomainConfig protocol (66 methods), registration, import boundary |
| [core-public-api.md](core-public-api.md) | Entry points, capabilities table, extension points, multi-repo extraction path |
| [domain-implementation-guide.md](domain-implementation-guide.md) | Step-by-step guide to building a new domain (FPL worked example) |

### Operations

| Doc | Covers |
|-----|--------|
| [capabilities.md](capabilities.md) | User-facing capabilities and API surface |
| [../ROADMAP.md](../ROADMAP.md) | Active work, recently completed, backlog |
