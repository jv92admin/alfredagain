-- =============================================================================
-- Alfred V2 - Fix Foreign Key Cascades
-- =============================================================================
-- Problem: Deleting meal_plans or recipes with linked tasks causes FK errors
-- Solution: Change to ON DELETE SET NULL so tasks survive but lose the reference
-- Also fix meal_plans.recipe_id to SET NULL when recipe is deleted

-- =============================================================================
-- Fix tasks.meal_plan_id - SET NULL when meal plan is deleted
-- =============================================================================
ALTER TABLE tasks 
DROP CONSTRAINT IF EXISTS tasks_meal_plan_id_fkey;

ALTER TABLE tasks
ADD CONSTRAINT tasks_meal_plan_id_fkey 
FOREIGN KEY (meal_plan_id) 
REFERENCES meal_plans(id) 
ON DELETE SET NULL;

-- =============================================================================
-- Fix tasks.recipe_id - SET NULL when recipe is deleted
-- =============================================================================
ALTER TABLE tasks 
DROP CONSTRAINT IF EXISTS tasks_recipe_id_fkey;

ALTER TABLE tasks
ADD CONSTRAINT tasks_recipe_id_fkey 
FOREIGN KEY (recipe_id) 
REFERENCES recipes(id) 
ON DELETE SET NULL;

-- =============================================================================
-- Fix meal_plans.recipe_id - SET NULL when recipe is deleted
-- =============================================================================
ALTER TABLE meal_plans 
DROP CONSTRAINT IF EXISTS meal_plans_recipe_id_fkey;

ALTER TABLE meal_plans
ADD CONSTRAINT meal_plans_recipe_id_fkey 
FOREIGN KEY (recipe_id) 
REFERENCES recipes(id) 
ON DELETE SET NULL;

-- =============================================================================
-- Verify constraints
-- =============================================================================
-- You can verify with:
-- SELECT conname, confdeltype FROM pg_constraint WHERE conrelid = 'tasks'::regclass;
-- confdeltype: 'a' = no action, 'c' = cascade, 'n' = set null, 'd' = set default

