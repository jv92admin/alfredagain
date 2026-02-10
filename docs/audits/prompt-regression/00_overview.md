# Prompt Regression Audit: Pre-Refactor vs Post-Refactor

**Pre-refactor session:** `prompt_logs_downloaded/20260203_014946` (Feb 3, 2026 — before domain abstraction)
**Post-refactor session:** `prompt_logs/20260207_235146` (Feb 7, 2026 — after Phase 3.5d)

**Goal:** Verify zero behavioral change in prompts sent to the LLM after the domain abstraction refactoring.

**Verdict:** BROKEN. The genericization replaced domain-specific examples with useless placeholders ("Item A", "show my items") that teach the LLM nothing about the actual domain. The core should only contain a minimal orchestration shell + Pydantic-enforced output contract. Domain-specific examples, guidance, and entity context belong in the domain layer and should be injected at runtime.

## Node-by-Node Status

| Node | File | Verdict | Severity |
|------|------|---------|----------|
| Understand | [01_understand.md](01_understand.md) | BROKEN — ~20 kitchen→generic replacements, all examples gutted | HIGH |
| Think | [02_think.md](02_think.md) | BROKEN — worst affected. Half kitchen/half generic = inconsistent. Critical examples removed entirely. | CRITICAL |
| Act | [03_act.md](03_act.md) | MIXED — reasonable core/domain split, but core has useless generic placeholders. Kitchen injection section exists and works. | MEDIUM |
| Reply | [04_reply.md](04_reply.md) | MOSTLY OK — system prompt and subdomains correctly kitchen-specific. ~8 genericized lines in identity/principles. | LOW |
| Summarize | [05_summarize.md](05_summarize.md) | CLEAN — no changes. Kitchen examples in system prompt are about behavior pattern, not domain. | NONE |
| Act Quick | [06_act_quick.md](06_act_quick.md) | SAME AS ACT — mirrors Act node pattern. | MEDIUM |
| Router | N/A | Removed from post-refactor pipeline (Understand absorbed routing) | N/A |

## Summary of Damage

### What's wrong
1. **Understand prompt** — all examples replaced with "Item A", "that item", "show my items". The LLM gets zero signal about what entities exist or how users refer to them.
2. **Think prompt** — the most critical node. `<alfred_context>` and `<system_structure>` are still kitchen-specific (subdomains, linked tables, recipes, meal plans) but examples use `item_1`, `gen_item_1`. The LLM gets **inconsistent signals** — worse than either pure kitchen or pure generic. Critical workflow examples (multi-entity operations, iterative meal planning, post-action awareness table) were REMOVED entirely.
3. **Act prompt** — core template has useless placeholders but kitchen content is properly injected in a separate section. Architecturally closest to correct.
4. **Reply prompt** — mostly fine. System prompt identity comes from domain correctly. Minor genericization in principles section.

### What's correct
1. **Summarize** — untouched, works fine
2. **Reply system prompt header** — correctly loaded from `domain.get_system_prompt()`
3. **Reply subdomains section** — correctly injected by domain with kitchen formatting guides
4. **Act domain injection** — "Kitchen-Specific Read Patterns" section is properly separated and injected
5. **Act user prompt** — schema, domain descriptions, field enums all come from domain injection correctly

## Architectural Conclusion

The refactoring confused two things:
1. **Core orchestration shell** — "You are the Understand node, resolve refs, curate context" + Pydantic output contract. This is what core should own.
2. **Domain prompt content** — all examples, entity types, quick mode tables, subdomain descriptions, workflow patterns. This must come from the domain.

The genericized prompts are valuable as **template documentation** for domain implementors ("here's the shape your examples should follow") but must NOT be what gets sent to the LLM at runtime.

## What Needs to Happen

### Per-node fix priority

1. **Think** (CRITICAL) — needs the most work. The entire `<alfred_context>`, `<system_structure>`, `<conversation_management>`, and `<output_contract>` examples sections should come from domain injection. Core should only own `<identity>`, `<precedence>`, and the structural skeleton of other sections.

2. **Understand** (HIGH) — all examples, quick mode table, reference resolution table, curation examples must come from domain. Core keeps: role definition, output contract structure, "what you don't do" list.

3. **Act** (MEDIUM) — already partially correct. Replace useless generic placeholders in core template with truly structural examples or remove them. Domain injection mechanism works.

4. **Reply** (LOW) — mostly fine. Fix ~8 genericized lines in `<identity>` and `<principles>`.

5. **Summarize** (NONE) — no action needed.

### Architecture target

For each node, the prompt should be assembled as:
```
CORE SHELL (orchestration role + output contract structure)
  + DOMAIN CONTENT (examples, entity guidance, workflow patterns)
  + DYNAMIC CONTEXT (user profile, entities, conversation history, current message)
```

The current genericized `.md` files should be renamed as template documentation (e.g., `understand_template.md`) and NOT loaded at runtime. Runtime prompts should be composed from core shell + domain injection.
