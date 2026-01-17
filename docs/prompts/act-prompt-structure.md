# Act Prompt Structure

**Purpose:** Documents the Act node's prompt assembly — common sections, step-type-specific sections, entity context, and output contract.

**Related:** `src/alfred/prompts/injection.py`, `src/alfred/graph/nodes/act.py`, `prompts/act/*.md`

---

## Architecture Overview

```
act.py                              injection.py
┌────────────────────────┐         ┌─────────────────────────────────┐
│ Gather context:        │         │ build_act_user_prompt()         │
│ ├─ entity_context      │────────▶│   │                             │
│ ├─ conversation        │         │   ├─ _build_common_sections()   │
│ ├─ step_results        │         │   │   ├─ status                 │
│ ├─ schema (if CRUD)    │         │   │   ├─ task                   │
│ ├─ profile (if gen)    │         │   │   ├─ data_section           │
│ └─ prev_turn_context   │         │   │   ├─ entities  ◀── ALWAYS   │
│                        │         │   │   ├─ conversation ◀── ALWAYS│
│ Call builder ──────────│         │   │   └─ decision               │
└────────────────────────┘         │   │                             │
                                   │   └─ _build_step_type_sections()│
                                   │       ├─ subdomain_header       │
                                   │       ├─ guidance               │
                                   │       ├─ schema (read/write)    │
                                   │       └─ artifacts (write)      │
                                   └─────────────────────────────────┘
```

**Key Guarantee:** Entity context and conversation are NEVER omitted — they're in `_build_common_sections()` which is called for ALL step types.

---

## Section Matrix: What's Included Per Step Type

| Section | ANALYZE | GENERATE | READ | WRITE | Common? |
|---------|:-------:|:--------:|:----:|:-----:|---------|
| Subdomain header | ✅ | ✅ | ✅ | ✅ | ✅ COMMON |
| STATUS table | ✅ | ✅ | ✅ | ✅ | ✅ COMMON |
| User profile | ✅ | ✅ | ❌ | ❌ | ⚠️ analyze/generate only |
| Subdomain guidance | ✅ | ✅ | ❌ | ✅ | ⚠️ varies |
| Task section | ✅ | ✅ | ✅ | ✅ | ✅ COMMON |
| Step-type guidance | ✅ | ✅ | ✅ | ✅ | ✅ COMMON (different content) |
| Data/Step history | ✅ | ✅ | ✅ | ✅ | ✅ COMMON (different label) |
| Schema | ❌ | ❌ | ✅ | ✅ | ⚠️ read/write only |
| **Entities in Context** | ✅ | ✅ | ✅ | ✅ | ✅ **ALWAYS** |
| Generated artifacts | ❌ | ❌ | ❌ | ✅ | ⚠️ write only |
| **Conversation context** | ✅ | ✅ | ✅ | ✅ | ✅ **ALWAYS** |
| DECISION | ✅ | ✅ | ✅ | ✅ | ✅ COMMON (different options) |

---

## Prompt Assembly Order

The user prompt is assembled in this order:

```
1. Subdomain header      ← from get_full_subdomain_content()
2. Subdomain guidance    ← user preferences (write only here, or after profile for analyze/generate)
3. STATUS table          ← step #, goal, type, progress, today
4. Previous step note    ← note from prior step (read/write only)
5. User profile          ← constraints, equipment (analyze/generate only)
6. Subdomain guidance    ← user preferences (analyze/generate only)
7. Task section          ← "Your job this step: ..."
8. Batch manifest        ← batch progress (write only)
9. Step-type guidance    ← from get_contextual_examples()
10. Data section         ← prev_turn + prev_steps + current_step
11. Schema               ← database schema (read/write only)
12. Entities in Context  ← ◀── ALWAYS INCLUDED
13. Artifacts            ← generated content (write only)
14. Conversation         ← ◀── ALWAYS INCLUDED
15. DECISION             ← output instructions
```

---

## System Prompt Structure

Act receives a **system prompt** assembled from files in `prompts/act/`:

