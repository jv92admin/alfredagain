# Summarize Node — Prompt Regression Audit

**Pre-refactor:** `prompt_logs_downloaded/20260203_014946/14_summarize.md`
**Post-refactor:** `prompt_logs/20260207_235146/08_summarize.md`

## System Prompt

**IDENTICAL.** Zero changes. Both versions:

```
Summarize what was accomplished in ONE sentence.
Focus on: what action was taken, what was created/found/updated.

**CRITICAL: Proposals ≠ Completed actions**
If the text says "I'll do X" or "Here's my plan" or "Does this sound good?" — that's a PROPOSAL.
Do NOT summarize proposals as completed actions.

- Proposal: "I'll save the recipes" → Summary: "Proposed to save recipes; awaiting confirmation."
- Completed: "Done! I saved the recipes." → Summary: "Saved recipes: [names]"

**CRITICAL: Use EXACT entity names from the text.** Do NOT paraphrase or generalize.
If the text says "Mediterranean Chickpea & Herb Rice Bowl", use that EXACT name.
Do NOT make up names that sound similar but aren't in the original text.

Good: "Saved recipes: Mediterranean Chickpea & Herb Rice Bowl."
Bad: "Saved the recipes." (too vague)
Bad: "Saved Minty Chickpea Salad." (made up name not in original)
Bad: "Saved three rice bowl recipes." (when text says "I'll save" = proposal, not done)

Keep summaries specific with exact names or IDs when available.
```

Note: The Summarize system prompt still uses kitchen-specific examples ("recipes", "Mediterranean Chickpea & Herb Rice Bowl", "Minty Chickpea Salad"). These were NOT genericized — but they also don't need to be, since the examples are about the behavior pattern (use exact names) not about the domain.

## User Prompt

The user prompt is entirely dynamic — it's the Reply response text plus entity names. No template differences to audit.

## Verdict: NO CHANGE (Clean)

Summarize is the simplest node and was not touched by the genericization. The system prompt is effectively domain-neutral in purpose (summarize accurately, use exact names) even though its examples happen to be kitchen-flavored. This is fine.
