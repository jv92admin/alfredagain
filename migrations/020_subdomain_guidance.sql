-- Migration 020: Subdomain Guidance Modules
-- Adds per-subdomain narrative preferences for context injection
--
-- Structure: JSONB with subdomain keys, each containing a narrative string
-- Max ~200 tokens per subdomain (enforced in application layer)
--
-- Example:
-- {
--   "inventory": "Assume common staples available. Doesn't track partial consumption.",
--   "recipes": "Write for intermediate skill. Skip obvious steps. 6-8 steps max.",
--   "meal_plans": "Cooks 2-3x/week on weekends. Batch prep friendly. Fast weeknight execution.",
--   "shopping": "Prefers bulk shopping. Consolidate trips. Comfortable with substitutions.",
--   "tasks": "Day-before reminders preferred. Link prep tasks to meals."
-- }

ALTER TABLE preferences ADD COLUMN IF NOT EXISTS 
    subdomain_guidance JSONB DEFAULT '{}';

COMMENT ON COLUMN preferences.subdomain_guidance IS 
    'Per-subdomain narrative preferences for LLM context injection. Keys: inventory, recipes, meal_plans, shopping, tasks. Values: ~200 token max narrative strings.';
