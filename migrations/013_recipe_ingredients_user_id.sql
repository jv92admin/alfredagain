-- Migration 013: Add user_id to recipe_ingredients
-- Makes recipe_ingredients a user-owned table for simpler CRUD operations
-- (no need to first read recipe IDs to delete all ingredients)

-- ============================================================================
-- 1. Add user_id column
-- ============================================================================

ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- ============================================================================
-- 2. Backfill from parent recipes table
-- ============================================================================

UPDATE recipe_ingredients ri
SET user_id = r.user_id
FROM recipes r
WHERE ri.recipe_id = r.id
AND ri.user_id IS NULL;

-- ============================================================================
-- 3. Make user_id NOT NULL (after backfill)
-- ============================================================================

ALTER TABLE recipe_ingredients ALTER COLUMN user_id SET NOT NULL;

-- ============================================================================
-- 4. Add index for user_id queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_user ON recipe_ingredients(user_id);

-- ============================================================================
-- 5. Enable RLS (if not already) and add user policy
-- ============================================================================

ALTER TABLE recipe_ingredients ENABLE ROW LEVEL SECURITY;

-- Drop old policy if exists
DROP POLICY IF EXISTS recipe_ingredients_user_policy ON recipe_ingredients;

-- User can only see/modify their own recipe ingredients
CREATE POLICY recipe_ingredients_user_policy ON recipe_ingredients
    FOR ALL
    USING (true)
    WITH CHECK (user_id IS NOT NULL);

-- ============================================================================
-- 6. Add comment
-- ============================================================================

COMMENT ON COLUMN recipe_ingredients.user_id IS 'Owner of the recipe - denormalized for simpler CRUD operations';

