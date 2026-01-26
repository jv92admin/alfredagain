# Streaming Architecture Enhancements

> Ideas for future improvements to Alfred's streaming UX.
> Prerequisites: Phase A (active context events) and Phase B (inline progress) are complete.

---

## 1. Error Display in Tool Calls

**Effort:** Small | **Value:** Polish

### Current State
- Tool errors occur but aren't surfaced to user
- `tool_error` event type is defined in plan but not implemented

### Proposed
When a CRUD operation fails:
```
Step 2: Update inventory ●
  update(inventory) → ⚠️ Failed: Item not found
```

### Implementation
1. Backend: Emit `tool_error` from act.py catch blocks
2. Frontend: Handle in `updatePhaseState`, render with error styling
3. Consider: Should errors block the step or allow retry?

---

## 2. Reply Streaming (Typewriter Effect)

**Effort:** Medium | **Value:** UX Delight

### Current State
- Reply node generates full response, emits as single `done` event
- User sees nothing → full response (jarring for long responses)

### Proposed
Stream reply text as it generates:
```
[Full response appears]
  ↓
Based on your inventory, I found 3 re|  ← cursor blinks as text streams
```

### Implementation
1. Backend: Use LLM streaming in reply.py, emit `streaming_text` chunks
2. Frontend: New `StreamingText` component with typewriter render
3. Consideration: Need to buffer/debounce for smooth animation

### Trade-offs
- Adds complexity to reply node
- LangGraph streaming mode may need adjustment
- Worth it for long responses, overkill for short ones

---

## 3. Phase Collapse/Expand

**Effort:** Medium | **Value:** Cleaner UI

### Current State
- All phases show expanded during streaming
- After completion, entire progress block disappears
- Final message shows collapsed `ActiveContextDisplay`

### Proposed
Collapsible phase sections:
```
▼ Understanding... ✓
    [AI Context: 2 entities]

▶ Planning... ✓                    ← collapsed, click to expand

▼ Step 1: Read inventory ✓         ← auto-expands current step
    read(inventory) → 12 items
    [AI Context: +12 items]
```

### Behavior
- Phases auto-collapse when complete
- Current phase always expanded
- User can manually expand/collapse
- Optional: "Expand All" / "Collapse All" toggle

### Implementation
1. Add `expanded` state per phase in `PhaseState`
2. Auto-collapse logic in `updatePhaseState`
3. Click handlers on phase headers

---

## 4. Persistent Context Bar

**Effort:** Medium | **Value:** Always-Visible Context

### Current State
- Context only visible inline during streaming
- Final context in message bubble (collapsed by default)
- No persistent "what does AI know?" indicator

### Proposed
Always-visible context panel:
```
┌─────────────────────────────────────────────┐
│ 🧠 AI Context (Turn 5)                      │
│ recipe_1: Butter Chicken [read]             │
│ inv_1: Chicken breast [read]                │
│ gen_recipe_1: New Pasta Recipe [proposed]   │
│                              [Pin] [Clear]  │
└─────────────────────────────────────────────┘
```

### Features
- Shows current active entities
- Updates in real-time as events arrive
- Pin/unpin to control retention
- Clear generated content

### Implementation
1. Lift `activeContext` state to App level
2. New `ContextBar` component (sidebar or header)
3. Wire to same `active_context` events
4. Add pin/unpin API to SessionIdRegistry

### Considerations
- Mobile: Where does it go? Drawer?
- Information density: Too much? Collapsed by default?
- Relationship to inline display: Replace or complement?

---

## Priority Recommendation

| Order | Enhancement | Reason |
|-------|-------------|--------|
| 1 | Error display | Small effort, improves reliability perception |
| 2 | Phase collapse | Makes streaming cleaner, builds on existing code |
| 3 | Reply streaming | Nice-to-have, most value for long responses |
| 4 | Persistent context bar | Larger UX decision, needs design thinking |

---

## Related Specs

- [Streaming Architecture Plan](../../CLAUDE.plans/fluffy-mixing-sun.md) - Original phases A/B/C
- [Capabilities](../architecture/capabilities.md) - User-facing feature list
