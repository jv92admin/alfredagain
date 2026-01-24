# PR: Unified Context API for Generated Entities

## Summary

This PR unifies how generated entities (`gen_recipe_1`) flow through the pipeline, ensuring Think, Act, and Reply all have consistent access to the same data. Previously, generated content was treated as an anomaly with 10+ special handling locations. Now it flows through the same API as regular entities.

**Key insight:** The "what" (which entities exist, what data is available) should be common across all nodes. Only the "how much detail" (formatting) varies by node.

---

## Problem Statement

### The Symptom

When a user asked "Show me that shakshuka recipe you made earlier" (Turn 4 of `read_rerouting` scenario), Alfred responded:

> "I looked for the full details of the Simple Shakshuka recipe you mentioned, but I don't have the instructions or technique explanations available right now..."

But Turns 5 and 6 (modify and save) worked correctly, proving the data existed.

### Root Cause Analysis

The debugging journey revealed **two context visibility issues**:

**Issue 1: Reply didn't see generated content**

| Node | Saw pending_artifacts? | What it was told |
|------|------------------------|------------------|
| Think | ✅ Yes | "Act has full data for Generated Content" |
| Act | ✅ Yes | Full JSON injected for write/generate/analyze steps |
| Reply | ❌ **No** | Only saw refs + labels, not content |

**Issue 2: Act didn't get JSON for analyze steps**

The injection code (`injection.py`) only added `## 5. Generated Data` for `write` steps, even though `act.py` built the section for write/generate/analyze. This caused Act to say "No data to analyze" during analyze steps.

When Think saw `gen_recipe_1` in "Generated Content", it correctly planned an `analyze` step (per the guidance "no read needed"). Act received the analyze step and had the data. But Act's analyze output was reasoning text, not structured data. Reply then tried to format a response but **couldn't see the actual recipe content**.

### The Fragmented State (Before)

Generated entities were handled in 10+ special locations:

```
Act generate → pending_artifacts (separate storage)
    ├── act.py:1254-1272    → special "Generated Data" injection
    ├── crud.py:575-662     → special read rerouting
    ├── builders.py:254-285 → special "Generated Content" section
    ├── act.py:1708-1716    → special artifact modification
    ├── entity.py:82-93     → special tier extraction
    └── summarize.py:209-217 → special cleanup
```

Meanwhile, regular entities flowed through a unified path:
```
DB → CRUD → translate_output → SessionIdRegistry → builders.py → all nodes
```

---

## Solution: Unified Data Access

### Phase 1: Add Unified Methods to SessionIdRegistry

**File:** `src/alfred/core/id_registry.py`

Added two methods that serve as the single source of truth:

```python
def get_entity_data(self, ref: str) -> dict | None:
    """
    Unified entity data access - the SINGLE source of truth.

    Works identically for gen_* and regular refs.
    Returns full content if available in registry, None otherwise.
    """
    return self.pending_artifacts.get(ref)

def update_entity_data(self, ref: str, content: dict) -> bool:
    """
    Update content of an existing entity in the registry.

    Used when Act modifies a gen_* artifact.
    """
    if ref in self.pending_artifacts:
        self.pending_artifacts[ref] = content
        # Update label if changed
        new_label = content.get("name") or content.get("title")
        if new_label:
            self.ref_labels[ref] = new_label
        return True
    return False
```

### Phase 2: Refactor CRUD Read Rerouting

**File:** `src/alfred/tools/crud.py`

Simplified `_try_reroute_pending_read()` to use the unified method:

```python
def _try_reroute_pending_read(params: dict, registry: Any) -> list[dict] | None:
    """Check if db_read references entities with registry data."""
    refs = _extract_refs_from_filters(params.get("filters", []))
    if not refs:
        return None

    results = []
    for ref in refs:
        # UNIFIED: Use single method for all refs
        data = registry.get_entity_data(ref)
        if data is not None:
            result = data.copy()
            result["id"] = ref
            results.append(result)
        else:
            return None  # Any ref without registry data = go to DB

    return results if results else None
```

**Key change:** Removed `ref.startswith("gen_")` check. The unified method handles this internally.

### Phase 3: Refactor Act Artifact Modification

**File:** `src/alfred/graph/nodes/act.py`

Replaced direct `pending_artifacts` mutation with unified method:

```python
# BEFORE (direct mutation)
if key.startswith("gen_") and key in session_registry.pending_artifacts:
    session_registry.pending_artifacts[key] = new_content

# AFTER (unified method)
if session_registry.update_entity_data(key, new_content):
    modified_refs.append(key)
```

### Phase 4: Refactor Entity Tier Logic

**File:** `src/alfred/context/entity.py`

Replaced `get_generated_pending()` with unified check:

