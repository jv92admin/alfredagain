# Alfred V3 Decision Architecture

This document maps every decision point in the Alfred pipeline, what information each needs, and how decisions cascade downstream.

---

## Overview

```
User Message
     │
     ▼
┌────────────┐
│ Understand │──────────────────────────────────────────────────────┐
└─────┬──────┘                                                      │
      │                                                             │
      ├── quick_mode=true ──▶ ┌───────────┐ ──▶ ┌───────┐ ──▶ ┌─────▼─────┐
      │                       │ Act Quick │     │ Reply │     │ Summarize │
      │                       └───────────┘     └───────┘     │  (async)  │
      │                                                       └───────────┘
      │
      └── quick_mode=false ──▶ ┌───────┐ ──▶ ┌─────┐ ──▶ ┌───────┐ ──▶ ┌───────────┐
                               │ Think │     │ Act │     │ Reply │     │ Summarize │
                               └───────┘     └─────┘     └───────┘     │  (async)  │
                                                                       └───────────┘
```

**Note:** Router is currently skipped (single-agent). Summarize runs async after Reply.

---

## Decision Point Reference

### 1. Router

| Aspect | Details |
|--------|---------|
| **File** | `src/alfred/graph/nodes/router.py`, `prompts/router.md` |
| **Decisions** | `agent`, `goal`, `complexity` |
| **Inputs** | user_message, system.md (static) |
| **Outputs** | `RouterOutput(agent, goal, complexity)` |
| **Downstream Impact** | Think receives goal; Act uses complexity for model selection |

**What Router Must Know:**
- Which agent handles this domain (pantry, coach, cellar)
- How complex is this request (affects model choice, planning depth)

---

### 2. Understand

| Aspect | Details |
|--------|---------|
| **File** | `src/alfred/graph/nodes/understand.py`, `prompts/understand.md` |
| **Decisions** | Entity state changes, clarification needs, reference resolution, **quick mode detection** |
| **Inputs** | user_message, active_entities, pending_entities, recent_turns |
| **Outputs** | `UnderstandOutput(entity_updates, referenced_entities, needs_clarification, processed_message, quick_mode, quick_intent, quick_subdomain)` |
| **Downstream Impact** | EntityRegistry updates; Think skipped if clarification needed OR quick_mode=true |

