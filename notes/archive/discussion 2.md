ARCHITECTURE_ADDENDUM.md

A tactical consolidation of architectural evolution, tradeoff resolution, and forward-compatible design decisions

🧠 Context and Purpose

This document captures post-v1 architectural evolutions and clarifies LLM-agent orchestration decisions made in follow-up discussions. It does not supersede the original ARCHITECTURE.md but instead locks in clarified mental models, design boundaries, and system behaviors needed for robust multi-agent expansion, better planning-execution separation, and safer reasoning control.

I. Planning, Execution, and the Ambiguity Contract
🔑 Principle: "Ambiguous plans, deterministic execution"
Layer	Role	Ambiguity Allowed?	Responsibility
Planner	Generate intent-level steps	✅ Yes	Hypothesize task sequence, not tools
Execution Loop	Perform steps + act	❌ No	Structured action schema: act, tool_call, complete, fail
Orchestrator	Route + validate flow	❌ No	Enforce allowable transitions, detect block/failure

→ We no longer define brittle action labels like C-G-MEALPLAN.
→ We now rely on natural-language steps (e.g., "generate shopping list") at the planning level, which LLMs interpret inside a strict loop with defined transitions.

II. Planner Output Format

Planners must emit:

A goal

A list of intent-level steps (each with optional complexity tag)

Optional handoff metadata (for agent transitions)

💡 Example:

{
  "goal": "Build a 5-day vegetarian meal plan",
  "steps": [
    { "name": "Draft meal ideas", "complexity": "high" },
    { "name": "Check pantry gaps", "complexity": "low" },
    { "name": "Suggest substitutions", "complexity": "medium" }
  ]
}


🔁 Each step becomes a unit of execution evaluated within the loop. The loop enforces action schema; the planner never encodes tool names, function parameters, or execution logic.

III. Reasoning Effort and Complexity-Aware Execution

Planner-assigned complexity tags (low / medium / high) allow:

Dynamic model selection (e.g., GPT-4o vs GPT-5.2)

Parameter tuning (e.g., reasoning_effort)

Cost-efficient execution

💡 Mapping:

Complexity	Model	Reasoning Effort	Use Case
Low	4o	none / low	Inventory lookup, data reads
Medium	GPT-5.1	medium	Simple synthesis, filtering
High	GPT-5.2	high / xhigh	Generating full meal plans, recipes
IV. Context and Query Design: Pre vs In-loop

📦 Two types of retrieval:

Pre-planning Context Assembly

Summary facts to help planner reason (e.g., “inventory low”, “user avoids spicy food”)

Done before planning or in router step

Small, high-signal inputs only

In-loop Querying

Tool-invoked SQL or retrieval

Actioned by the executor, not planner

Used for ground-truth during execution

🛑 Do not:

Query the full database preemptively

Force planner to construct tool calls

✅ Do:

Separate context (summary) from execution (precision)

V. Multi-Agent Planning and Execution

🎯 Top-level planner outputs:

{
  "workflow": [
    { "agent": "pantry", "goal": "...", "produces": ["meal_plan_draft"] },
    { "agent": "coach", "goal": "...", "consumes": ["meal_plan_draft"] },
    { "agent": "pantry", "goal": "...", "consumes": ["coach_feedback"] }
  ]
}


Each agent:

Runs its own plan/execute loop

May emit call_agent actions to invoke peers

Uses structured handoff artifacts (e.g., meal_plan_id, not raw blobs)

🔄 Planner replanning happens:

Only at boundaries or when agent emits blocked

Controlled by orchestrator, not the agent

VI. Finalization and Summarization

🧵 All user-facing replies are synthesized by:

The agent itself (if single-agent, low complexity)

A separate summarizer/synthesizer (if multi-agent or high complexity)

↩️ Each agent emits an internal artifact. Only the synthesizer formats a final message.

VII. Execution Loop Actions

Permitted LLM action types inside loop:

Action	Description
tool_call	Execute a named tool with arguments
step_complete	Mark step done with optional notes
ask_user	Emit clarifying question
fail	Exit the loop with reason
blocked	Emit structured “I’m stuck” signal
call_agent	Request invocation of another agent

➡️ This allows orchestration code to remain schema-bound and policy-safe.

VIII. Linkage, Identity, and Tool Discipline

LLMs reason in terms of objects. Tools operate on IDs. To bridge this:

Introduce canonical entity_ref contracts: {type, id, label}

Return IDs from all tools; never expect models to fabricate them

Tools perform cross-table joins; agents just reason about concepts

Example:

{
  "type": "ingredient",
  "id": "ing_003",
  "label": "tomato"
}


📐 This supports strong DB integrity and LLM decoupling from schema logic.

IX. Clarification, Replanning, and Graceful Failure

✨ New blocked action lets agents express:

{
  "action": "blocked",
  "reason": "User preferences unclear for lunch",
  "suggested_next": "ask_user"
}


The orchestrator chooses whether to:

Ask for clarification

Trigger replanning

Fail gracefully

This cleanly separates semantic uncertainty from system logic.

X. Forward-Compatible Patterns (Summary Table)
Component	Behavior	Optionality
Planner	Emits agent+step plan	Required
Complexity Tags	Drive model config	Recommended
Synthesizer	Finalizes user reply	Required for multi-agent
call_agent	Enables cross-agent loops	Optional until multi-agent
blocked	Structured uncertainty escape	Strongly Recommended
entity_ref	Object → ID → DB abstraction	Strongly Recommended
XI. Deferred Implementation Topics

Not unique to your product but still needed:

✅ Supabase integration (standard tools, types)

✅ Session memory scope + expiry

✅ Persona tone & prompt framing

✅ Testing, error handling

✅ Auth, logging, metadata infra

You’ve made all architectural decisions needed to defer these until they’re implementation-relevant.

✅ Final Status

You’ve now locked in:

Coarse-grained global plan

Local plans per agent

Reasoning parameterization by complexity

Tool-bounded execution logic

Multi-agent orchestration structure

LLM-internal reasoning properly scoped

Future-ready: additive patterns, not disruptive rewrites

The thinking here is durable.