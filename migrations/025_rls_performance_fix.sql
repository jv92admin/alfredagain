-- =============================================================================
-- Migration 025: RLS Performance Fix + Additional Security Fixes
-- =============================================================================
-- Fixes:
-- 1. Performance: wrap auth.uid() in (select auth.uid()) 
-- 2. RLS for prompt_logs table
-- 3. RLS for users table
-- 4. Fix functions with mutable search_path
-- =============================================================================

-- -----------------------------------------------------------------------------
-- inventory
-- -----------------------------------------------------------------------------
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
DROP POLICY IF EXISTS recipes_select_policy ON recipes;
DROP POLICY IF EXISTS recipes_insert_policy ON recipes;
DROP POLICY IF EXISTS recipes_update_policy ON recipes;
DROP POLICY IF EXISTS recipes_delete_policy ON recipes;

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

-- -----------------------------------------------------------------------------
-- ingredients (public table - auth check only)
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS ingredients_select_policy ON ingredients;
DROP POLICY IF EXISTS ingredients_insert_policy ON ingredients;

CREATE POLICY ingredients_select_policy ON ingredients
    FOR SELECT USING ((select auth.uid()) IS NOT NULL);
CREATE POLICY ingredients_insert_policy ON ingredients
    FOR INSERT WITH CHECK ((select auth.uid()) IS NOT NULL);

-- -----------------------------------------------------------------------------
-- Fix SECURITY DEFINER view (if not already done)
-- -----------------------------------------------------------------------------
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
-- Additional Security Fixes
-- =============================================================================

-- -----------------------------------------------------------------------------
-- prompt_logs - RLS (users can only see their own logs)
-- -----------------------------------------------------------------------------
ALTER TABLE prompt_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS prompt_logs_select_policy ON prompt_logs;
DROP POLICY IF EXISTS prompt_logs_insert_policy ON prompt_logs;
DROP POLICY IF EXISTS prompt_logs_delete_policy ON prompt_logs;

CREATE POLICY prompt_logs_select_policy ON prompt_logs
    FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY prompt_logs_insert_policy ON prompt_logs
    FOR INSERT WITH CHECK (user_id = (select auth.uid()));
