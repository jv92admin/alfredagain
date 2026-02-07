# Refactoring Discipline Skill

Guidelines for the alfred-core extraction refactor. Reference this before making changes.

## Core Principles

### 1. Parallel Structure First
- Build new abstractions alongside old code
- Never break existing functionality during extraction
- Old code continues working until new code is proven

### 2. Phase Gates
- Tests must pass before moving to next phase
- No skipping verification steps
- If tests fail, fix before proceeding

### 3. Deprecation Over Deletion
- Add deprecation aliases for moved constants
- Old imports should warn, not break
- Only delete after full migration is verified

## Refactoring Checklist

Before each change:
- [ ] Read the existing code thoroughly
- [ ] Understand all callers/consumers
- [ ] Write test for current behavior if missing
- [ ] Make smallest possible change
- [ ] Run tests after each atomic change

After each change:
- [ ] Verify no behavior change (unless intentional)
- [ ] Update any affected imports
- [ ] Check for duplicate definitions
- [ ] Run `pytest` to verify nothing broke

## Common Pitfalls

### 1. Breaking Circular Imports
When extracting to new modules:
- Watch for circular import chains
- Use TYPE_CHECKING imports for type hints
- Consider interface modules for breaking cycles

### 2. Losing Context in Abstractions
- Preserve semantic meaning in method names
- Don't over-abstract on first pass
- Kitchen-specific behavior should remain explicit

### 3. Copy-Paste Drift
- When duplicating code temporarily, track all copies
- Use TODO comments with ticket references
- Set deadline for consolidation

### 4. Test Coverage Gaps
- Extraction can orphan test coverage
- Verify tests exercise the new code paths
- Add integration tests for cross-module boundaries

### 5. Documentation Staleness
- Update docstrings when moving code
- Keep CLAUDE.md constraints in sync
- Update architecture docs for significant changes

## Documentation Discipline

### When Moving Code
1. Update the source file's docstring/comments
2. Add deprecation notice if leaving stub
3. Update any architecture docs that reference it
4. Add entry to migration changelog if public API

### When Adding Abstractions
1. Document the protocol/interface contract
2. Explain why this abstraction exists
3. Provide example implementation
4. Note any invariants that must be preserved

## Unit Test Strategy

### For Extracted Core Code
- Use StubDomainConfig (minimal implementation)
- Mock database with in-memory store
- Test protocol compliance, not kitchen specifics

### For Domain-Specific Code
- Use KITCHEN_DOMAIN config
- Test against real fixtures
- Verify integration with core

### Test Naming Convention
```
test_{component}_{behavior}_{scenario}
test_id_registry_translates_uuid_to_ref
test_workflow_routes_to_correct_subdomain
```

## Phase-Specific Notes

### Phase 0: DRY workflow.py
- Extract shared logic to internal helpers
- Do NOT change function signatures yet
- Focus: reduce duplication, identify patterns

### Phase 1: Define Interface
- Protocol is abstract, implementation concrete
- Don't wire up consumers yet
- Focus: get the contract right

### Phase 2: Wire Up Domain Config
- One file at a time
- Keep old constants as deprecated aliases
- Focus: prove the abstraction works

### Phase 3: Extract Personas
- Large file moves, watch imports
- Test persona rendering explicitly
- Focus: clean separation of content

### Phase 4: Package Extraction
- Create alfred-core as sibling directory
- Use relative pip install for testing
- Focus: clean dependency graph

## Red Flags

Stop and reassess if you see:
- More than 3 files changing in one commit
- Test failures you don't understand
- Circular import errors
- "This would be easier if we just..."
- Urge to refactor adjacent code

## Recovery Patterns

If something breaks:
1. `git stash` current work
2. Verify main branch works
3. Identify smallest breaking change
4. Fix that one thing
5. Re-apply other changes incrementally

## Phase 3+ Deferred Items

Kitchen-specific code identified during Phase 2 that needs extraction in later phases:

### id_registry.py (Phase 3)
- **Lines 91-92**: Recipe-specific detail tracking initialization
- **Lines 219-224**: `_compute_entity_label()` has special meal_plan formatting
- **Lines 274-300**: Recipe detail tracking (`_track_recipe_read_level`, `last_read_level`, `last_full_turn`)
- **Line 658**: Hardcoded FK fallback set `{"recipe_id", "ingredient_id", "meal_plan_id", "task_id"}`

### act.py (Phase 3)
- **Lines 560-598**: `_normalize_subdomain()` has kitchen-specific subdomain aliases
- **Lines 1984-1992**: `table_map` in `act_quick_node()` hardcodes kitchen tables
- **Line 66**: `TRACKED_ENTITY_TYPES` constant lists kitchen-specific types

### Action Items
When tackling Phase 3:
1. Move recipe/meal-specific tracking logic to KITCHEN_DOMAIN
2. Add `get_subdomain_aliases()` method to DomainConfig for normalize_subdomain
3. Replace TRACKED_ENTITY_TYPES with `domain.entities.keys()`
4. Add FK fallback configuration to DomainConfig or derive from entities
