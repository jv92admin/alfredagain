# Context API Specification

**Date:** 2026-01-13  
**Purpose:** Define 3-layer context model as "APIs" nodes consume

---

## The Three Context Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT API                                   │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: ENTITY CONTEXT                                        │
│  "What things exist and their status"                           │
│  Owner: SessionIdRegistry + Understand                          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: CONVERSATION HISTORY                                  │
│  "What user and assistant said"                                 │
│  Owner: Summarize                                               │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: REASONING TRACE                                       │
│  "What LLMs decided and discovered"                             │
│  Owner: Summarize (aggregates from all nodes)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Entity Context

**Source of Truth:** `SessionIdRegistry`  
**Managed by:** Understand (curation), Act (registration)

### Data Model
```python
class EntityContext:
    # Active entities (last 2 turns or explicitly retained)
    active: list[EntitySnapshot]
    
    # Generated but not saved (ephemeral)
    generated: list[EntitySnapshot]
    
    # Long-term memory (older but retained by Understand)
    retained: list[EntitySnapshot]
    
class EntitySnapshot:
    ref: str              # "recipe_1"
    type: str             # "recipes"
    label: str            # "Lemon Herb Chicken"
    status: str           # "read" | "created" | "updated" | "deleted" | "generated" | "linked"
    turn_created: int
    turn_last_ref: int
    retention_reason: str | None  # Why Understand kept it
```

### API Endpoints (Functions)

```python
def get_entity_context(registry: SessionIdRegistry, current_turn: int) -> EntityContext:
    """Build entity context from registry state."""
    
def format_entity_context(ctx: EntityContext, mode: str) -> str:
    """Format for injection into prompts.

    mode: 'full' (Act) | 'refs_and_labels' (Think) | 'reply' (Reply)
          | 'do_not_read' (Think alt) | 'curation' (Understand)
    """
```

### Who Consumes What

| Node | Active | Generated | Retained | Notes |
|------|--------|-----------|----------|-------|
| Understand | ✅ Full | ✅ Full | ✅ Full | For curation decisions |
| Think | ✅ Refs+Labels | ✅ Refs+Labels | ✅ Refs only | To avoid re-reads |
| Act | ✅ Full data | ✅ Full data | ❌ | Current work context |
| Reply | ✅ Labels only | ✅ Labels only | ❌ | For natural language |

---

## Layer 2: Conversation History

**Source of Truth:** `ConversationContext`  
**Managed by:** Summarize

### Data Model
```python
class ConversationHistory:
    # Recent exchanges (full detail, last 2 turns)
    recent_turns: list[ConversationTurn]
    
    # Compressed older history
    history_summary: str
    
    # Overall engagement theme
    engagement_summary: str
    
    # Pending state (awaiting user response)
    pending: PendingState | None

class ConversationTurn:
    user: str
    assistant_summary: str  # Condensed response
    routing: dict | None    # What router decided
    timestamp: str

class PendingState:
    type: str        # "propose" | "clarify" | "ask_user"
    context: str     # What was proposed/asked
    questions: list  # Specific questions if any
```

### API Endpoints

```python
def get_conversation_history(conversation: dict) -> ConversationHistory:
    """Build conversation history from stored state."""

def format_conversation_for_prompt(history: ConversationHistory, depth: int) -> str:
    """Format for injection.
    
    depth: 2 (recent only) | 5 (with summary) | 'full' (everything)
    """
```

### Who Consumes What

| Node | Recent (2) | Summary | Engagement | Pending |
|------|------------|---------|------------|---------|
| Understand | ✅ | ✅ | ✅ | ✅ |
| Think | ✅ | ✅ | ✅ | ✅ (critical!) |
| Act | ✅ | ❌ | ❌ | ❌ |
| Reply | ✅ | ❌ | ✅ | ✅ |

---

## Layer 3: Reasoning Trace

**Source of Truth:** `TurnExecutionSummary` (NEW - built by Summarize)  
**Contributors:** Think, Act, Understand, Analyze steps

