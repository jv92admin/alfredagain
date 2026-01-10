# Mode Configurations Spec

> **Goal:** Not every request needs 5 LLM calls. "What can I substitute for cottage cheese?" should be fast.

---

## The Problem

Current flow for ANY request:
```
User → Understand → Think → Act (loop) → Reply
       (1 call)    (1 call)  (2+ calls)  (1 call)
```

**5+ LLM calls for "what's a substitute for X?"** — ridiculous.

---

## The Solution: Mode-Specific Configurations

| Mode | Flow | Use Case |
|------|------|----------|
| **Plan** | Understand → Think → Act → Reply | Complex multi-step (meal planning, recipe creation) |
| **Quick** | UnderThink → Act → Reply | Simple queries (substitutes, "what do I have?") |
| **Cook** | UnderThink → Generate → Reply | Tips, suggestions, no CRUD |

---

## UnderThink: Combined Understand + Think

For simple modes, merge into one prompt:

```
UnderThink does:
1. Entity reference resolution (if needed)
2. Light context (recent turns only)
3. Single intent → single step
```

**Saves:** One LLM call + token duplication

**Loses:** Long-term memory curation (acceptable for quick tasks)

---

## Mode Constraints

| Mode | Allowed | Not Allowed (bounce to Plan) |
|------|---------|------------------------------|
| **Quick** | Read, simple generate | Multi-step, complex CRUD |
| **Cook** | Generate tips/suggestions | Any CRUD (save/delete/update) |
| **Plan** | Everything | — |

**Bounce example:**
- User in Cook mode: "Save this recipe"
- System: "Switch to Plan mode to save this"

---

## Token Savings

| Component | Plan Mode | Quick/Cook Mode |
|-----------|-----------|-----------------|
| Schema | Full subdomain | Minimal/none |
| Entity context | Full + long-term | Recent (last 2 turns) |
| LLM calls | 5+ | 2-3 |

---

## Implementation Notes

### Quick Mode Flow
```python
if mode == "quick":
    # Combined UnderThink call
    result = await underthink(message, recent_context_only=True)
    
    if result.needs_plan_mode:
        return bounce_to_plan_mode(result.reason)
    
    # Simplified single-step Act
    output = await act_simple(result.intent, result.entities)
    return reply(output)
```

### When to Bounce
- Multi-step detected ("do X then Y")
- Complex entity references (needs long-term memory)
- CRUD in non-CRUD mode

---

## Open Questions

1. **User-controlled vs auto-detect?** 
   - Current: User selects mode
   - Alternative: Auto-detect from message complexity?

2. **UnderThink prompt structure?**
   - How much context to include?
   - How to prevent it from over-planning?

3. **Act simplification?**
   - Skip step loops entirely?
   - Single tool call, single response?

---

## Not Over-Engineering

**Start simple:**
1. Quick mode = UnderThink + simplified Act
2. If it works, add Cook mode
3. If it works, consider auto-detection

**Don't build:**
- Complex mode-switching logic
- Auto-detection before validating manual modes work
- Multiple UnderThink variants

---

*Created: 2026-01-09*
