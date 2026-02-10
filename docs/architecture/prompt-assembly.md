# Prompt Assembly

How prompts are built for each pipeline node — template loading, dynamic injection, domain overrides.

---

## 1. Prompt Composition Model

Every pipeline node sends an LLM call with a **system prompt** and a **user prompt**. The system prompt defines the LLM's role and rules; the user prompt provides the specific context for the current request.

Prompts are assembled from two sources:

- **Core templates** — structural skeletons in `src/alfred/prompts/templates/*.md`. Define the node's role, output contract, and generic mechanics.
- **Domain content** — domain-specific examples, personas, entity-specific text. Provided by `DomainConfig` methods.

### The Fallback Chain

Every node follows the same resolution pattern:

```
1. Call domain.get_{node}_prompt_content()
   ↓ returns non-empty string?  →  USE IT (full replacement)
   ↓ returns ""?
2. Load core template from prompts/templates/{node}.md
3. Inject domain variables into template placeholders
4. Append domain.get_{node}_prompt_injection() if provided
```

This creates two override strategies:

| Strategy | DomainConfig Method | Effect |
|----------|-------------------|--------|
| **Full replacement** (preferred) | `get_{node}_prompt_content()` | Domain provides the entire prompt. Core template ignored. |
| **Template + injection** (fallback) | `get_{node}_domain_context()` + `get_{node}_prompt_injection()` | Core template used as skeleton. Domain fills placeholders and/or appends content. |

Kitchen uses **full replacement** for all nodes (Think, Act, Reply, Understand). The core templates exist as fallbacks for domains that don't provide full prompts.

### Why Two Strategies

Full replacement gives domains total control over prompt wording — critical because small phrasing changes affect LLM behavior. The template+injection fallback lets a new domain start with reasonable prompts by just filling in entity names and examples, without writing 500+ lines of prompt content from scratch.

---

## 2. Template Files

Core templates live in `src/alfred/prompts/templates/`:

| File | Lines | Purpose |
|------|-------|---------|
| `think.md` | 382 | Think node: step planning, decision types (plan_direct, propose, clarify), step_type definitions, entity handling rules |
| `understand.md` | 307 | Understand node: reference resolution, entity curation, quick mode detection, confirmation/rejection signals |
| `reply.md` | 158 | Reply node: narration rules, editorial principles, formatting guidelines |
| `summarize.md` | 166 | Summarize node: history management, turn compression, engagement summary rules |
| `router.md` | 36 | Router node: agent classification (currently single-agent, so minimal) |
| `act/base.md` | 73 | Act node base: execution engine role, core principles (one action per response, step ownership) |
| `act/crud.md` | 37 | CRUD tools reference: db_read/db_create/db_update/db_delete parameters, filter operators |
| `act/read.md` | 151 | READ step: query construction, filter patterns, multi-query strategies, empty result handling |
| `act/write.md` | 101 | WRITE step: FK handling, batch operations, linked record creation, error recovery |
| `act/analyze.md` | 107 | ANALYZE step: no DB calls, reasoning over data from previous steps, analysis patterns |
| `act/generate.md` | 117 | GENERATE step: entity tagging with `gen_*` refs, quality principles, no DB calls |

**Total:** 1,635 lines of core template content.

### Act Template Layering

The Act node is unique — it has 6 template files that get composed into a single system prompt. The assembly order depends on step type:

```
base.md              ← always included (execution engine role)
  + crud.md          ← only for read/write steps (tool reference)
  + {step_type}.md   ← read.md, write.md, analyze.md, or generate.md
  + domain injection ← domain.get_act_prompt_injection(step_type)
```

