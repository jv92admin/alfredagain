-- =============================================================================
-- Migration 016: Enable pg_trgm for Fuzzy Matching
-- =============================================================================
-- 
-- This migration enables the pg_trgm extension for trigram-based fuzzy matching
-- on ingredient names and aliases. Used for typo correction and near-duplicate
-- detection in inventory, shopping_list, and recipe_ingredients tables.
--
-- IMPORTANT: Run this in Supabase Dashboard > SQL Editor
-- The extension may need to be enabled via Dashboard > Database > Extensions first
-- =============================================================================

-- Enable pg_trgm extension (for fuzzy string matching)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =============================================================================
-- Trigram Indexes on ingredients table
-- =============================================================================

-- Index on ingredient name for fuzzy search
CREATE INDEX IF NOT EXISTS idx_ingredients_name_trgm 
    ON ingredients USING gin (name gin_trgm_ops);

-- Note: Cannot create trigram index directly on aliases array because
-- array_to_string is not IMMUTABLE. Alias matching is handled in the
-- match_ingredient_fuzzy function by unnesting and checking each alias.

-- =============================================================================
-- Fuzzy Match Function
-- =============================================================================
-- Returns ingredients matching a query with trigram similarity
-- Searches both name and aliases, returns best matches above threshold

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
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (i.id)
        i.id,
        i.name,
        i.category,
        GREATEST(
            similarity(lower(i.name), lower(query))::FLOAT,
            -- Check similarity against each alias
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
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- Exact Match Function (includes aliases)
-- =============================================================================
-- Fast exact match on name or any alias (case-insensitive)

CREATE OR REPLACE FUNCTION match_ingredient_exact(
    query TEXT
)
RETURNS TABLE(
    id UUID,
    name TEXT,
    category TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT i.id, i.name, i.category
    FROM ingredients i
    WHERE 
        lower(i.name) = lower(query)
        OR lower(query) = ANY(SELECT lower(a) FROM unnest(i.aliases) AS a);
END;
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON FUNCTION match_ingredient_fuzzy IS 
    'Find ingredients matching query using trigram similarity. Searches name and aliases.';

COMMENT ON FUNCTION match_ingredient_exact IS 
    'Find ingredient by exact name or alias match (case-insensitive).';

