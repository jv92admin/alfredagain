-- =============================================================================
-- Migration 017: Semantic Matching Functions
-- =============================================================================
-- 
-- This migration adds semantic (vector-based) matching functions for ingredients
-- and recipes. Uses pgvector for cosine similarity search on embeddings.
--
-- Prerequisites: 
-- - pgvector extension enabled (done in 001_core_tables.sql)
-- - Embeddings populated via scripts/generate_embeddings.py
-- =============================================================================

-- =============================================================================
-- Semantic Match Function for Ingredients
-- =============================================================================
-- Find ingredients semantically similar to a query embedding

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
) AS $$
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
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- Semantic Match Function for Recipes
-- =============================================================================
-- Find recipes semantically similar to a query embedding
-- Useful for "hearty dinner", "quick breakfast", etc.

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
) AS $$
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
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- Combined Ingredient Lookup Function
-- =============================================================================
-- Chains: exact → fuzzy → semantic (if embedding provided)
-- Returns best match with match type indicator

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
) AS $$
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
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON FUNCTION match_ingredient_semantic IS 
    'Find ingredients by vector similarity. Requires embeddings to be populated.';

COMMENT ON FUNCTION match_recipe_semantic IS 
    'Find recipes by vector similarity. Useful for semantic search like "quick breakfast".';

COMMENT ON FUNCTION lookup_ingredient IS 
    'Combined lookup: exact → fuzzy → semantic. Returns best match with type indicator.';