**What Understand Must Know:**
- What entities exist (active vs pending)
- Recent conversation context (to resolve "that recipe" → specific ID)
- Whether this is an answer to a prior clarification (don't re-clarify)
- **Whether this is a simple single-step query (quick mode detection)**

**Quick Mode Detection:**
Understand sets `quick_mode: true` for simple queries targeting one subdomain:

| Subdomain | Read | Write | Reason |
|-----------|------|-------|--------|
| inventory | ✅ | ✅ | Simple table |
| shopping | ✅ | ✅ | Simple table |
| tasks | ✅ | ✅ | Optional FKs |
| recipes | ✅ | ❌ | Linked tables |
| meal_plans | ✅ | ❌ | FK refs, date logic |
| preferences | ✅ | ✅ | Profile updates |

---

### 3. Think

| Aspect | Details |
|--------|---------|
| **File** | `src/alfred/graph/nodes/think.py`, `prompts/think.md` |
| **Decisions** | `decision` (plan_direct/propose/clarify), `steps[]` with step_type/subdomain/group |
| **Inputs** | router_output.goal, mode_context, profile, dashboard, active_entities, conversation |
| **Outputs** | `ThinkOutput(decision, goal, steps[], proposal_message, clarification_questions)` |
| **Downstream Impact** | Act branches on step_type; Reply formats based on decision |

**What Think Must Know:**
- User's goal (from Router)
- User's preferences (profile) - to avoid re-asking
- Current data state (dashboard) - to know what exists
- Mode (quick/plan/create) - affects planning depth

**Critical Understanding:**
Think assigns `step_type` which determines how Act executes:

| Step Type | What It Means | Act Behavior |
|-----------|---------------|--------------|
| `read` | Fetch data from DB | Calls `db_read`, returns records |
| `write` | Persist EXISTING content | Calls `db_create/update/delete` |
| `analyze` | Reason over prior step data | NO db calls, returns analysis |
| `generate` | Create NEW content | NO db calls, returns generated content |

**Key Distinction:**
- `generate` = LLM creates content that doesn't exist yet
- `write` = Persist content that already exists (from generate step, archive, or user)

**Never use `write` to CREATE content.** That's `generate`'s job.

---

### 4. Act (Branching)

| Aspect | Details |
|--------|---------|
| **File** | `src/alfred/graph/nodes/act.py`, `prompts/act/*.md` |
| **Branch Variable** | `step_type` (from ThinkStep, line 713) |
| **Decisions** | tool_call vs step_complete, which tool, what params |
| **Inputs** | Varies by branch (see below) |
| **Outputs** | `step_data`, `turn_entities`, `content_archive` updates |
| **Downstream Impact** | Reply receives step_results; Summarize receives turn_entities |

**Branch-Specific Inputs:**

| Input | read | write | analyze | generate |
|-------|------|-------|---------|----------|
| `subdomain_schema` | YES | YES | NO | NO |
| `profile_section` | NO | NO | YES | YES |
| `archive_section` | YES | YES | YES | YES |
| `prev_step_section` | YES | YES | YES | YES |
| `turn_entities_section` | YES | YES | YES | YES |
| `contextual_examples` | YES | YES | YES | YES |
| `conversation_section` | YES | YES | YES | YES |

**Prompt Files Loaded:**
- All branches: `prompts/act/base.md`
- Branch-specific: `prompts/act/{step_type}.md`

---

### 4b. Act Quick (Quick Mode Only)

| Aspect | Details |
|--------|---------|
| **File** | `src/alfred/graph/nodes/act.py` (`act_quick_node`) |
| **When** | `quick_mode=true` from Understand |
| **Decisions** | Which tool to call, what params |
| **Inputs** | `quick_intent`, `quick_subdomain`, subdomain schema |
| **Outputs** | `step_results` with single tool result |
| **Downstream Impact** | Reply formats the response |

**What Act Quick Must Know:**
- Plaintext intent (e.g., "Show user's shopping list")
- Target subdomain (for schema injection)
- No prior step results (single-step execution)

**Key Difference from Full Act:**
- No step_complete loop
- No think_output.steps iteration
- Single LLM call → single tool call → done

---

### 5. Reply

| Aspect | Details |
|--------|---------|
| **File** | `src/alfred/graph/nodes/reply.py`, `prompts/reply.md` |
| **Decisions** | Presentation format, what to show, what to summarize |
| **Inputs** | step_results, think_output.decision, conversation |
| **Outputs** | `final_response` (natural language to user) |
| **Downstream Impact** | Summarize compresses this; User sees it |

**What Reply Must Know:**
- What was accomplished (step_results)
- What was the intent (think_output.decision - execute vs propose vs clarify)
- Whether content was generated vs saved (different presentation)

**Key Rules:**
- If `generate` step produced content → show full content, offer to save
- If `write` step saved content → confirm what was saved
- If proposal → present the proposal, don't claim completion

---

### 6. Summarize

| Aspect | Details |
|--------|---------|
| **File** | `src/alfred/graph/nodes/summarize.py`, `prompts/summarize.md` |
| **Decisions** | What to compress, which entities to track, garbage collection |
| **Inputs** | final_response, turn_entities, think_output.decision, conversation |
| **Outputs** | Updated `conversation`, updated `entity_registry` |
| **Downstream Impact** | Next turn's context for all nodes |

**What Summarize Must Know:**
- Was this a proposal or execution? (determines summary text)
- Which entities were created/modified? (for tracking)
- Which entities are stale? (for garbage collection)

**Critical Safeguards:**
1. If Think decided `propose` or `clarify`, skip LLM summarization → use deterministic text
2. Only promote entities from `db_read` or `db_write` sources to `active_entities`
3. PENDING entities from generate/analyze are NOT promoted (ghost entity prevention)

---

## Information Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           STATE (per turn)                              │
├─────────────────────────────────────────────────────────────────────────┤
│ user_message        │ From user input                                  │
│ router_output       │ Router → Think, Act                              │
│ understand_output   │ Understand → EntityRegistry                       │
│ think_output        │ Think → Act, Reply, Summarize                    │
│ step_results        │ Act → Reply, Summarize                           │
│ turn_entities       │ Act → Summarize → EntityRegistry                 │
│ content_archive     │ Act → Act (cross-turn), persisted                │
│ conversation        │ Summarize → Think, Act, Understand               │
│ entity_registry     │ Summarize → Understand, Think                    │
│ mode_context        │ CLI/UI → Think, Act                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Step Type Taxonomy

### read
- **Purpose**: Fetch data from database
- **DB Calls**: YES (`db_read`)
- **Prompt Includes**: Schema, prev results, archive
- **Output**: Actual DB records in `step_data`

### write  
- **Purpose**: Persist EXISTING content to database
- **DB Calls**: YES (`db_create`, `db_update`, `db_delete`)
- **Prompt Includes**: Schema, prev results, archive
- **Output**: Created/updated records in `step_data`
- **Important**: Content must already exist (from generate step, archive, or user input)

### analyze
- **Purpose**: Reason over data from previous steps
- **DB Calls**: NO
- **Prompt Includes**: Profile, prev results, archive
- **Output**: Analysis/decision in `step_complete.data`
- **Use When**: Comparing lists, filtering by criteria, making decisions

### generate
- **Purpose**: Create NEW content (recipes, plans, suggestions)
- **DB Calls**: NO
- **Prompt Includes**: Profile, prev results, archive
- **Output**: Generated content in `step_complete.data`
- **Use When**: User asks for ideas, suggestions, plans, recipes
- **Follow-up**: Usually followed by `write` step if user wants to save

---

## Common Patterns

### Pattern 1: Generate then Save
```
User: "Create a recipe for chicken pasta"
Think: [
  {step_type: "generate", description: "Create chicken pasta recipe"},
  {step_type: "write", description: "Save the recipe with ingredients"}
]
```

### Pattern 2: Read then Analyze
```
User: "Which shopping items do I already have?"
Think: [
  {step_type: "read", subdomain: "shopping", group: 0},
  {step_type: "read", subdomain: "inventory", group: 0},
  {step_type: "analyze", description: "Find items in both lists", group: 1}
]
```

### Pattern 3: Direct Write (content from user)
```
User: "Add eggs to my shopping list"
Think: [
  {step_type: "write", description: "Add eggs to shopping list"}
]
```

---

## Validation Checklist

When debugging, verify each node receives what it needs:

- [ ] **Router**: Gets user_message
- [ ] **Understand**: Gets active_entities from conversation (same source as Think)
- [ ] **Think**: Gets profile, dashboard, router_output.goal, mode_context
- [ ] **Act/read**: Gets schema, prev_step_section, archive_section
- [ ] **Act/write**: Gets schema, prev_step_section, archive_section
- [ ] **Act/analyze**: Gets profile, prev_step_section, archive_section
- [ ] **Act/generate**: Gets profile, prev_step_section, archive_section
- [ ] **Reply**: Gets step_results with actual data, think_output.decision
- [ ] **Summarize**: Gets turn_entities, think_output.decision

---

## Version History

- **V3.1 (current)**: Quick Mode (bypass Think for simple queries), async Summarize, Router skip
- **V3 (Jan 2026)**: Step types (read/write/analyze/generate), group-based parallelization, entity lifecycle
- **V2 (legacy)**: CRUD-only steps, no generate/analyze distinction

