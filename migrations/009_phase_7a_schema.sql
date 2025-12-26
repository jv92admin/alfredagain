-- Migration 009: Phase 7a Schema Expansion
-- Adds: expanded preferences, prep as meal_type, recipe variations, tasks table
-- Run this migration in Supabase SQL Editor

-- ============================================================================
-- 1. Expanded Preferences
-- ============================================================================
-- Add new columns for richer user profile

ALTER TABLE preferences ADD COLUMN IF NOT EXISTS nutrition_goals TEXT[] DEFAULT '{}';
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS cooking_frequency TEXT;
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS available_equipment TEXT[] DEFAULT '{}';
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS time_budget_minutes INT DEFAULT 30;
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS preferred_complexity TEXT DEFAULT 'moderate';

-- Add comments for documentation
COMMENT ON COLUMN preferences.nutrition_goals IS 'Array of nutrition goals: high-protein, low-carb, low-sodium, etc.';
COMMENT ON COLUMN preferences.cooking_frequency IS 'How often user cooks: daily, 3-4x/week, weekends-only, rarely';
COMMENT ON COLUMN preferences.available_equipment IS 'Kitchen equipment: instant-pot, air-fryer, grill, sous-vide, etc.';
COMMENT ON COLUMN preferences.time_budget_minutes IS 'Typical time budget per meal in minutes';
COMMENT ON COLUMN preferences.preferred_complexity IS 'Recipe complexity preference: quick-easy, moderate, elaborate';


-- ============================================================================
-- 2. Prep as meal_type
-- ============================================================================
-- Expand meal_type enum to include 'prep' for batch cooking / prep work

-- First drop existing constraint if it exists
ALTER TABLE meal_plans DROP CONSTRAINT IF EXISTS meal_plans_meal_type_check;

-- Add new constraint with 'prep' option
ALTER TABLE meal_plans ADD CONSTRAINT meal_plans_meal_type_check 
    CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'prep'));

COMMENT ON COLUMN meal_plans.meal_type IS 'Type of meal: breakfast, lunch, dinner, snack, or prep (for batch cooking/prep work)';


-- ============================================================================
-- 3. Recipe Variations
-- ============================================================================
-- Add parent_recipe_id to support recipe variations (e.g., "spicy version of butter chicken")

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS parent_recipe_id UUID REFERENCES recipes(id);

-- Create index for efficient variation lookups
CREATE INDEX IF NOT EXISTS idx_recipes_parent ON recipes(parent_recipe_id) WHERE parent_recipe_id IS NOT NULL;

COMMENT ON COLUMN recipes.parent_recipe_id IS 'Links to parent recipe for variations (e.g., spicy version of base recipe)';


-- ============================================================================
-- 4. Tasks Table
-- ============================================================================
-- Simple transient task list for prep work, reminders, shopping errands

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_date DATE,
    category TEXT CHECK (category IN ('prep', 'shopping', 'cleanup', 'other')),
    completed BOOLEAN DEFAULT false,
    recipe_id UUID REFERENCES recipes(id),
    meal_plan_id UUID REFERENCES meal_plans(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

-- User can only see/modify their own tasks
CREATE POLICY tasks_user_policy ON tasks
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_user_due ON tasks(user_id, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_user_completed ON tasks(user_id, completed);

-- Add comments
COMMENT ON TABLE tasks IS 'Transient task list for prep work, reminders, shopping errands';
COMMENT ON COLUMN tasks.category IS 'Task type: prep (cooking prep), shopping (errands), cleanup, other';
COMMENT ON COLUMN tasks.recipe_id IS 'Optional link to related recipe';
COMMENT ON COLUMN tasks.meal_plan_id IS 'Optional link to related meal plan';

