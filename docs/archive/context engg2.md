1) UNDERSTAND: Parsing + Entity Resolution + Constraint Compilation
Boundary

Understand should convert fuzzy language into structured signals.
It is allowed to be probabilistic, but its output must be machine-checkable and confidence-scored.

What it should resolve
A. Intent classification (lightweight, stable)

intent.type: e.g., plan_meals, add_inventory, generate_recipes, update_preferences

intent.mode: propose vs commit vs clarify

intent.scope: e.g., dinners, week, recipes_only

Why here: Intent is linguistic. If Think has to infer intent repeatedly, you’ll get drift. Understand is your “parser.”

B. Entity mentions → canonical candidates (with confidence)

entity_mentions.ingredients[]

raw_text, candidate_ids[], confidence, resolution_policy

entity_mentions.recipes[]

entity_mentions.tools[] (air fryer, Instant Pot)

entity_mentions.time[] (“this week”, “tomorrow”, “weekdays”)

Why here: Canonical identity is state-adjacent. You want IDs/enums downstream. Think should not guess what “greens” means.

C. Constraint compilation (crucial)

Turn natural language into enforceable rules:

constraints.exclusions.ingredient_ids[]

constraints.allergies[]

constraints.dietary[]

constraints.cook_days[] (enum)

constraints.servings_rule

constraints.budget_ceiling (if relevant)

constraints.max_prep_time (if relevant)

Why here: Constraints must be stable and should not be “remembered” later. This is the first place you turn language into law.

D. Missing info detection

open_questions[] with canonical options (not freeform)

blocking_fields[]

Why here: It prevents downstream inventing. Also makes clarify decisions deterministic.

E. Session state update proposals (optional, gated)

state_patch_proposal (add aliases, add new ingredient entity, etc.)

include confidence thresholds and “needs confirmation” flags

Why here: It’s the only place where ambiguous entity creation should happen.

What Understand should NOT do

produce plans

choose recipes

decide CRUD steps

generate long content

That belongs downstream.

2) THINK

Role: Compiled state → execution plan + data needs (deterministic)

Think does coordination, not interpretation.

ThinkPlan (revised)
Goal & success criteria
{
  "goal": "Propose a 7-day dinner plan aligned with constraints",
  "success_criteria": [
    "7 dinner entries proposed",
    "no excluded ingredients used",
    "meals scheduled only on allowed cook days"
  ]
}


Why here:
Defines “done” in system terms, not language terms.

Data requirements (macro-based, lightweight)

This replaces bespoke resources.

{
  "data_requirements": [
    {
      "subdomain": "meal_plans",
      "intent": "read_window",
      "time_window": "next_7_days",
      "fields": "default",
      "purpose": "avoid duplicates"
    },
    {
      "subdomain": "inventory",
      "intent": "read_snapshot",
      "filters": {
        "expiring_within_days": 7
      },
      "fields": "default",
      "purpose": "prioritize perishables"
    },
    {
      "subdomain": "recipes",
      "intent": "read_catalog_index",
      "fields": "minimal",
      "purpose": "candidate selection"
    }
  ]
}

Why this fits the boundary

Think does not name tables or columns

Think does not describe joins

Think does not say “if needed”

Every field is bounded (enums, ints, IDs)

Act will map:

subdomain + intent + time_window + fields
→ deterministic db_read patterns

Step graph (no execution semantics)
{
  "steps": [
    {
      "step_id": "retrieve_context",
      "step_type": "retrieve",
      "inputs": ["data_requirements"]
    },
    {
      "step_id": "analyze_candidates",
      "step_type": "analyze",
      "inputs": ["retrieved_state", "constraints"]
    },
    {
      "step_id": "generate_plan",
      "step_type": "generate",
      "inputs": ["analysis_output"]
    }
  ]
}


Why here:
Think designs the program, not the queries.

What Think explicitly does not do

guess entity identity

enforce constraints

normalize schema payloads

decide CRUD order

3) ACT: Deterministic Retrieval/Mutation + Artifact Generation (No Re-Interpretation)
Boundary

Act is a transactional executor.

It should not “figure out what you meant.”

It should not fix plan ambiguities.

It should not invent missing pieces.

It can generate content only where explicitly instructed, and even then generation should produce artifacts with a strict structure.

What Act should resolve
A. Execute declared reads (ideally bundled)

return retrieved_state with stable keys

return snapshot_id or retrieved_at timestamps (optional but useful)

Why here: Act is the tool runner. It produces the grounded working set.

B. Execute writes only with validated payloads

take normalized inputs (prefer IDs)

write

return created IDs + row counts

Why here: Act is how state becomes real. It must be deterministic.

C. Generate artifacts, but do not normalize them

When generating recipes, meal plans, shopping lists, etc., Act should output:

artifact.type: recipe_draft, meal_plan_draft, etc.

artifact.schema_version

artifact.content: full structured content

Then you have another explicit normalization step (either a write step with a mapping spec, or a compiler step).

Why: This prevents the “generated rich recipe → Act saves simplified recipe” problem. Normalization is not Act’s job unless the mapping is deterministic and specified.

D. Output deltas, not narratives

Act should output:

state_deltas (what changed)

artifacts_created

errors / blocked_reason

note_for_next_step (IDs, references only)

Why here: Keeps later stages honest.

What Act should NOT do

guess which entities map to which IDs

coerce cuisines/tags without a defined mapping

“clean up” generated content to fit schema unless explicitly instructed with a mapping

decide whether to save vs propose

Recommended minimal contract change

Have Act always return, for any CRUD step:

created_ids[]

updated_ids[]

deleted_ids[]

optional display_map keyed by ID

Then Summarize never needs resolution; it just renders IDs and names deterministically.

4) REPLY: Presentation Layer Over State + Artifacts
Boundary

Reply is a renderer, not a reasoner.

It must never become a semantic patch layer. It should not “smooth over” inconsistencies between artifacts and state.

What it should resolve
A. Select what to show (priority formatting)

choose ordering (outcome-first)

collapse low-signal logs

present artifacts in full where required

Why here: This is user experience, not state.

B. Explicitly label representational status

“generated but not saved”

“saved (simplified catalog entry)”

“full recipe content below (as generated)”

Why here: This preserves the state/context boundary for users and prevents trust erosion.

C. Offer one next step

But only based on:

what was actually done

what is in state

what artifacts exist

Why here: Keeps flow moving without re-planning.

What Reply should NOT do

reinterpret user intent

justify decisions that were not explicitly recorded

claim correctness beyond what state indicates

5) SUMMARIZE: Immutable Ledger of What Happened
Boundary

Summarize is an audit log writer.

It should be “boring” and deterministic — and closer to the truth than Reply.

What it should resolve
A. Execution ledger

steps completed

tools called

entities created/updated/deleted

IDs, counts, timestamps

Why here: This is how you debug and prevent silent drift.

B. State deltas snapshot

before/after counts (optional)

list of mutated entity IDs

pointer to artifacts (if persisted)

Why here: Summarize is where “state truth” is captured in a durable form.

C. Error classification

schema errors

missing entity mappings

conflicts / duplicates

validation failures

Why here: Summarize should help the system learn where boundaries are leaking.

What Summarize should NOT do

propose next steps

interpret user’s emotions

describe food nicely

add new content

Summarize can add value by producing an audit-friendly crosswalk, but only if it is derived from committed state:

Example crosswalk structure

created entities: IDs + canonical names

updated entities: IDs + fields changed

deleted entities: IDs