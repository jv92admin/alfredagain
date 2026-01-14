The Context Model: Three Layers
┌─────────────────────────────────────────────────────────────────────┐│ LAYER 1: ENTITY CONTEXT                                              ││ "What objects exist in our working memory"                          ││ Managed by: Understand (curation) + SessionIdRegistry (storage)     │├─────────────────────────────────────────────────────────────────────┤│ LAYER 2: TURN NARRATIVE                                              ││ "What happened and why"                                             ││ Managed by: Summarize (builds) + Think/Act (consumes)               ││ ← THIS IS WHAT'S MISSING                                            │├─────────────────────────────────────────────────────────────────────┤│ LAYER 3: CONVERSATION HISTORY                                        ││ "What was said"                                                     ││ Managed by: Summarize (compresses) + all nodes (read)               │└─────────────────────────────────────────────────────────────────────┘
What Each Layer Contains
Layer 1: Entity Context
What: Refs to objects (recipe_1, inv_5, gen_meal_plan_1)
Who manages: Understand (decides what stays active) + Registry (stores)
Retention: Last 2 turns auto-retained + explicit retentions from Understand
## Entities in Context### Recent (last 2 turns)- recipe_3: Air Fryer Paneer Tikka (recipe) [read]- recipe_4: Chicken Tikka Bites (recipe) [read]- inv_1..inv_59: [inventory items]### Retained (older, Understand decided)- gen_meal_plan_1: Weekly Plan (turn 2) — *"User's ongoing goal"*### Pending (unsaved)- gen_recipe_1: Custom Thai Curry — *needs save confirmation*### Excluded (this turn)- recipe_5, recipe_6 — *User said no french toast, no wings*
Layer 2: Turn Narrative (THE MISSING PIECE)
What: What happened each turn — steps executed, conclusions, decisions
Who manages: Summarize (builds from step_results + understand_output)
Retention: Last 2 turns full detail, older compressed
## What Happened### Turn 3 (current session)**User asked:** "exclude french toast and wings"**We did:**  1. Analyzed existing recipe options  2. Excluded recipe_5 (French Toast), recipe_6 (Wings) per user**Result:** 4 remaining options: recipe_3, recipe_4, recipe_8, recipe_9**Understand noted:** Demoted recipe_5, recipe_6### Turn 2**User asked:** "no cod this week"**We did:**  1. Read 9 recipes → recipe_1 through recipe_9  2. Read 59 inventory items  3. Analyzed for cod exclusion**Result:** 6 options presented (excluded cod recipes)### Earlier (compressed)User started meal planning session. Exploring recipe options.
Layer 3: Conversation History
What: User messages + assistant responses
Who manages: Summarize (appends + compresses)
Retention: Last 2-3 turns full text, older turns → narrative summary
## ConversationUser: can you help me plan some meals?Alfred: Absolutely! You usually cook on Sundays and Wednesdays...User: lets not do cod this week?Alfred: Here are 6 recipes that fit... [list]User: lets not do the french toast or wings→ (current, being processed)
How They Cascade in a Prompt
Here's how a Think prompt should be structured:
<session_context>## User Profile[Static: diet, allergies, equipment, skill]## Kitchen Dashboard  [Semi-static: inventory count, recipe count, meal plan status]</session_context><entity_context>## Entities in Context### Recent (last 2 turns) — already loaded, reference by ID- recipe_3: Air Fryer Paneer Tikka [read]- recipe_4: Chicken Tikka Bites [read]... (IDs, labels, actions)### Excluded this turn- recipe_5, recipe_6 — user rejected### Remaining viable- recipe_3, recipe_4, recipe_8, recipe_9</entity_context><turn_narrative>## What We've Done### Last turnSteps: Read recipes (9), Read inventory (59), Analyze (6 viable)Conclusion: 6 cod-free recipes fit inventoryUser response: "exclude french toast and wings"### This turnUnderstand: Demoted recipe_5, recipe_6Remaining: recipe_3, recipe_4, recipe_8, recipe_9</turn_narrative><conversation_history>## Recent Conversation[Last 2-3 turns full text]## Earlier[Compressed: "User started meal planning, exploring options"]</conversation_history><current_task>**User says:** "lets not do the french toast or wings"**Today:** 2026-01-13**Mode:** PLANDO NOT re-read recipes — they're in context. Plan the next phase.</current_task>
The Retention Policy
Content Type	Last 2 Turns	Older	Very Old
Entity refs	Auto-retained	Only if Understand retained	Dropped
Turn narrative	Full detail	Compressed	Dropped
Conversation	Full text	Summary	Summary chains
The 2-turn window is consistent across both systems:
Registry: ref_turn_last_ref within 2 turns = "recent"
Narrative: Last 2 TurnExecutionSummary = full detail
Conversation: Last FULL_DETAIL_TURNS (currently 3) = full text
Who Manages What
Manager	Responsibility	Retention Logic
Understand	Entity curation	"Is this ref still relevant?" → retain_active with reason
Summarize	Narrative compression	"What happened?" → build TurnExecutionSummary
Registry	Entity storage	Refs + labels + turn tracking
The key insight: They're parallel systems:
Understand = entity memory manager (what objects)
Summarize = narrative memory manager (what happened)
Both use ~2 turn "recent" window + explicit retention for important older stuff.
Reply's Role in Conversation
You're right — Reply isn't prompted to be conversational. It's prompted to "present data."
Current Reply: "Here are the results of execution..."
Should be: "Got it — no French toast or wings. That leaves us with 4 solid options..."
Reply should:
Acknowledge the conversation flow ("Got it", "Okay so...")
Present results in context of what user asked
Bridge to next step naturally
Maintain the collaborative tone
Proposed Prompt Sections (Standardized)
For Think and Act (multi-step):
1. <session_context>     — Profile, preferences, dashboard (static)2. <entity_context>      — What refs are active, what's excluded, what's viable3. <turn_narrative>      — What happened last 2 turns (steps, conclusions)4. <conversation>        — What was said (full recent, compressed older)5. <current_task>        — What to do now
For Reply:
1. <conversation_flow>   — Recent exchanges (for tone continuity)2. <execution_results>   — What happened this turn3. <entity_context>      — What to present (refs with labels)4. <reply_guidance>      — Be conversational, acknowledge, bridge
Implementation: What Changes
Component	Current	Needed
Summarize	Thin audit log	Build TurnExecutionSummary with steps + notes + conclusions
Think prompt	Has conversation, entities	Add <turn_narrative> section
Act prompt	Has entities, current step	Add prior turn context for analyze/generate
Reply prompt	"Present data"	Add conversation continuity guidance
State	Has conversation, id_registry	Add turn_execution_summaries: list
When Narratives Stop Appending
Turn 1: TurnExecutionSummary_1 created → storedTurn 2: TurnExecutionSummary_2 created → storedTurn 3: TurnExecutionSummary_3 created → stored         TurnExecutionSummary_1 → COMPRESSED into "earlier_summary" stringTurn 4: TurnExecutionSummary_4 created → stored         TurnExecutionSummary_2 → COMPRESSED...
Rule: Keep last 2 TurnExecutionSummary objects, compress older into narrative string.
This mirrors how conversation works: last N turns full, older compressed.
Does This Mental Model Make Sense?
The three layers:
Entities (what objects) — Understand curates, Registry stores
Narratives (what happened) — Summarize builds, Think/Act consume ← MISSING
Conversation (what was said) — Summarize compresses, all read
Both entity and narrative use 2-turn "recent" + explicit retention for important older stuff.