Joined with `\n\n---\n\n` separators (see [act.py:338-381](src/alfred/graph/nodes/act.py#L338-L381)).

---

## 3. Act Prompt Deep Dive

The Act node has the most complex prompt assembly because it handles 4 step types with different requirements and loops within a step.

### System Prompt Assembly

`_get_system_prompt(step_type)` at [act.py:338](src/alfred/graph/nodes/act.py#L338) builds the system prompt:

1. Check `domain.get_act_prompt_content(step_type)` — if non-empty, return it directly
2. Otherwise, layer core templates: `base.md` → `crud.md` (read/write only) → `{step_type}.md`
3. Append `domain.get_act_prompt_injection(step_type)` if non-empty

Kitchen provides full replacement prompts via [act_content.py](src/alfred_kitchen/domain/prompts/act_content.py) (696 lines) — one pre-assembled prompt per step type that includes the base layer, CRUD tools, step mechanics, and kitchen-specific examples all in one string.

### User Prompt Assembly

`build_act_user_prompt()` at [injection.py:49](src/alfred/prompts/injection.py#L49) assembles the user prompt from 15 sections. It delegates to two builders:

- `_build_common_sections()` at [injection.py:215](src/alfred/prompts/injection.py#L215) — 6 sections present in every step type
- `_build_step_type_sections()` at [injection.py:323](src/alfred/prompts/injection.py#L323) — variable sections that depend on step type

### The 15 Sections (Assembly Order)

The final prompt is joined with `\n\n` separators. Sections are ordered for optimal LLM attention:

| # | Section | Source | When Included |
|---|---------|--------|---------------|
| 1 | Subdomain header | `domain.get_act_subdomain_header(subdomain, step_type)` | Always (if domain provides) |
| 2 | Schema | `get_schema_with_fallback(subdomain)` | read, write, generate |
| 3 | User preferences (write) | `domain.get_user_profile()` + subdomain guidance | write only |
| 4 | STATUS table | Built inline: step N of M, goal, type, progress, date | Always |
| 5 | Previous step note | `state["prev_step_note"]` | read, write (if present) |
| 6 | User profile | `domain.get_user_profile()` | analyze, generate |
| 7 | Subdomain guidance | `domain.get_subdomain_guidance()` | analyze, generate |
| 8 | Task | Step description + user's full request | Always |
| 9 | Batch manifest | `BatchManifest.to_prompt_table()` | write (if batch active) |
| 10 | Guidance/examples | `domain.get_examples(subdomain, step_type, ...)` | Always (if domain provides) |
| 11 | Data section | Previous turn steps + previous step results + current step tool results | Always |
| 12 | Entities in Context | `build_act_entity_context()` output | Always |
| 13 | Artifacts | Generated `gen_*` content from SessionIdRegistry | write, generate, analyze |
| 14 | Conversation context | `format_full_context()` | Always |
| 15 | Decision prompt | `_build_decision_section(step_type)` | Always |

### Section Details

**STATUS table** (section 4) — A markdown table showing step index, goal, type, tool call count (read/write), and today's date. Provides the LLM with progress awareness.

**Task** (section 8) — Two parts: "Your job this step: {step_description}" and the user's full original request with a note that other parts are handled by later steps.

**Data section** (section 11) — Three layers of results:
- Previous turn context (last 2 steps from prior turn)
- Previous step results this turn (summarized for older steps, full for recent)
- Current step tool results (what this step's tool calls returned so far)

**Entities in Context** (section 12) — The 5-tier entity context from `build_act_entity_context()`. See [sessions-context-entities.md](sessions-context-entities.md) for the full breakdown.

**Artifacts** (section 13) — Full JSON dumps of generated `gen_*` content. Write steps use this to know what to save; analyze steps use it to reason about generated content.

**Decision prompt** (section 15) — Step-type-specific output instructions:
- analyze/generate: `step_complete` only (no DB calls allowed)
- read/write: `tool_call` or `step_complete`

Built by `_build_decision_section()` at [injection.py:408](src/alfred/prompts/injection.py#L408).

### Where Act Gathers Its Data

The `act_node()` function at [act.py:980](src/alfred/graph/nodes/act.py#L980) collects all prompt inputs before calling `build_act_user_prompt()`:

| Data | Source | Lines |
|------|--------|-------|
| Previous step results | `_format_step_results(step_results, current_step_index)` | [act.py:1084](src/alfred/graph/nodes/act.py#L1084) |
| Current step tool results | `_format_current_step_results(current_step_tool_results)` | [act.py:1090](src/alfred/graph/nodes/act.py#L1090) |
| Conversation context | `format_full_context(conversation, ...)` | [act.py:1093](src/alfred/graph/nodes/act.py#L1093) |
| Previous turn steps | `_format_previous_turn_steps(conversation)` | [act.py:1098](src/alfred/graph/nodes/act.py#L1098) |
| Content archive | `state["content_archive"]` | [act.py:1101](src/alfred/graph/nodes/act.py#L1101) |
| Entity context | `build_act_entity_context(session_registry, ...)` | [act.py:1159](src/alfred/graph/nodes/act.py#L1159) |
| User profile | `domain.get_user_profile(user_id)` | [act.py:1174](src/alfred/graph/nodes/act.py#L1174) |
| Subdomain guidance | `domain.get_subdomain_guidance(user_id)` | [act.py:1176](src/alfred/graph/nodes/act.py#L1176) |
| Schema | `get_schema_with_fallback(subdomain)` | [act.py:1196](src/alfred/graph/nodes/act.py#L1196) |
| Batch manifest | `state["current_batch_manifest"]` | [act.py:1205](src/alfred/graph/nodes/act.py#L1205) |
| Pending artifacts | `session_registry.get_all_pending_artifacts()` | [act.py:1127](src/alfred/graph/nodes/act.py#L1127) |

The assembled user prompt is passed to `call_llm()` alongside `_get_system_prompt(step_type)` at [act.py:1239-1244](src/alfred/graph/nodes/act.py#L1239-L1244).

---

## 4. Domain Prompt Override Chain

Each node has a specific pattern for how domain content integrates with core templates.

### Act Node

```python
# act.py:338 — _get_system_prompt(step_type)
domain_content = domain.get_act_prompt_content(step_type)  # Full replacement
if domain_content:
    return domain_content
# Fallback: base.md + crud.md + {step_type}.md + domain injection
domain_injection = domain.get_act_prompt_injection(step_type)
```

**DomainConfig methods:**
- `get_act_prompt_content(step_type)` → full system prompt ([base.py:946](src/alfred/domain/base.py#L946))
- `get_act_prompt_injection(step_type)` → appended to template assembly ([base.py:965](src/alfred/domain/base.py#L965))

**Kitchen implementation:** [act_content.py](src/alfred_kitchen/domain/prompts/act_content.py) provides pre-assembled prompts per step type. [act_injections.py](src/alfred_kitchen/domain/prompts/act_injections.py) provides injections as fallback (unused when content is provided).

### Think Node

```python
# think.py:81 — _get_system_prompt()
domain_content = domain.get_think_prompt_content()  # Full replacement
if domain_content:
    _SYSTEM_PROMPT = domain_content
else:
    raw = _PROMPT_PATH.read_text(encoding="utf-8")  # Core template
    _SYSTEM_PROMPT = raw.replace("{domain_context}", domain.get_think_domain_context())
                        .replace("{domain_planning_guide}", domain.get_think_planning_guide())
```

**DomainConfig methods:**
- `get_think_prompt_content()` → full system prompt ([base.py:981](src/alfred/domain/base.py#L981))
- `get_think_domain_context()` → fills `{domain_context}` placeholder ([base.py:1011](src/alfred/domain/base.py#L1011))
- `get_think_planning_guide()` → fills `{domain_planning_guide}` placeholder ([base.py:1023](src/alfred/domain/base.py#L1023))

**Kitchen implementation:** [think_content.py](src/alfred_kitchen/domain/prompts/think_content.py) (577 lines) provides the full prompt. [think_injections.py](src/alfred_kitchen/domain/prompts/think_injections.py) provides the two placeholder values as fallback.

### Reply Node

```python
# reply.py:36 — _get_prompts()
_SYSTEM_PROMPT = domain.get_system_prompt()  # Identity prompt (always from domain)

domain_content = domain.get_reply_prompt_content()  # Full replacement
if domain_content:
    _REPLY_PROMPT = domain_content
else:
    raw = _REPLY_PROMPT_PATH.read_text(encoding="utf-8")  # Core template
    _REPLY_PROMPT = raw.replace("{domain_subdomain_guide}", domain.get_reply_subdomain_guide())
```

Reply is unique: it uses **two** prompts. The system prompt is the domain's identity statement (`get_system_prompt()`, e.g., "You are Alfred, a helpful kitchen assistant"). The reply instructions are a separate prompt providing formatting rules.

**DomainConfig methods:**
- `get_system_prompt()` → identity statement ([base.py:735](src/alfred/domain/base.py#L735))
- `get_reply_prompt_content()` → full reply instructions ([base.py:931](src/alfred/domain/base.py#L931))
- `get_reply_subdomain_guide()` → fills `{domain_subdomain_guide}` placeholder ([base.py:1036](src/alfred/domain/base.py#L1036))

**Kitchen implementation:** [system.md](src/alfred_kitchen/domain/prompts/system.md) (32 lines) defines Alfred's identity. [reply_content.py](src/alfred_kitchen/domain/prompts/reply_content.py) (299 lines) provides full reply instructions. [reply_guide.py](src/alfred_kitchen/domain/prompts/reply_guide.py) (137 lines) provides the subdomain guide as fallback.

### Understand Node

```python
# understand.py:72-74
domain_content = domain.get_understand_prompt_content()  # Full replacement
base_prompt = domain_content if domain_content else _load_prompt()  # Core template fallback
full_prompt = f"{base_prompt}\n\n---\n\n# Current Request\n\n{context}"
```

Understand uses an inline system prompt (hardcoded at [understand.py:88-93](src/alfred/graph/nodes/understand.py#L88-L93)) describing the memory manager role. The domain content or core template provides the user prompt body, with request-specific context appended.

**DomainConfig method:**
- `get_understand_prompt_content()` → full prompt body ([base.py:996](src/alfred/domain/base.py#L996))

**Kitchen implementation:** [understand_content.py](src/alfred_kitchen/domain/prompts/understand_content.py) (317 lines) provides reference resolution patterns, quick mode table, curation examples.

### Router Node

```python
# router.py:24 — _get_system_prompt()
raw = _PROMPT_PATH.read_text(encoding="utf-8")
router_content = domain.get_router_prompt_injection()
_SYSTEM_PROMPT = raw.replace("{domain_router_content}", router_content)
```

Router has no full-replacement option — it always uses the core template with injection. This is because routing is currently minimal (single-agent mode) and the template is only 36 lines.

**DomainConfig method:**
- `get_router_prompt_injection()` → fills `{domain_router_content}` placeholder ([base.py:1049](src/alfred/domain/base.py#L1049))

**Kitchen implementation:** [router_content.py](src/alfred_kitchen/domain/prompts/router_content.py) (17 lines) defines the kitchen agent.

### Summarize Node

Summarize uses **no template files**. All its system prompts are inline strings within the node code:

- Turn summary: "Summarize what was accomplished in ONE sentence." ([summarize.py:496](src/alfred/graph/nodes/summarize.py#L496))
- Response summary: "Summarize this response using EXACT names..." ([summarize.py:518](src/alfred/graph/nodes/summarize.py#L518))
- History compression: "Summarize this conversation exchange..." ([summarize.py:552](src/alfred/graph/nodes/summarize.py#L552))
- Engagement summary: "Update the session summary..." ([summarize.py:664](src/alfred/graph/nodes/summarize.py#L664))

These are domain-agnostic tasks (summarizing text), so no domain override is needed.

---

## 5. Persona and Examples Injection

Three `DomainConfig` methods control per-subdomain content injection into Act prompts:

### `get_persona(subdomain, step_type)`

Returns the persona/guidance text for a subdomain and step type. Used by `build_act_quick_prompt()` at [injection.py:601](src/alfred/prompts/injection.py#L601) for quick mode's guidance section.

**Abstract method** — every domain must implement. Defined at [base.py:248](src/alfred/domain/base.py#L248).

### `get_examples(subdomain, step_type, step_description, prev_subdomain)`

Returns contextual example interactions. Called by `_build_step_type_sections()` at [injection.py:365](src/alfred/prompts/injection.py#L365) to populate the guidance/examples section (#10 in the 15-section layout).

The `step_description` and `prev_subdomain` parameters enable context-sensitive example selection — the domain can return different examples based on what the step is doing and what subdomain the previous step targeted.

**Abstract method** — every domain must implement. Defined at [base.py:261](src/alfred/domain/base.py#L261).

### `get_act_subdomain_header(subdomain, step_type)`

Returns a combined subdomain intro + persona + scope block used at the top of Act prompts (section #1). Called by `_build_step_type_sections()` at [injection.py:360](src/alfred/prompts/injection.py#L360).

**Has a default** (empty string) — optional override. Defined at [base.py:283](src/alfred/domain/base.py#L283).

### How They Flow Into Prompts

```
Act System Prompt (from _get_system_prompt):
  └── domain.get_act_prompt_content() or template layers

Act User Prompt (from build_act_user_prompt):
  ├── Section 1:  domain.get_act_subdomain_header()
  ├── Section 10: domain.get_examples()
  └── domain.get_persona()  ← only in quick mode via build_act_quick_prompt
```

In full Act mode, `get_persona()` is not called directly — the persona is embedded in `get_act_subdomain_header()` and `get_examples()`. In quick mode, `build_act_quick_prompt()` calls both `get_act_subdomain_header()` and `get_persona()` separately at [injection.py:600-601](src/alfred/prompts/injection.py#L600-L601).

---

## 6. Subdomain Guidance

Subdomain guidance is a generic mechanism for injecting per-subdomain user preferences into prompts. The guidance content comes from user profile data (stored in the database), not hardcoded domain code.

### The Mechanism

Three functions in [injection.py:452-529](src/alfred/prompts/injection.py#L452-L529):

| Function | Purpose | Used By |
|----------|---------|---------|
| `get_subdomain_guidance(user_profile, subdomain)` | Extract one subdomain's guidance from profile dict | Act node |
| `format_subdomain_guidance_section(user_profile, subdomain)` | Format as `## User Preferences ({subdomain})` section | Act node |
| `format_all_subdomain_guidance(user_profile)` | Format all subdomains' guidance into one section | Think node |

### Where It Appears

- **Think node:** All subdomain guidance is injected so the planner can see user preferences across all domains. Called at [think.py:190](src/alfred/graph/nodes/think.py#L190) via `format_all_subdomain_guidance()`.
- **Act node:** Only the current step's subdomain guidance is injected. Fetched at [act.py:1176-1182](src/alfred/graph/nodes/act.py#L1176-L1182) and passed to `build_act_user_prompt()` as sections 3 (write) or 7 (analyze/generate).

### Truncation

Each subdomain's guidance is capped at `MAX_GUIDANCE_CHARS = 800` (~200 tokens) to prevent prompt bloat. Defined at [injection.py:449](src/alfred/prompts/injection.py#L449).

### Data Source

The guidance dict is fetched via `domain.get_subdomain_guidance(user_id)` at [base.py:1109](src/alfred/domain/base.py#L1109), which returns `dict[str, str]` mapping subdomain name to narrative preference text. Kitchen fetches this from the user's profile record in the database.

---

## 7. Caching

Prompt templates are loaded from disk once and cached for the process lifetime.

### Caching Patterns by Node

| Node | Cache Variable | Populated | Invalidated |
|------|---------------|-----------|-------------|
| Think | `_SYSTEM_PROMPT` (module-level) | First call to `_get_system_prompt()` | Never (app restart) |
| Reply | `_REPLY_PROMPT`, `_SYSTEM_PROMPT` (module-level) | First call to `_get_prompts()` | Never |
| Router | `_SYSTEM_PROMPT` (module-level) | First call to `_get_system_prompt()` | Never |
| Act | `_PROMPT_CACHE` (dict) | Per-file on first `_load_prompt(filename)` | Never |
| Understand | None | Loaded fresh each call via `_load_prompt()` | N/A |
| Summarize | None | Inline strings, no loading | N/A |

### Why No Invalidation

Domain content is static for the lifetime of a domain registration. The `DomainConfig` object is created once at startup via `register_domain()`, and its prompt methods return the same content every time. Changing prompt content requires restarting the application.

### Act's Dict-Based Cache

Act uses a `_PROMPT_CACHE: dict[str, str]` at [act.py:324](src/alfred/graph/nodes/act.py#L324) because it loads multiple files (`base.md`, `crud.md`, `read.md`, etc.). The `_load_prompt(filename)` function at [act.py:327](src/alfred/graph/nodes/act.py#L327) checks the dict before reading from disk.

However, when the domain provides a full replacement via `get_act_prompt_content(step_type)`, the cache is bypassed entirely — the domain method is called on every `act_node()` invocation. Domain implementations should do their own caching if the content is expensive to produce.

---

## 8. Node-by-Node Prompt Structure

Summary table showing where each node's prompts come from:

| Node | System Prompt Source | User Prompt Source | Domain Methods Used |
|------|--------------------|--------------------|---------------------|
| **Router** | `router.md` + `{domain_router_content}` injection | Inline: user message + condensed conversation | `get_router_prompt_injection()` |
| **Understand** | Inline: "You are Alfred's MEMORY MANAGER..." (hardcoded) | `domain.get_understand_prompt_content()` or `understand.md` + request context | `get_understand_prompt_content()` |
| **Think** | `domain.get_think_prompt_content()` or `think.md` + `{domain_context}` + `{domain_planning_guide}` | 3 XML sections: `<session_context>`, `<conversation_history>`, `<immediate_task>` | `get_think_prompt_content()`, `get_think_domain_context()`, `get_think_planning_guide()`, `get_user_profile()`, `get_domain_snapshot()`, `get_subdomain_guidance()` |
| **Act** | `domain.get_act_prompt_content(step_type)` or `base.md` + `crud.md` + `{step_type}.md` + injection | 15-section assembly via `build_act_user_prompt()` | `get_act_prompt_content()`, `get_act_prompt_injection()`, `get_act_subdomain_header()`, `get_examples()`, `get_user_profile()`, `get_subdomain_guidance()` |
| **Act Quick** | `quick_header` + `crud.md` (inline in [injection.py:579-597](src/alfred/prompts/injection.py#L579-L597)) | Simplified 5-section assembly via `build_act_quick_prompt()` | `get_act_subdomain_header()`, `get_persona()` |
| **Reply** | `domain.get_system_prompt()` (identity) | `domain.get_reply_prompt_content()` or `reply.md` + `{domain_subdomain_guide}` + execution summary | `get_system_prompt()`, `get_reply_prompt_content()`, `get_reply_subdomain_guide()` |
| **Summarize** | Inline strings (4 different prompts for different tasks) | Inline: constructed from turn data | None |

### Kitchen Domain Prompt Files

The kitchen domain provides full-replacement content for most nodes:

| File | Lines | Consumed By |
|------|-------|-------------|
| [act_content.py](src/alfred_kitchen/domain/prompts/act_content.py) | 696 | `get_act_prompt_content(step_type)` → Act system prompt |
| [act_injections.py](src/alfred_kitchen/domain/prompts/act_injections.py) | 137 | `get_act_prompt_injection(step_type)` → fallback injection |
| [think_content.py](src/alfred_kitchen/domain/prompts/think_content.py) | 577 | `get_think_prompt_content()` → Think system prompt |
| [think_injections.py](src/alfred_kitchen/domain/prompts/think_injections.py) | 137 | `get_think_domain_context()`, `get_think_planning_guide()` → fallback injections |
| [reply_content.py](src/alfred_kitchen/domain/prompts/reply_content.py) | 299 | `get_reply_prompt_content()` → Reply instructions |
| [reply_guide.py](src/alfred_kitchen/domain/prompts/reply_guide.py) | 137 | `get_reply_subdomain_guide()` → fallback injection |
| [understand_content.py](src/alfred_kitchen/domain/prompts/understand_content.py) | 317 | `get_understand_prompt_content()` → Understand prompt body |
| [router_content.py](src/alfred_kitchen/domain/prompts/router_content.py) | 17 | `get_router_prompt_injection()` → Router injection |
| [system.md](src/alfred_kitchen/domain/prompts/system.md) | 32 | `get_system_prompt()` → Reply system prompt |
| [cook.md](src/alfred_kitchen/domain/prompts/cook.md) | 41 | Bypass mode: cook session system prompt |
| [brainstorm.md](src/alfred_kitchen/domain/prompts/brainstorm.md) | 53 | Bypass mode: brainstorm session system prompt |

**Total kitchen prompt content:** 2,443 lines.

---

## Key Files

| File | Lines | Role |
|------|-------|------|
| [src/alfred/prompts/injection.py](src/alfred/prompts/injection.py) | 672 | Act prompt assembly: `build_act_user_prompt()`, `build_act_quick_prompt()`, subdomain guidance |
| [src/alfred/graph/nodes/act.py](src/alfred/graph/nodes/act.py) | 1,913 | Act system prompt loading (`_get_system_prompt`), data gathering for user prompt |
| [src/alfred/graph/nodes/think.py](src/alfred/graph/nodes/think.py) | 310 | Think prompt loading and user prompt assembly |
| [src/alfred/graph/nodes/reply.py](src/alfred/graph/nodes/reply.py) | 1,224 | Reply prompt loading (system + instructions) |
| [src/alfred/graph/nodes/understand.py](src/alfred/graph/nodes/understand.py) | ~200 | Understand prompt loading with domain override |
| [src/alfred/graph/nodes/router.py](src/alfred/graph/nodes/router.py) | ~80 | Router prompt loading with injection |
| [src/alfred/domain/base.py](src/alfred/domain/base.py) | 1,135 | DomainConfig: 12 prompt-related abstract/default methods |
| [src/alfred/prompts/templates/](src/alfred/prompts/templates/) | 1,635 | Core template files (11 .md files) |
| [src/alfred_kitchen/domain/prompts/](src/alfred_kitchen/domain/prompts/) | 2,443 | Kitchen domain prompt content (8 .py + 3 .md files) |
