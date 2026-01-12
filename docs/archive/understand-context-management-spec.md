# Understand Context Management Spec

> **Purpose:** Define Understand's role as the surgical context manager for Alfred's multi-turn conversations.

---

## Core Insight

Understand's true value is **context curation**, not message rewriting.

| Old Role | New Role |
|----------|----------|
| `processed_message` (redundant) | ❌ Remove |
| Entity reference resolution | ✅ Keep |
| **Context curation (active/background)** | ✅ **Primary focus** |
| Quick mode detection | Debate later |

---

## 1. What "Active" Means (Unified Definition)

**Active entities** = entities injected into Think/Act prompts

### Sources of Active Entities

| Source | How It Works |
|--------|--------------|
| **Automatic (last 2 turns)** | Any entity referenced in turns N-1 and N-2 is automatically active |
| **Understand-curated** | Older entities Understand decides are still relevant |

### Data Structure (Fits Existing `SessionIdRegistry`)

```python
# Existing fields (keep)
ref_to_uuid: dict[str, str]      # recipe_1 → abc123-uuid
ref_labels: dict[str, str]       # recipe_1 → "Thai Curry"
ref_turn_last_ref: dict[str, int] # recipe_1 → 5 (last turn referenced)

# New field for Understand curation
ref_active_reason: dict[str, str] # gen_meal_plan_1 → "User's ongoing weekly plan"
```

### Active Calculation

```python
def get_active_entities(self, current_turn: int) -> list[str]:
    """Returns refs that should be in Think/Act context."""
    active = []
    for ref in self.ref_to_uuid.keys():
        last_ref = self.ref_turn_last_ref.get(ref, 0)
        # Automatic: last 2 turns
        if current_turn - last_ref <= 2:
            active.append(ref)
        # Understand-curated: has active_reason
        elif ref in self.ref_active_reason:
            active.append(ref)
    return active
```

---

## 2. Context Windows (Consistent Across Nodes)

| Node | Mandatory Context |
|------|-------------------|
| **Understand** | Last 4-5 turns (detailed) + previous Understand notes |
| **Think** | Last 2-3 turns (complete) + active entities |
| **Act** | Last 2-3 turns (complete) + current turn steps + active entities |

**Key:** Think and Act see the **same historical window** so plans are executable.

---

## 3. Data Structure: Works WITH Existing Systems

**Not a parallel system** — extends existing structures:

```
SessionIdRegistry (existing, extended)
├── ref_to_uuid           # recipe_1 → uuid (existing)
├── ref_labels            # recipe_1 → "Thai Curry" (existing)
├── ref_turn_last_ref     # recipe_1 → 5 (existing - automatic recency)
└── ref_active_reason     # NEW: gen_meal_plan_1 → "User's ongoing plan"
                          # ↑ Understand's influence on active state

conversation (existing, extended)
└── understand_decision_log   # NEW: History for future Understand
    └── [{turn: 3, ref: "...", reason: "..."}, ...]
```

**Two pieces:**
- `ref_active_reason` in registry = **current state** (is this entity Understand-retained?)
- `understand_decision_log` in conversation = **decision history** (so next Understand sees prior reasoning)

---

## 4. Understand ↔ Understand Continuity

Each Understand pass reads **previous decision log** to maintain continuity:

```
Turn 3 Understand:
  - Reads: Decision log (empty)
  - Outputs: "gen_meal_plan_1 retained: User building weekly plan"
  - Updates: ref_active_reason["gen_meal_plan_1"] = "User building weekly plan"

Turn 5 Understand:
  - Reads: Decision log from turns 3-4
  - Sees: "gen_meal_plan_1 retained: User building weekly plan"
  - Decision: Keep it active (user still working on this)
```

---

## 5. What Each Node Sees

### Understand Sees (Most Context)

```
## Current Message
{user_message}

## Recent Conversation (Last 4-5 turns, detailed with entity annotations)
Turn 1: User asked X, Alfred did Y
  - Entities: recipe_1 (read), recipe_2 (read)
Turn 2: User asked Z, Alfred generated W  
  - Entities: gen_meal_plan_1 (generated)
Turn 3: ...
Turn 4: ...
Turn 5 (current): {user_message}

## Previous Understand Decisions
- Turn 3: Retained gen_meal_plan_1 — "User building weekly plan"
- Turn 4: Retained recipe_3 — "Part of meal plan"

## All Known Entities
(Full SessionIdRegistry view - everything tracked this session)
```