```
┌─────────────────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT = base.md + [crud.md] + {step_type}.md                │
│ ─────────────────────────────────────────────────────────────────── │
│   base.md     — Always included (core principles, actions)          │
│   crud.md     — For read/write steps (common: tools, operators)     │
│   read.md     — Read-specific (advanced patterns, semantic search)  │
│   write.md    — Write-specific (update/delete examples, linked)     │
│   analyze.md  — Analyze-specific mechanics                          │
│   generate.md — Generate-specific mechanics                         │
└─────────────────────────────────────────────────────────────────────┘
```

**Note:** Act does NOT use `system.md` (Alfred's personality). Act is an execution layer, not user-facing. Only **Reply** uses `system.md`.

**CRUD file split (V7.1):**
- `crud.md` — Common only: tools table, filter syntax, operators, schema reminder
- `read.md` — All read patterns: semantic search, OR logic, date ranges, array contains, column selection
- `write.md` — Update/delete examples (ID-based), subdomain-specific patterns in personas

**Built by:** `_get_system_prompt(step_type)` in `act.py`

---

## Data Sources

| Section | Source Function/Object |
|---------|------------------------|
| **entity_context** | `_build_enhanced_entity_context()` in `act.py` |
| **conversation_context** | `format_full_context()` from `memory/conversation.py` |
| **prev_turn_context** | `_format_previous_turn_steps()` in `act.py` |
| **prev_step_results** | `_format_step_results()` in `act.py` |
| **current_step_results** | `_format_current_step_results()` in `act.py` |
| **schema** | `get_schema_with_fallback(subdomain)` |
| **profile_section** | `format_profile_for_prompt()` from `profile_builder.py` |
| **subdomain_guidance** | `profile.subdomain_guidance[subdomain]` |
| **subdomain_header** | `get_full_subdomain_content()` from `personas.py` — includes CRUD guidance |
| **step-type guidance** | `get_contextual_examples()` from `examples.py` |

**Subdomain Personas (V7.1):** Each subdomain in `personas.py` has step-type-specific guidance:
- `read`: Query patterns, what columns to include (e.g., "with instructions", "with ingredients")
- `write`: CRUD patterns, field references, linked table operations
- `analyze`/`generate`: Domain-specific reasoning guidance

---

## Turn Windows

| Data Type | Window | Notes |
|-----------|--------|-------|
| **Step results (current)** | Current turn only | Steps 0 to current_step_index - 1 |
| **Entity data (full)** | Last 2 turns + current | ✅ From `turn_step_results` + current `step_results` |
| **Entity refs (recent)** | Last 2 turns | Refs + labels (if no data available) |
| **Long-term memory** | >2 turns | Refs only — need db_read for data |
| **Conversation** | Last 2-3 exchanges | Recent context |
| **Previous turn summary** | Last turn | Last 2 steps only |

---

## Output Contract

Act returns `ActDecision`:

```python
class ActDecision(BaseModel):
    action: Literal["tool_call", "step_complete", "ask_user", "blocked", "fail", ...]
    
    # For tool_call
    tool: str | None           # db_read, db_create, db_update, db_delete
    params: dict | None        # Tool parameters
    
    # For step_complete
    result_summary: str | None # What was accomplished
    data: dict | None          # Step output (for analyze/generate)
    note_for_next_step: str | None  # Context for later steps
    
    # For ask_user
    question: str | None
    
    # For blocked
    reason_code: str | None    # INSUFFICIENT_INFO, PLAN_INVALID, TOOL_FAILURE
    details: str | None
    suggested_next: str | None # ask_user, replan, fail
```

**Valid actions by step type:**

| Step Type | tool_call | step_complete | ask_user | blocked |
|-----------|:---------:|:-------------:|:--------:|:-------:|
| read | ✅ | ✅ | ✅ | ✅ |
| write | ✅ | ✅ | ✅ | ✅ |
| analyze | ❌ | ✅ | ✅ | ✅ |
| generate | ❌ | ✅ | ✅ | ✅ |

---

## Implementation Details

### Main Entry Point

```python
# src/alfred/prompts/injection.py

def build_act_user_prompt(
    # Step info
    step_type: str,              # read, write, analyze, generate
    step_index: int,
    total_steps: int,
    step_description: str,
    subdomain: str,
    user_message: str,
    # Context data (ALWAYS passed)
    entity_context: str,         # ◀── ALWAYS included in output
    conversation_context: str,   # ◀── ALWAYS included in output
    prev_turn_context: str,
    prev_step_results: str,
    current_step_results: str,
    # Step-type specific (passed only when needed)
    schema: str | None = None,              # read/write only
    profile_section: str | None = None,     # analyze/generate only
    subdomain_guidance: str | None = None,
    batch_manifest_section: str | None = None,
    artifacts_section: str | None = None,
    archive_section: str | None = None,
    prev_step_note: str | None = None,
    # Metadata
    tool_calls_made: int = 0,
    prev_subdomain: str | None = None,
) -> str:
```

### Internal Functions

| Function | Purpose |
|----------|---------|
| `_build_common_sections()` | Build sections for ALL step types: status, task, data_section, entities, conversation, decision |
| `_build_step_type_sections()` | Build step-type-specific: subdomain_header, guidance, schema, batch_manifest, artifacts, prev_note |
| `_build_decision_section()` | Build decision prompt (different options per step type) |

---

## Entity Data Architecture ✅ IMPLEMENTED

### Active Entities: Full Data Available

Act now sees **full data** for entities from the last 2 turns + current turn:

```markdown
## Active Entities (Context Snapshot)
Data from recent turns. **For read steps, always call db_read — this is reference, not a substitute.**

### `recipe_3`: Malaysian Sambal (recipe)
  cuisine: malaysian | time: 45min | servings: 4
  occasions: weeknight, spicy | health: high-protein
  **ingredients (8 items):**
    - `ri_1`: 1 lb cod
    - `ri_2`: 8 oz noodles
    - `ri_3`: 2 tbsp sambal
    ...
  **instructions (6 steps):**
    1. Prep noodles and vegetables...
    2. Marinate cod with sambal...
    ...
```

**Key features:**
- Full instruction text shown (enables Act to modify for WRITE steps)
- Ingredient refs (`ri_X`) shown inline when full ingredient data is available
- Snapshot warning reminds Act to always call `db_read` for read steps

**Implementation:**
1. `summarize.py`: Persists `step_results` → `conversation["turn_step_results"][turn_num]`
2. `summarize.py`: Prunes to last 2 turns only
3. `act.py`: `_build_enhanced_entity_context()` merges current + prior turn data
4. Deduplication: latest version wins (newer turn overwrites older)

### Long-Term Memory: Refs Only

Entities >2 turns old show refs only (data pruned):

```markdown
## Long Term Memory (refs only)
**Older entities retained by Understand — need db_read for data.**
- `recipe_1`: Butter Chicken (recipe)
```

**Design principle:** Understand can "retain" an old ref, but cannot inject data. Only `db_read` can bring data into context.

---

## Files to Update Together

When changing Act's prompt structure:

| File | What to change |
|------|----------------|
| `src/alfred/prompts/injection.py` | `build_act_user_prompt()` and helpers |
| `src/alfred/graph/nodes/act.py` | Context gathering, system prompt |
| `prompts/act/*.md` | System prompt templates |
| `src/alfred/core/id_registry.py` | `translate_read_output()` (nested ingredient IDs) |
| `src/alfred/graph/nodes/summarize.py` | Persist `turn_step_results` |

---

## Key Design Decisions

1. **Entity context ALWAYS included** — Common section, never omitted regardless of step type
2. **Conversation ALWAYS included** — Common section, never omitted
3. **Refs only for long-term** — Entities >2 turns old show refs + labels only
4. **Schema for CRUD only** — Analyze/generate don't need DB schema
5. **Profile for generation only** — Read steps don't need user preferences
6. **Full instructions shown** — Write steps need actual text to modify

---

## Act Quick

Act Quick bypasses Think for simple single-table reads. It uses the same prompt builder:

```python
# In act_quick_node():
user_prompt = build_act_user_prompt(
    step_type="read",
    ...  # Same parameters as regular Act
)
```

**Criteria (set by Understand):**
1. Single table (no joins)
2. Read only (no writes)
3. Data lookup (answer is IN the database)

**V7.1:** Knowledge questions (substitutions, techniques) route to Think, not Act Quick.

---

*Last updated: 2026-01-16*
