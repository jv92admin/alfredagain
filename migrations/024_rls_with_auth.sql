-- =============================================================================
-- Migration 024: Proper RLS with Supabase Auth (auth.uid())
-- =============================================================================
-- This migration replaces the permissive RLS policies with proper auth.uid() checks.
-- Requires Supabase Auth to be configured with Google OAuth.
--
-- IMPORTANT: Run this AFTER enabling Google OAuth in Supabase Dashboard.
-- =============================================================================

-- =============================================================================
-- 1. Sync auth.users to public.users (trigger for new sign-ups)
-- =============================================================================

-- Function to create public.users record when auth.users is created
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, display_name, created_at)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1)),
        NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        display_name = COALESCE(EXCLUDED.display_name, public.users.display_name);
    
    -- Also create default preferences for new users
    INSERT INTO public.preferences (user_id, cooking_skill_level, household_size)
    VALUES (NEW.id, 'intermediate', 1)
    ON CONFLICT (user_id) DO NOTHING;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger on auth.users insert
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- =============================================================================
-- 2. Update users table to allow auth.uid() as primary key
-- =============================================================================

-- Ensure users table can handle Supabase Auth UUIDs
-- (Already UUID, so no schema change needed)

-- =============================================================================
-- 3. RLS Policies for all user-owned tables
-- =============================================================================

-- -----------------------------------------------------------------------------
-- inventory
-- -----------------------------------------------------------------------------
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS inventory_user_policy ON inventory;
DROP POLICY IF EXISTS inventory_select_policy ON inventory;
DROP POLICY IF EXISTS inventory_insert_policy ON inventory;
DROP POLICY IF EXISTS inventory_update_policy ON inventory;
DROP POLICY IF EXISTS inventory_delete_policy ON inventory;

CREATE POLICY inventory_select_policy ON inventory
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY inventory_insert_policy ON inventory
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY inventory_update_policy ON inventory
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY inventory_delete_policy ON inventory
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- recipes
-- -----------------------------------------------------------------------------
ALTER TABLE recipes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recipes_user_policy ON recipes;
DROP POLICY IF EXISTS recipes_select_policy ON recipes;
DROP POLICY IF EXISTS recipes_insert_policy ON recipes;
DROP POLICY IF EXISTS recipes_update_policy ON recipes;
DROP POLICY IF EXISTS recipes_delete_policy ON recipes;

-- Users can see their own recipes AND system recipes
CREATE POLICY recipes_select_policy ON recipes
    FOR SELECT USING (user_id = (select auth.uid()) OR is_system = true);
CREATE POLICY recipes_insert_policy ON recipes
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY recipes_update_policy ON recipes
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY recipes_delete_policy ON recipes
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- recipe_ingredients
-- -----------------------------------------------------------------------------
ALTER TABLE recipe_ingredients ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recipe_ingredients_user_policy ON recipe_ingredients;
DROP POLICY IF EXISTS recipe_ingredients_select_policy ON recipe_ingredients;
DROP POLICY IF EXISTS recipe_ingredients_insert_policy ON recipe_ingredients;
DROP POLICY IF EXISTS recipe_ingredients_update_policy ON recipe_ingredients;
DROP POLICY IF EXISTS recipe_ingredients_delete_policy ON recipe_ingredients;

CREATE POLICY recipe_ingredients_select_policy ON recipe_ingredients
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY recipe_ingredients_insert_policy ON recipe_ingredients
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY recipe_ingredients_update_policy ON recipe_ingredients
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY recipe_ingredients_delete_policy ON recipe_ingredients
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- meal_plans
-- -----------------------------------------------------------------------------
ALTER TABLE meal_plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS meal_plans_user_policy ON meal_plans;
DROP POLICY IF EXISTS meal_plans_select_policy ON meal_plans;
DROP POLICY IF EXISTS meal_plans_insert_policy ON meal_plans;
DROP POLICY IF EXISTS meal_plans_update_policy ON meal_plans;
DROP POLICY IF EXISTS meal_plans_delete_policy ON meal_plans;

CREATE POLICY meal_plans_select_policy ON meal_plans
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY meal_plans_insert_policy ON meal_plans
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY meal_plans_update_policy ON meal_plans
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY meal_plans_delete_policy ON meal_plans
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- shopping_list
-- -----------------------------------------------------------------------------
ALTER TABLE shopping_list ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS shopping_list_user_policy ON shopping_list;
DROP POLICY IF EXISTS shopping_list_select_policy ON shopping_list;
DROP POLICY IF EXISTS shopping_list_insert_policy ON shopping_list;
DROP POLICY IF EXISTS shopping_list_update_policy ON shopping_list;
DROP POLICY IF EXISTS shopping_list_delete_policy ON shopping_list;

