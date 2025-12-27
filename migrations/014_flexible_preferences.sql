-- Migration 014: Flexible Preferences
-- Adds planning_rhythm and current_vibes for more natural preference expression

-- Planning tags (2-3 max) - how user wants to cook right now
-- Examples: "weekends only", "30min weeknights", "meal prep sundays"
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS 
    planning_rhythm TEXT[] DEFAULT '{}';

-- Vibe tags (up to 5) - current culinary interests
-- Examples: "more vegetables", "fusion experiments", "salad skills", "comfort food"
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS 
    current_vibes TEXT[] DEFAULT '{}';

-- Note: We keep the old fields (cooking_frequency, time_budget_minutes, preferred_complexity)
-- for backwards compatibility, but the new fields are preferred for LLM interaction.
-- The old fields can be deprecated later or used as structured fallbacks.

COMMENT ON COLUMN preferences.planning_rhythm IS 'Freeform cooking schedule tags (2-3 max). E.g., ["weekends only", "quick weeknights"]';
COMMENT ON COLUMN preferences.current_vibes IS 'Current culinary interests/goals (up to 5). E.g., ["more vegetables", "fusion experiments"]';