### Data Model
```python
class ReasoningTrace:
    # Last 2 turns of execution summaries
    recent_summaries: list[TurnExecutionSummary]
    
    # Compressed older reasoning
    reasoning_summary: str

class TurnExecutionSummary:
    turn_num: int
    
    # What Think decided
    think_decision: str           # "plan_direct" | "propose" | "clarify"
    think_goal: str              # "Find vegetarian recipes"
    
    # What steps executed
    steps: list[StepSummary]
    
    # Understand's curation this turn
    entity_curation: CurationSummary
    
    # Conversation flow metadata
    conversation_phase: str      # "exploring" | "narrowing" | "confirming"
    user_expressed: str          # "wants variety" | "prefers quick meals"

    # Blocked state (set when turn was blocked before completion)
    blocked_reason: str | None   # "CRUD failed: ... | db_create on inventory: sugar, onions"
    
class StepSummary:
    step_num: int
    type: str                    # "read" | "analyze" | "generate" | "write"
    subdomain: str
    description: str             # From plan
    outcome: str                 # LLM's result_summary if available, else generic count
    entities_involved: list[str] # Refs touched
    note: str | None             # Act's note_for_next_step
    
class CurationSummary:
    retained: list[str]          # Refs explicitly kept
    demoted: list[str]           # Refs no longer active
    reasons: dict[str, str]      # ref -> reason
```

### API Endpoints

```python
def get_reasoning_trace(conversation: dict, current_state: dict) -> ReasoningTrace:
    """Build reasoning trace from stored summaries + current turn."""

def format_reasoning_for_prompt(trace: ReasoningTrace, node: str) -> str:
    """Format for injection.
    
    node: 'think' | 'act' | 'reply'
    Different nodes need different detail levels.
    """
```

### Who Consumes What

| Node | Last Turn Steps | Curation | Conversation Phase | Notes |
|------|-----------------|----------|-------------------|-------|
| Understand | ❌ | ✅ (own history) | ❌ | Focuses on entities |
| Think | ✅ Full | ✅ Summary | ✅ | Avoid re-planning |
| Act | ✅ Current turn | ❌ | ❌ | Within-turn context |
| Reply | ✅ Outcomes only | ❌ | ✅ | For continuity |

---

## Combined: Node Context Requirements

### Understand Node

```
┌─────────────────────────────────────────┐
│ UNDERSTAND CONTEXT                      │
├─────────────────────────────────────────┤
│ ENTITY: Full (all 3 tiers)              │
│ CONVERSATION: Full history + pending    │
│ REASONING: Own decision history only    │
└─────────────────────────────────────────┘
```

**Purpose:** Decide what entities to retain/demote based on user intent.

### Think Node

```
┌─────────────────────────────────────────┐
│ THINK CONTEXT                           │
├─────────────────────────────────────────┤
│ ENTITY: Refs + Labels (no full data)    │
│ CONVERSATION: Recent + summary + pending│
│ REASONING: Last turn summary + curation │
│                                         │
│ CRITICAL ADDITIONS:                     │
│ - "DO NOT re-read: recipe_1, recipe_2"  │
│ - "Last turn: read 5 recipes, analyzed" │
│ - "User expressed: wants quick meals"   │
└─────────────────────────────────────────┘
```

**Purpose:** Plan next steps while knowing what already happened.

### Act Node

```
┌─────────────────────────────────────────┐
│ ACT CONTEXT                             │
├─────────────────────────────────────────┤
│ ENTITY: Full data (active + generated)  │
│ CONVERSATION: Recent turns only         │
│ REASONING: Current turn steps + notes   │
│                                         │
│ CRITICAL ADDITIONS:                     │
│ - Full step results from current turn   │
│ - prev_step_note                        │
│ - content_archive for retrieval         │
└─────────────────────────────────────────┘
```

**Purpose:** Execute with full data access.

### Reply Node

```
┌─────────────────────────────────────────┐
│ REPLY CONTEXT                           │
├─────────────────────────────────────────┤
│ ENTITY: Labels only (for natural lang)  │
│ CONVERSATION: Recent + engagement       │
│ REASONING: Step outcomes + phase        │
│                                         │
│ CRITICAL ADDITIONS:                     │
│ - Conversation phase                    │
│ - "User expressed: ..."                 │
│ - What was just accomplished            │
└─────────────────────────────────────────┘
```