CREATE POLICY prompt_logs_delete_policy ON prompt_logs
    FOR DELETE USING (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- users - RLS (users can only see/edit their own record)
-- -----------------------------------------------------------------------------
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_select_policy ON users;
DROP POLICY IF EXISTS users_update_policy ON users;

-- Users can read their own record
CREATE POLICY users_select_policy ON users
    FOR SELECT USING (id = (select auth.uid()));
-- Users can update their own record
CREATE POLICY users_update_policy ON users
    FOR UPDATE USING (id = (select auth.uid())) WITH CHECK (id = (select auth.uid()));
-- Note: INSERT is handled by trigger from auth.users, not direct insert

-- -----------------------------------------------------------------------------
-- Fix functions with mutable search_path
-- -----------------------------------------------------------------------------

-- Fix get_table_columns function
CREATE OR REPLACE FUNCTION get_table_columns(p_table_name text)
RETURNS TABLE (
    column_name text,
    data_type text,
    is_nullable text,
    column_default text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT 
        c.column_name::text,
        c.data_type::text,
        c.is_nullable::text,
        c.column_default::text
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name = p_table_name
    ORDER BY c.ordinal_position;
$$;

-- Fix auto_create_ingredients function
CREATE OR REPLACE FUNCTION auto_create_ingredients()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    INSERT INTO ingredients (name, is_system)
    SELECT DISTINCT ri.name, false
    FROM recipe_ingredients ri
    WHERE ri.recipe_id = NEW.id
      AND NOT EXISTS (SELECT 1 FROM ingredients i WHERE i.name = ri.name)
    ON CONFLICT (name) DO NOTHING;
    RETURN NEW;
END;
$$;

-- Fix cleanup_old_prompt_logs function
CREATE OR REPLACE FUNCTION cleanup_old_prompt_logs(keep_sessions INTEGER DEFAULT 4)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    deleted_count INTEGER;
    cutoff_session TEXT;
BEGIN
    SELECT session_id INTO cutoff_session
    FROM (
        SELECT DISTINCT session_id 
        FROM prompt_logs 
        ORDER BY session_id DESC 
        LIMIT keep_sessions
    ) recent
    ORDER BY session_id ASC
    LIMIT 1;
    
    IF cutoff_session IS NOT NULL THEN
        DELETE FROM prompt_logs WHERE session_id < cutoff_session;
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
    ELSE
        deleted_count := 0;
    END IF;
    
    RETURN deleted_count;
END;
$$;

-- Fix handle_new_user function (from migration 024)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
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
    
    INSERT INTO public.preferences (user_id, cooking_skill_level, household_size)
    VALUES (NEW.id, 'intermediate', 1)
    ON CONFLICT (user_id) DO NOTHING;
    
    RETURN NEW;
END;
$$;

-- -----------------------------------------------------------------------------
-- Fix remaining functions with mutable search_path
-- -----------------------------------------------------------------------------

-- Fix match_ingredient_fuzzy
CREATE OR REPLACE FUNCTION match_ingredient_fuzzy(
    query TEXT,
    threshold FLOAT DEFAULT 0.6,
    limit_n INT DEFAULT 5
)
RETURNS TABLE(
    id UUID,
    name TEXT,
    category TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (i.id)
        i.id,
        i.name,
        i.category,
        GREATEST(
            similarity(lower(i.name), lower(query))::FLOAT,
            COALESCE((
                SELECT MAX(similarity(lower(a), lower(query))::FLOAT)
                FROM unnest(i.aliases) AS a
            ), 0::FLOAT)
        )::FLOAT AS sim
    FROM ingredients i
    WHERE 
        similarity(lower(i.name), lower(query)) >= threshold
        OR EXISTS (
            SELECT 1 FROM unnest(i.aliases) AS a 
            WHERE similarity(lower(a), lower(query)) >= threshold
        )
    ORDER BY i.id, sim DESC
    LIMIT limit_n;
END;
$$;

-- Fix match_ingredient_exact
CREATE OR REPLACE FUNCTION match_ingredient_exact(
    query TEXT
)
RETURNS TABLE(
    id UUID,
    name TEXT,
    category TEXT
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT i.id, i.name, i.category
    FROM ingredients i
    WHERE 
        lower(i.name) = lower(query)
        OR lower(query) = ANY(SELECT lower(a) FROM unnest(i.aliases) AS a);
END;
$$;

-- Fix match_ingredient_semantic (from migration 017)
CREATE OR REPLACE FUNCTION match_ingredient_semantic(
    query_embedding VECTOR(1536),
    limit_n INT DEFAULT 5,
    max_distance FLOAT DEFAULT 0.5
)
RETURNS TABLE(
    id UUID,
    name TEXT,
    category TEXT,
    distance FLOAT
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        i.id,
        i.name,
        i.category,
        (i.embedding <=> query_embedding)::FLOAT AS dist
    FROM ingredients i
    WHERE i.embedding IS NOT NULL
      AND (i.embedding <=> query_embedding) <= max_distance
    ORDER BY i.embedding <=> query_embedding
    LIMIT limit_n;
END;
$$;

-- Fix match_recipe_semantic
CREATE OR REPLACE FUNCTION match_recipe_semantic(
    query_embedding VECTOR(1536),
    user_id_filter UUID DEFAULT NULL,
    limit_n INT DEFAULT 10,
    max_distance FLOAT DEFAULT 0.6
)
RETURNS TABLE(
    id UUID,
    name TEXT,
    cuisine TEXT,
    difficulty TEXT,
    distance FLOAT
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        r.id,
        r.name,
        r.cuisine,
        r.difficulty,
        (r.embedding <=> query_embedding)::FLOAT AS dist
    FROM recipes r
    WHERE r.embedding IS NOT NULL
      AND (r.embedding <=> query_embedding) <= max_distance
      AND (user_id_filter IS NULL OR r.user_id = user_id_filter)
    ORDER BY r.embedding <=> query_embedding
    LIMIT limit_n;
END;
$$;

-- Fix lookup_ingredient
CREATE OR REPLACE FUNCTION lookup_ingredient(
    query TEXT,
    fuzzy_threshold FLOAT DEFAULT 0.6,
    query_embedding VECTOR(1536) DEFAULT NULL
)
RETURNS TABLE(
    id UUID,
    name TEXT,
    category TEXT,
    match_type TEXT,
    confidence FLOAT
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    exact_result RECORD;
    fuzzy_result RECORD;
    semantic_result RECORD;
BEGIN
    -- 1. Try exact match first
    SELECT * INTO exact_result FROM match_ingredient_exact(query) LIMIT 1;
    IF FOUND THEN
        RETURN QUERY SELECT 
            exact_result.id, 
            exact_result.name, 
            exact_result.category,
            'exact'::TEXT,
            1.0::FLOAT;
        RETURN;
    END IF;
    
    -- 2. Try fuzzy match
    SELECT * INTO fuzzy_result FROM match_ingredient_fuzzy(query, fuzzy_threshold, 1);
    IF FOUND THEN
        RETURN QUERY SELECT 
            fuzzy_result.id, 
            fuzzy_result.name, 
            fuzzy_result.category,
            'fuzzy'::TEXT,
            fuzzy_result.similarity;
        RETURN;
    END IF;
    
    -- 3. Try semantic match (if embedding provided)
    IF query_embedding IS NOT NULL THEN
        SELECT * INTO semantic_result FROM match_ingredient_semantic(query_embedding, 1, 0.5);
        IF FOUND THEN
            RETURN QUERY SELECT 
                semantic_result.id, 
                semantic_result.name, 
                semantic_result.category,
                'semantic'::TEXT,
                (1.0 - semantic_result.distance)::FLOAT;
            RETURN;
        END IF;
    END IF;
    
    -- No match found
    RETURN;
END;
$$;

-- Fix update_flavor_preferences
CREATE OR REPLACE FUNCTION update_flavor_preferences()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
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
$$;

-- -----------------------------------------------------------------------------
-- Note about pg_trgm extension
-- -----------------------------------------------------------------------------
-- The pg_trgm extension warning can be ignored for now.
-- Moving it requires recreating indexes, which is disruptive.
-- It's a low-severity issue and the extension is safe in public schema.