```python
# BEFORE
generated_refs = registry.get_generated_pending()
for ref in recent_refs:
    if ref not in generated_refs:
        ctx.active.append(snapshot)

# AFTER - unified data check
for ref in recent_refs:
    has_registry_data = registry.get_entity_data(ref) is not None
    is_generated = registry.ref_actions.get(ref) == "generated"

    if has_registry_data and is_generated:
        ctx.generated.append(snapshot)
    else:
        ctx.active.append(snapshot)
```

### Phase 5: Align ThinkContext Builder

**File:** `src/alfred/context/builders.py`

Updated ThinkContext to use the same logic as entity.py for consistency:

```python
# V9 UNIFIED: Identify generated entities using same logic as entity.py
generated_refs = [
    ref for ref in pending_artifacts
    if ref_actions.get(ref) == "generated"
]
```

### Phase 6: The Critical Fix — Give Reply Access

**File:** `src/alfred/context/builders.py`

This was the missing piece. Reply needed the same view as Think and Act:

```python
@dataclass
class ReplyContext:
    entity: EntityContext
    conversation: ConversationHistory
    reasoning: ReasoningTrace
    execution_outcome: str
    pending_artifacts: dict  # V9: Full content of generated artifacts

    def format(self) -> str:
        sections = []

        # ... existing sections ...

        # V9 UNIFIED: Include generated content so Reply can display it
        if self.pending_artifacts:
            gen_lines = ["## Generated Content (Full Data)"]
            gen_lines.append("Use this to show users the actual content.")
            for ref, content in self.pending_artifacts.items():
                label = content.get("name") or content.get("title") or ref
                gen_lines.append(f"### {ref}: {label}")
                gen_lines.append(json.dumps(content, indent=2))
            sections.append("\n".join(gen_lines))

        return "\n\n".join(sections)
```

And in `build_reply_context()`:

```python
def build_reply_context(state: "AlfredState") -> ReplyContext:
    # ... existing code ...

    # V9 UNIFIED: Get pending_artifacts so Reply has same view as Think/Act
    pending_artifacts = {}
    if isinstance(registry, SessionIdRegistry):
        pending_artifacts = registry.get_all_pending_artifacts()
    elif isinstance(registry, dict):
        pending_artifacts = registry.get("pending_artifacts", {})

    return ReplyContext(
        entity=get_entity_context(registry, current_turn, mode="reply"),
        conversation=get_conversation_history(conversation),
        reasoning=get_reasoning_trace(conversation),
        execution_outcome=outcome,
        pending_artifacts=pending_artifacts,  # NEW
    )
```

### Phase 7: Fix Artifact Injection for All Step Types

**File:** `src/alfred/prompts/injection.py`

The injection code only added `## 5. Generated Data` for `write` steps, but act.py was building the section for write/generate/analyze. This caused Act to say "No data to analyze" even though the data existed.

```python
# BEFORE (broken)
if step_type == "write" and artifacts_section:

# AFTER (fixed)
if step_type in ("write", "generate", "analyze") and artifacts_section:
```

### Phase 8: Clarify Think Prompt Guidance

**File:** `prompts/think.md`

Added explicit guidance for "show me" requests:

```markdown
**EXCEPTION — "Show me the recipe" for gen_* refs:**
When user wants to **SEE the full content** of a generated artifact,
use `read` — NOT analyze. The read will be rerouted to return the
artifact from memory, which puts the full content in step_results
for Reply to display.

| User Request | `gen_*` in Generated Content | Action |
|--------------|------------------------------|--------|
| "analyze/compare/check" | ✅ `analyze` | Act reasons internally |
| "show me / display / what's in it" | ✅ `read` | Data flows to Reply |
| "modify / improve / add X" | ✅ `generate` | Act updates artifact |
```

### Phase 9: Multi-Entity Operations Guidance

**File:** `prompts/think.md`

Added guidance for operations requiring multiple data sources:

```markdown
**CRITICAL — Multi-entity operations (compare, match, diff):**
If your `analyze` step requires data from **multiple sources** (e.g., "compare recipe with inventory"),
verify **ALL** sources are in context:

| Operation | Sources Needed | Check |
|-----------|----------------|-------|
| "What ingredients am I missing?" | Recipe + Inventory | Both in context? |
| "Compare this recipe with that one" | Recipe A + Recipe B | Both available? |

**If ANY source is missing → read it first.**
```

This prevents bugs where Think plans an `analyze` step assuming all data is available, but one source (like inventory) was only read in an earlier turn.

---

## The Debugging Journey

### Stage 1: Initial Hypothesis — Read Rerouting Bug

Initially suspected the CRUD read rerouting wasn't working. Added debug logging:

```python
print(f"[DEBUG CRUD] execute_crud called: tool={tool}")
print(f"[DEBUG CRUD] get_entity_data({ref}) returned: {data is not None}")
```

**Finding:** No `db_read` calls during Turn 4. The rerouting code was never invoked.

