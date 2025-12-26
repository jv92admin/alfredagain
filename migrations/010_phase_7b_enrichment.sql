-- Migration 010: Phase 7b Async Enrichment
-- Adds: cooking_log table, flavor_preferences trigger
-- Run this migration in Supabase SQL Editor

-- ============================================================================
-- 1. Cooking Log Table
-- ============================================================================
-- Event log for tracking what was cooked, when, and ratings

CREATE TABLE IF NOT EXISTS cooking_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_id UUID REFERENCES recipes(id) ON DELETE SET NULL,
    cooked_at TIMESTAMPTZ DEFAULT NOW(),
    servings INT,
    rating INT CHECK (rating >= 1 AND rating <= 5),
    notes TEXT,
    from_meal_plan_id UUID REFERENCES meal_plans(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE cooking_log ENABLE ROW LEVEL SECURITY;

-- User can only see/modify their own cooking logs
CREATE POLICY cooking_log_user_policy ON cooking_log
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_cooking_log_user_date ON cooking_log(user_id, cooked_at DESC);
CREATE INDEX IF NOT EXISTS idx_cooking_log_recipe ON cooking_log(recipe_id);

-- Add comments
COMMENT ON TABLE cooking_log IS 'Event log tracking what was cooked, when, and user ratings';
COMMENT ON COLUMN cooking_log.rating IS 'User rating 1-5 stars';
COMMENT ON COLUMN cooking_log.from_meal_plan_id IS 'If cooked from a meal plan, link to that plan';


-- ============================================================================
-- 2. Flavor Preferences Trigger
-- ============================================================================
-- Automatically update flavor_preferences when a cooking_log entry is added
-- This tracks ingredient usage frequency for personalization

-- Ensure flavor_preferences table has the right structure
-- (Should already exist from core tables, but add columns if missing)
ALTER TABLE flavor_preferences ADD COLUMN IF NOT EXISTS times_used INT DEFAULT 0;
ALTER TABLE flavor_preferences ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ;

-- Create or replace the trigger function
CREATE OR REPLACE FUNCTION update_flavor_preferences()
RETURNS TRIGGER AS $$
BEGIN
    -- For each ingredient in the cooked recipe, increment usage count
    INSERT INTO flavor_preferences (user_id, ingredient_id, times_used, last_used_at)
    SELECT 
        NEW.user_id, 
        ri.ingredient_id, 
        1, 
        NOW()
    FROM recipe_ingredients ri 
    WHERE ri.recipe_id = NEW.recipe_id
      AND ri.ingredient_id IS NOT NULL
    ON CONFLICT (user_id, ingredient_id) 
    DO UPDATE SET 
        times_used = flavor_preferences.times_used + 1,
        last_used_at = NOW();
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create the trigger
DROP TRIGGER IF EXISTS trg_update_flavor_prefs ON cooking_log;
CREATE TRIGGER trg_update_flavor_prefs
    AFTER INSERT ON cooking_log
    FOR EACH ROW 
    WHEN (NEW.recipe_id IS NOT NULL)
    EXECUTE FUNCTION update_flavor_preferences();

-- Add comments
COMMENT ON FUNCTION update_flavor_preferences IS 'Automatically updates flavor_preferences when user logs a cooked recipe';


-- ============================================================================
-- 3. Helper View for Top Ingredients (optional but useful)
-- ============================================================================
-- Pre-aggregated view of top ingredients per user

CREATE OR REPLACE VIEW user_top_ingredients AS
SELECT 
    user_id,
    ingredient_id,
    i.name AS ingredient_name,
    times_used,
    last_used_at,
    RANK() OVER (PARTITION BY user_id ORDER BY times_used DESC) as rank
FROM flavor_preferences fp
JOIN ingredients i ON fp.ingredient_id = i.id
WHERE times_used > 0;

COMMENT ON VIEW user_top_ingredients IS 'Ranked list of most-used ingredients per user';

