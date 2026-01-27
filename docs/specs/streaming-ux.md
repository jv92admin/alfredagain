# Streaming UX Enhancements

> Progressive visibility into AI execution with collapsible reasoning.

**Status:** Implemented (Jan 2026)

---

## Summary

Three improvements to Alfred's streaming experience during chat:

1. **Entity Display Summarization** - Bulk entities (inventory, shopping, ingredients) are summarized when >5 items
2. **Progressive Plan Reveal** - Steps appear one-by-one as they execute, not all at once
3. **Collapsible Reasoning** - Reasoning trace preserved in message bubble, collapsed by default

---

## Implementation

### 1. Entity Display Summarization

**File:** `frontend/src/components/Chat/ActiveContextDisplay.tsx`

Groups entities by type and summarizes bulk collections:

| Entity Type | Threshold | Display When Over |
|-------------|-----------|-------------------|
| inventory / inv | 5 | `📦 Inventory (N items) → VIEW` |
| shopping_list / shop | 5 | `🛒 Shopping List (N items) → VIEW` |
| ingredients / ing | 5 | `🧂 Ingredients (N items) → VIEW` |
| recipes, meal_plans, tasks | ∞ | Always individual chips |

"VIEW" link navigates to the relevant page.

### 2. Progressive Plan Reveal

**File:** `frontend/src/components/Chat/StreamingProgress.tsx`

- `plan` event: Stores goal and step count, but does NOT populate steps[]
- `step` event: Creates step entry from event data (description comes from backend)
- Steps appear one-by-one as each `step` event fires
- CSS transitions for smooth appearance

**Backend fix:** `src/alfred/graph/workflow.py` - Preserved `think_output` from think node (was being overwritten to `None` by act node).

### 3. Collapsible Reasoning

**Files:**
- `frontend/src/components/Chat/MessageBubble.tsx` - Added `reasoning?: PhaseState` to Message interface, CollapsibleReasoning component
- `frontend/src/components/Chat/ChatView.tsx` - Preserves phaseState in assistant message on done event

Display: `▶ Show reasoning (N steps completed)` - expands to full StreamingProgress trace.

---

## Bug Fixes

- **Sparse array handling:** Added `.filter(Boolean)` guards in StreamingProgress and CollapsibleReasoning to handle out-of-order events or stale data
- **Step descriptions not showing:** Fixed backend bug where `think_output` was overwritten to `None` when processing act node output

---

## Files Modified

| File | Changes |
|------|---------|
| `frontend/src/components/Chat/ActiveContextDisplay.tsx` | SummaryChip, grouping logic, TYPE_ROUTES |
| `frontend/src/components/Chat/StreamingProgress.tsx` | Export PhaseState, progressive step reveal, sparse array guard |
| `frontend/src/components/Chat/MessageBubble.tsx` | Message.reasoning field, CollapsibleReasoning component |
| `frontend/src/components/Chat/ChatView.tsx` | Preserve phaseState in message |
| `src/alfred/graph/workflow.py` | Don't overwrite think_output in act node handler |