**Purpose:** Respond naturally with continuity.

---

## Implementation: Context Builder Functions

**File:** `src/alfred/context/builders.py`

```python
"""
Context API - Unified context building for all nodes.

Each node calls the appropriate builder to get its context.
Builders read from state/conversation and format appropriately.
"""

def build_understand_context(state: AlfredState) -> dict:
    """Full context for Understand's curation decisions."""
    return {
        "entity": get_entity_context(state["id_registry"], state["current_turn"]),
        "conversation": get_conversation_history(state["conversation"]),
        "reasoning": get_own_decision_history(state["conversation"]),
    }

def build_think_context(state: AlfredState) -> dict:
    """Context for Think's planning decisions."""
    return {
        "entity": get_entity_context(state["id_registry"], state["current_turn"], 
                                     mode="refs_and_labels"),
        "conversation": get_conversation_history(state["conversation"]),
        "reasoning": get_reasoning_trace(state["conversation"]),
        "curation": get_current_curation(state),  # From this turn's Understand
    }

def build_act_context(state: AlfredState) -> dict:
    """Context for Act's execution."""
    return {
        "entity": get_entity_context(state["id_registry"], state["current_turn"],
                                     mode="full_data"),
        "conversation": get_recent_conversation(state["conversation"], depth=2),
        "reasoning": get_current_turn_steps(state),
    }

def build_reply_context(state: AlfredState) -> dict:
    """Context for Reply's response generation."""
    return {
        "entity": get_entity_context(state["id_registry"], state["current_turn"],
                                     mode="labels_only"),
        "conversation": get_conversation_with_engagement(state["conversation"]),
        "reasoning": get_execution_outcomes(state),
    }
```

---

## Prompt Injection Pattern

Each node's prompt follows this structure:

```markdown
## Entity Context
{format_entity_context(ctx.entity, mode)}

## Conversation History  
{format_conversation(ctx.conversation)}

## What Happened (Reasoning Trace)
{format_reasoning(ctx.reasoning)}

---
## Your Task
{node-specific instructions}
```

The `format_*` functions handle the detail level per node.

---

## Storage Schema Update

```python
class ConversationContext(TypedDict):
    # LAYER 2: Conversation History
    recent_turns: list[dict]
    history_summary: str
    engagement_summary: str
    pending_clarification: dict | None
    
    # LAYER 1: Entity Context (via id_registry)
    id_registry: dict
    
    # LAYER 3: Reasoning Trace (NEW)
    turn_summaries: list[dict]     # Last 2 TurnExecutionSummary
    reasoning_summary: str         # Compressed older reasoning
    
    # Legacy (keep for now)
    content_archive: dict
    understand_decision_log: list
    step_summaries: list
```

---

## Migration Path

1. **Phase 1:** Create `build_*_context()` functions ✅
2. **Phase 2:** Update Summarize to build `TurnExecutionSummary` ✅
3. **Phase 3:** Update Understand to use `build_understand_context()` ✅
4. **Phase 4:** Update Think to use `build_think_context()` ✅
5. **Phase 5:** Update Act to use `build_act_entity_context()` ✅ (follows naming convention, lives in act.py)
6. **Phase 6:** Update Reply to use `build_reply_context()` ✅

### Current Implementation Status (Complete)

| Node | Context Builder | Location |
|------|-----------------|----------|
| **Understand** | `build_understand_context()` | builders.py ✅ |
| **Think** | `build_think_context()` | builders.py ✅ |
| **Act** | `build_act_entity_context()` | act.py ✅ |
| **Reply** | `build_reply_context()` | builders.py ✅ |

**Naming Convention:** All builders follow `build_{node}_context()` pattern. Act's builder lives in act.py because it requires SessionIdRegistry methods and complex step_results parsing for full-data injection.

---

*This is the "endpoint" model - each node knows exactly what context it needs, and the API provides it consistently.*