### Think Sees (Delineated Recent + Long Term)

```
## Task
User: "{user_message}"
Today: 2026-01-09 | Mode: PLAN

---

## Recent Context (Last 2 turns)

**Turn 4:** User asked about pantry
Alfred: Listed 15 inventory items

**Turn 5 (current):** "{user_message}"

**Active from recent:**
- inv_1: Eggs (read, turn 4)
- inv_2: Milk (read, turn 4)

---

## Long Term Memory

**Retained from earlier turns:**
- gen_meal_plan_1: Weekly Meal Plan (generated, turn 2)
- recipe_3: Thai Curry (saved, turn 1)

---

## Profile / Dashboard
(As today)
```

**Note:** Think sees the delineation (recent vs long term) but NOT the "why" from Understand.

### Act Sees (Same Delineation)

```
## Step 2: Save meal plan to database

## This Turn's Steps
Step 1: Read user preferences → done
Step 2: (current)

---

## Recent Context (Last 2 turns)
(Same as Think)

**Active from recent:**
- inv_1: Eggs (read, turn 4)
- inv_2: Milk (read, turn 4)

---

## Long Term Memory
- gen_meal_plan_1: Weekly Meal Plan (generated, turn 2)
- recipe_3: Thai Curry (saved, turn 1)

---

## Schema
(Subdomain-specific)
```

---

## 6. Understand Output Model (Updated)

### Remove

- `processed_message` — redundant, Think has raw message

### Keep

- `entity_mentions` — reference resolution
- `referenced_entities` — simple refs mentioned this turn
- `needs_disambiguation` — when ambiguous
- `quick_mode` (debate later)

### Add/Modify

```python
class EntityCuration(BaseModel):
    """Understand's context curation decisions."""
    # Which older entities to keep active (beyond automatic 2-turn window)
    retain_active: list[RetentionDecision] = []
    # Which entities to demote (remove from active, keep in registry)
    demote: list[str] = []
    # Which entities to drop entirely (user said "forget" etc.)
    drop: list[str] = []
    # Fresh start
    clear_all: bool = False

class RetentionDecision(BaseModel):
    """Why an older entity should stay active."""
    ref: str                    # e.g., "gen_meal_plan_1"
    reason: str                 # e.g., "User's ongoing weekly plan"
    # turn is set by system, not LLM
```

---

## 7. Understand Prompt Structure (Revised)

### Identity: Lead with Value, Not Restrictions

**Bad (defensive):**
> "You are a context curator, not message rewriter"

**Good (value-first):**
> "You are Alfred's **memory manager**. In multi-turn conversations, you ensure the system remembers what matters and forgets what doesn't.
>
> Without you, Alfred forgets important context after 2 turns. With you, Alfred can handle complex requests that span many turns — like building a meal plan over a week of conversations, or refining a recipe through multiple iterations.
>
> Your decisions directly impact whether Alfred can follow through on user goals."

### Sections

1. **You Are** — Memory manager, enables multi-turn intelligence
2. **Your Value** — What breaks without you (context loss), what works with you (long-term continuity)
3. **What You Receive**
   - Current message
   - Recent conversation (last 4-5 turns with entity annotations)
   - Previous Understand decisions (from earlier turns)
   - All known entities
4. **Your Job**
   - Resolve references ("that recipe" → `recipe_1`)
   - Curate context (what stays active beyond automatic 2-turn window)
   - Explain retention decisions (for future Understand agents)
5. **Output Contract** — Updated model (no `processed_message`)
6. **Examples** — Show good curation decisions across multi-turn scenarios

### Key Input: Annotated Conversation History

Show Understand HOW entities were used each turn:

```
## Turn 3 (2 turns ago)
User: "add cod to the first recipe"
Alfred: Updated recipe_1 with cod

Entities this turn:
- recipe_1: updated (referenced in user message)
- gen_meal_plan_1: (exists, not mentioned)

---

## Turn 4 (1 turn ago)  
User: "what's in my pantry?"
Alfred: Listed 15 items

Entities this turn:
- inv_1...inv_15: read (new)
- recipe_1: (not mentioned)
- gen_meal_plan_1: (not mentioned) ← 2 turns without mention, at risk!

---

## Turn 5 (current)
User: "save that meal plan"

Your job: Recognize gen_meal_plan_1 is relevant despite not being mentioned in turns 3-4.
```

This helps Understand see the conversation flow and make informed retention decisions.

---

## 8. Implementation Checklist

### Phase 1: Data Structure (SessionIdRegistry) ✅
- [x] Add `ref_active_reason: dict[str, str]` — stores Understand's retention reason
- [x] Add `get_active_entities(current_turn)` method — returns (recent, retained) tuple
- [x] Add `set_active_reason()` and `clear_active_reason()` helper methods
- [x] Add `understand_decision_log` to conversation storage — history for future Understand

### Phase 2: Understand Output Model ✅
- [x] Remove `processed_message` — redundant with raw message
- [x] Add `RetentionDecision` model with ref + reason
- [x] Update `EntityCurationDecision` model:
  - [x] `retain_active: list[RetentionDecision]` with reasons
  - [x] Renamed `demote_to_background` → `demote`
  - [x] Renamed `drop_entities` → `drop`
  - [x] Added `curation_summary` for decision log
- [x] Keep: `entity_mentions`, `referenced_entities`, `needs_disambiguation`

### Phase 3: Understand Prompt Rewrite ✅
- [x] Lead with value-first identity ("Memory Manager")
- [x] Show annotated conversation history (last 4-5 turns with entities per turn)
- [x] Show previous Understand decisions (decision log table)
- [x] Remove all `processed_message` guidance
- [x] Add 6 examples: clear ref, ambiguous, retention, demotion, fresh start, rejection

### Phase 4: Think/Act Prompt Updates ✅
- [x] Delineate "Recent Context" vs "Long Term Memory" sections
- [x] Use `get_active_entities()` for entity injection
- [x] Ensure both see same 2-turn window
- [x] Don't expose "why" to Think/Act (retention reason only shown to Understand)

### Phase 5: Testing
- [ ] Multi-turn recipe iteration (entity retained across topic switch)
- [ ] Topic switch and return (meal plan → pantry → meal plan)
- [ ] "Forget that" / "start fresh" commands
- [ ] 5+ turn conversation with long-term goal

---

## 9. Future Enhancements

### Think Sees "Why" (Optional)

If helpful for planning:
```
## Active Entities
- gen_meal_plan_1: Weekly Meal Plan — *User's ongoing goal (turn 2)*
```

### Automatic Decay

Understand notes older than N turns could auto-expire unless refreshed.

### Confidence Scores

Understand could output confidence on retention decisions, helping prioritize if context gets too large.

---

## Implemented Enhancements (V5)

### 1. Lazy Registration with Name Enrichment ✅

**Implementation:** 
- `_lazy_enrich_queue` tracks refs needing enrichment
- `_enrich_lazy_registrations()` batch queries target tables
- `_add_enriched_labels()` post-processes results with `_*_label` fields
- Generic across all FK types (recipes, ingredients, tasks)

**Files:** `id_registry.py`, `crud.py`

### 2. Meal Plan Display Formatting ✅

**Implementation:**
- Custom `"format": "meal_plan"` protocol
- `_format_meal_plan_record()` produces: `date [slot] → recipe_name (ref) id:meal_X`
- Entity labels use `_compute_entity_label()` for "Jan 12 [lunch]" format

**Files:** `injection.py`, `id_registry.py`

### 3. Linked Entity Display Consistency ✅

**Implementation:**
- Linked entities (action: `linked`) filtered from active entity lists
- Shown inline with parent records only
- `_compute_entity_label()` handles type-specific labels
- Consistent format: `ref: Label (type) [action]`

**Files:** `id_registry.py`, `injection.py`

### 4. Cross-Domain Query Optimization

**Decision:** Keep Think planning multi-step (clearer, more predictable).

No implementation needed — current behavior is intentional.

---

*Created: 2026-01-09*
*Updated: 2026-01-10 - Marked enhancements as implemented*