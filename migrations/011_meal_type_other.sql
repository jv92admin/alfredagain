-- Migration 011: Replace meal_type 'prep' with 'other'
-- Reason: Tasks are now a separate subdomain. 
-- Meal plans are for cooking sessions, 'other' covers experiments/stock making
-- Run this migration in Supabase SQL Editor

-- ============================================================================
-- 1. Drop old constraint FIRST (so we can use 'other')
-- ============================================================================
ALTER TABLE meal_plans DROP CONSTRAINT IF EXISTS meal_plans_meal_type_check;

-- ============================================================================
-- 2. Update existing 'prep' entries to 'other'
-- ============================================================================
UPDATE meal_plans SET meal_type = 'other' WHERE meal_type = 'prep';

-- ============================================================================
-- 3. Add new constraint with 'other'
-- ============================================================================
ALTER TABLE meal_plans ADD CONSTRAINT meal_plans_meal_type_check 
    CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'other'));

COMMENT ON COLUMN meal_plans.meal_type IS 'Type of meal: breakfast, lunch, dinner, snack, or other (for experiments, stock making, etc.)';