### Stage 2: Realization — Think Planned `analyze`, Not `read`

The debug output showed:
- Turn 2: `db_create` (inventory)
- Turn 3: `db_delete` (inventory)
- Turn 4: **No db_read** — jumped straight to Turn 6's `db_create`

Think saw `gen_recipe_1` in "Generated Content" and correctly followed the guidance:
> "Act has full data — no read needed"

So Think planned `analyze` instead of `read`.

### Stage 3: Question — Why Did This Matter?

If Think planned `analyze` and Act had the data, why didn't it work?

**Answer:** Act's analyze step produced reasoning text, not structured data. The analyze output went to `step_results`, but Reply couldn't show the recipe because:

1. The recipe content wasn't in `step_results` (just Act's analysis)
2. Reply didn't have access to `pending_artifacts`

### Stage 4: The Unified View Problem

The user asked the key question:

> "Why is Think receiving different context labeling to Act?"

This led to examining what each node actually sees:

- **Think:** ThinkContext with "Generated Content" section (pending_artifacts keys + labels)
- **Act:** Full JSON injection for write/generate/analyze steps (from `get_all_pending_artifacts()`)
- **Reply:** EntityContext (refs + labels only) — **NO access to actual content!**

### Stage 5: The Real Fix

Instead of making Think plan `read` for "show me" requests (a workaround), the proper fix was:

**Give Reply the same unified view as Think and Act.**

Now all nodes can see generated content, and the system works regardless of whether Think plans `read` or `analyze`.

---

## Testing

### Scenario Tests

```bash
$ python tests/scenario_runner.py read_rerouting --user 00000000-0000-0000-0000-000000000002

--- Turn 4: Read gen_recipe_1 ---
User: Show me that shakshuka recipe you made earlier
Alfred: Got it! Here's the full Simple Shakshuka recipe I generated earlier...
# ✅ Now shows the full recipe content

Scenario complete: PASSED
```

```bash
$ python tests/scenario_runner.py gen_artifact_flow --user 00000000-0000-0000-0000-000000000002

--- Turn 1: Generate ---
--- Turn 2: Modify ---
--- Turn 3: Save ---
Scenario complete: PASSED
```

### Unit Tests

Existing unit tests pass. Two pre-existing failures are unrelated (outdated test expectations for node names).

---

## Files Changed

| File | Change | Risk |
|------|--------|------|
| `src/alfred/core/id_registry.py` | Added `get_entity_data()`, `update_entity_data()` | Low - additive |
| `src/alfred/tools/crud.py` | Simplified `_try_reroute_pending_read()` | Medium - behavior |
| `src/alfred/graph/nodes/act.py` | Use `update_entity_data()` for modifications | Low - same behavior |
| `src/alfred/context/entity.py` | Use `get_entity_data()` for tier logic | Low - same behavior |
| `src/alfred/context/builders.py` | Added `pending_artifacts` to ReplyContext | Medium - new data |
| `src/alfred/prompts/injection.py` | Inject artifacts for write/generate/analyze (was write-only) | **High - critical fix** |
| `prompts/think.md` | "show me" guidance + multi-entity operations | Low - documentation |

---

## Architecture After

```
                    ┌─────────────────────────────────────┐
                    │       SessionIdRegistry             │
                    │  (Single Source of Truth)           │
                    │                                     │
                    │  • get_entity_data(ref) → dict|None │
                    │  • update_entity_data(ref, content) │
                    │  • pending_artifacts: dict          │
                    └──────────────┬──────────────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │    Think    │         │     Act     │         │    Reply    │
    │             │         │             │         │             │
    │ Generated   │         │ Generated   │         │ Generated   │
    │ Content     │         │ Data (JSON) │         │ Content     │
    │ section     │         │ section     │         │ (Full Data) │
    └─────────────┘         └─────────────┘         └─────────────┘
           │                       │                       │
           │                       │                       │
           └───────────────────────┴───────────────────────┘
                                   │
                         All nodes see the same
                         generated entity data
```

---

## Key Learnings

1. **Context visibility must be consistent.** If one node is told "the data is available", all downstream nodes that need it must also have access.

2. **Follow the data, not the symptoms.** The initial hypothesis (read rerouting bug) was wrong. The real issue was Reply not having access to the data.

3. **Unified APIs prevent drift.** Having `get_entity_data()` as a single source of truth means new features automatically work for both generated and regular entities.

4. **The prompt is a contract.** When Think's prompt says "Act has full data", that creates an expectation. If Reply then says "I don't have the data", the contract is broken.

---

## Rollback Plan

If issues arise, revert these commits in order:
1. ReplyContext changes (builders.py) — most impactful
2. Think prompt changes — documentation only
3. Entity tier logic changes — low risk
4. CRUD rerouting changes — functionally equivalent

The `get_entity_data()` and `update_entity_data()` methods can remain as they're additive and don't change existing behavior.
