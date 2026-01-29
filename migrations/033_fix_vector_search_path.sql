-- Migration 033: Fix extension operator search_path
--
-- Migration 025 set search_path = public on all RPC functions, but the
-- pgvector <=> operator and pg_trgm similarity() live in the extensions
-- schema. This broke semantic search and fuzzy matching.

-- Fix match_ingredient_fuzzy (similarity() from pg_trgm is in extensions)
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
SET search_path = public, extensions
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

-- Fix match_ingredient_semantic
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
SET search_path = public, extensions
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
SET search_path = public, extensions
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
SET search_path = public, extensions
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