CREATE POLICY shopping_list_select_policy ON shopping_list
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY shopping_list_insert_policy ON shopping_list
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY shopping_list_update_policy ON shopping_list
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY shopping_list_delete_policy ON shopping_list
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- preferences
-- -----------------------------------------------------------------------------
ALTER TABLE preferences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS preferences_user_policy ON preferences;
DROP POLICY IF EXISTS preferences_select_policy ON preferences;
DROP POLICY IF EXISTS preferences_insert_policy ON preferences;
DROP POLICY IF EXISTS preferences_update_policy ON preferences;
DROP POLICY IF EXISTS preferences_delete_policy ON preferences;

CREATE POLICY preferences_select_policy ON preferences
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY preferences_insert_policy ON preferences
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY preferences_update_policy ON preferences
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY preferences_delete_policy ON preferences
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- flavor_preferences
-- -----------------------------------------------------------------------------
ALTER TABLE flavor_preferences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS flavor_preferences_user_policy ON flavor_preferences;
DROP POLICY IF EXISTS flavor_preferences_select_policy ON flavor_preferences;
DROP POLICY IF EXISTS flavor_preferences_insert_policy ON flavor_preferences;
DROP POLICY IF EXISTS flavor_preferences_update_policy ON flavor_preferences;
DROP POLICY IF EXISTS flavor_preferences_delete_policy ON flavor_preferences;

CREATE POLICY flavor_preferences_select_policy ON flavor_preferences
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY flavor_preferences_insert_policy ON flavor_preferences
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY flavor_preferences_update_policy ON flavor_preferences
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY flavor_preferences_delete_policy ON flavor_preferences
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- conversation_memory
-- -----------------------------------------------------------------------------
ALTER TABLE conversation_memory ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversation_memory_user_policy ON conversation_memory;
DROP POLICY IF EXISTS conversation_memory_select_policy ON conversation_memory;
DROP POLICY IF EXISTS conversation_memory_insert_policy ON conversation_memory;
DROP POLICY IF EXISTS conversation_memory_update_policy ON conversation_memory;
DROP POLICY IF EXISTS conversation_memory_delete_policy ON conversation_memory;

CREATE POLICY conversation_memory_select_policy ON conversation_memory
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY conversation_memory_insert_policy ON conversation_memory
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY conversation_memory_update_policy ON conversation_memory
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY conversation_memory_delete_policy ON conversation_memory
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- tasks
-- -----------------------------------------------------------------------------
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tasks_user_policy ON tasks;
DROP POLICY IF EXISTS tasks_select_policy ON tasks;
DROP POLICY IF EXISTS tasks_insert_policy ON tasks;
DROP POLICY IF EXISTS tasks_update_policy ON tasks;
DROP POLICY IF EXISTS tasks_delete_policy ON tasks;

CREATE POLICY tasks_select_policy ON tasks
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY tasks_insert_policy ON tasks
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY tasks_update_policy ON tasks
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY tasks_delete_policy ON tasks
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- cooking_log
-- -----------------------------------------------------------------------------
ALTER TABLE cooking_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cooking_log_user_policy ON cooking_log;
DROP POLICY IF EXISTS cooking_log_select_policy ON cooking_log;
DROP POLICY IF EXISTS cooking_log_insert_policy ON cooking_log;
DROP POLICY IF EXISTS cooking_log_update_policy ON cooking_log;
DROP POLICY IF EXISTS cooking_log_delete_policy ON cooking_log;

CREATE POLICY cooking_log_select_policy ON cooking_log
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY cooking_log_insert_policy ON cooking_log
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY cooking_log_update_policy ON cooking_log
    FOR UPDATE USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY cooking_log_delete_policy ON cooking_log
    FOR DELETE USING (user_id = (select auth.uid()));

-- =============================================================================
-- 4. Public tables (no user_id, accessible to all authenticated users)
-- =============================================================================

-- ingredients - system-wide catalog, readable by all
ALTER TABLE ingredients ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ingredients_select_policy ON ingredients;
DROP POLICY IF EXISTS ingredients_insert_policy ON ingredients;

-- Anyone authenticated can read ingredients
CREATE POLICY ingredients_select_policy ON ingredients
    FOR SELECT USING ((select auth.uid()) IS NOT NULL);

-- Only allow insert if authenticated (for user-created ingredients)
CREATE POLICY ingredients_insert_policy ON ingredients
    FOR INSERT WITH CHECK ((select auth.uid()) IS NOT NULL);

-- =============================================================================
-- 5. Grant necessary permissions to authenticated role
-- =============================================================================

-- Ensure authenticated users can access the tables
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- =============================================================================
-- 6. Fix SECURITY DEFINER views to respect RLS
-- =============================================================================

-- Recreate user_top_ingredients view with SECURITY INVOKER
-- This ensures the view respects RLS policies of the querying user
DROP VIEW IF EXISTS user_top_ingredients;
CREATE VIEW user_top_ingredients 
WITH (security_invoker = true) AS
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

COMMENT ON VIEW user_top_ingredients IS 'Ranked list of most-used ingredients per user (respects RLS)';

-- =============================================================================
-- Note: After running this migration, the app MUST use authenticated clients
-- (with JWT tokens) instead of service role key for user operations.
-- Service role key should only be used for background/admin operations.
-- =============================================================================
