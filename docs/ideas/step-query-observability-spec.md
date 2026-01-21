# Step Query Observability Spec

## Problem

When Act executes a `db_read` with filters, downstream components (Reply, Think on next turn) only see:
```
Step 1: read inventory
Outcome: No records found
```

They DON'T see what filters were actually applied:
```
Query: location='pantry'  ← MISSING
```

This causes:
- Reply can't explain WHY nothing was found
- Think can't reason about what was actually queried
- Debugging is harder (have to dig through logs)

## Solution

Store executed query params alongside step results. Since we control tool execution, this is deterministic - no LLM ambiguity.

## Current Flow

```
Act LLM → decides tool_call(params) 
       → _execute_tool_call(tool, params)
       → result stored in current_step_tool_results
       → step_complete → step_results[idx] = data
```

Step results format today:
```python
step_results[0] = [("db_read", "inventory", [...])]  # (tool, table, data)
```

## Proposed Flow

Store params with each tool result:

```python
step_results[0] = [
    {
        "tool": "db_read",
        "table": "inventory", 
        "params": {"filters": [{"field": "location", "op": "=", "value": "pantry"}], "limit": 100},
        "data": [...],
        "count": 0
    }
]
```

## Implementation

### 1. act.py - Store params with results

In `_execute_tool_call` or where results are cached:

```python
# Before (tuple format):
tool_result = (tool, table, data)

# After (dict format):
tool_result = {
    "tool": tool,
    "table": params.get("table"),
    "params": params,  # Full params including filters
    "data": data,
    "count": len(data) if isinstance(data, list) else 1
}
```

**Location:** Around line 1429 in `act.py` where tool results are appended to `current_step_tool_results`.

### 2. reply.py - Format params in step summary

In `_format_execution_summary`:

```python
def _format_query_params(params: dict) -> str:
    """Format query params for human readability."""
    parts = []
    
    # Table
    if "table" in params:
        parts.append(f"Table: {params['table']}")
    
    # Filters
    filters = params.get("filters", [])
    if filters:
        filter_strs = []
        for f in filters:
            filter_strs.append(f"{f['field']} {f['op']} {f['value']}")
        parts.append(f"Filters: {', '.join(filter_strs)}")
    else:
        parts.append("Filters: none (all records)")
    
    # Limit
    if "limit" in params:
        parts.append(f"Limit: {params['limit']}")
    
    return " | ".join(parts)
```

Then in step formatting:
```python
### Step 1: Read inventory
Query: Table: inventory | Filters: location = 'pantry' | Limit: 100
Outcome: 0 records found
```

### 3. Think injection - Show in turn summaries

When building turn summaries for Think, include query context:

```
**Turn 1:** 
- Decision: plan_direct
- Steps executed:
  - read inventory (filters: location='pantry'): 0 records  ← ADD FILTER INFO
```

**Location:** `injection.py` in conversation/turn summary formatting.

## Backwards Compatibility

The step_results format change (tuple → dict) needs to be handled:

```python
# In reply.py and anywhere step_results are consumed:
def _extract_from_result(result):
    """Handle both old tuple and new dict format."""
    if isinstance(result, dict):
        return result["tool"], result["table"], result["data"], result.get("params")
    elif isinstance(result, tuple):
        # Legacy format: (tool, table, data)
        return result[0], result[1], result[2], None
```

## Files to Modify

| File | Change |
|------|--------|
| `src/alfred/graph/nodes/act.py` | Store params with tool results (~5 lines) |
| `src/alfred/graph/nodes/reply.py` | Format params in step summary (~20 lines) |
| `src/alfred/prompts/injection.py` | Include filters in turn summaries (~10 lines) |

## Testing

1. Run a query that filters: "what's in my fridge?"
2. Check Reply output shows the filter
3. Run follow-up, check Think's turn summary shows filter
4. Run query with no filters, verify "Filters: none" appears

## Example Output

**Before:**
```
### Step 1: Read inventory
Outcome: No records found
```

**After:**
```
### Step 1: Read inventory
Query: Table: inventory | Filters: location = 'pantry' | Limit: 100
Outcome: 0 records found

💡 Tip: This searched only 'pantry' location. Ask "show all my inventory" for everything.
```

## Future Enhancement

Reply could use query context to provide smarter suggestions:
- Empty result + narrow filter → suggest broader search
- Unexpected results + filter mismatch → explain what happened
