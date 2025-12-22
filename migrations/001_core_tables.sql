-- =============================================================================
-- Alfred V2 - Core Database Schema
-- =============================================================================
-- Run this migration in Supabase SQL Editor
-- Make sure to enable pgvector extension first!

-- Enable pgvector extension (run this first in Supabase Dashboard > Database > Extensions)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- CORE ENTITIES
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Master ingredient list (seeded from public APIs, enriched over time)
CREATE TABLE IF NOT EXISTS ingredients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    aliases TEXT[] DEFAULT '{}',
    category TEXT,
    default_unit TEXT,
    nutrition_per_100g JSONB,
    flavor_compounds TEXT[],
    embedding VECTOR(1536),
    is_system BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User's actual inventory
CREATE TABLE IF NOT EXISTS inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ingredient_id UUID REFERENCES ingredients(id),
    name TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    location TEXT,
    expiry_date DATE,
    purchase_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recipes
CREATE TABLE IF NOT EXISTS recipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    cuisine TEXT,
    difficulty TEXT,
    prep_time_minutes INT,
    cook_time_minutes INT,
    servings INT,
    instructions TEXT[] NOT NULL,
    tags TEXT[] DEFAULT '{}',
    source_url TEXT,
    embedding VECTOR(1536),
    is_system BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recipe ingredients junction
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipe_id UUID REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_id UUID REFERENCES ingredients(id),
    name TEXT NOT NULL,
    quantity NUMERIC,
    unit TEXT,
    notes TEXT,
    is_optional BOOLEAN DEFAULT false
);

-- Meal plans
CREATE TABLE IF NOT EXISTS meal_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    meal_type TEXT NOT NULL,
    recipe_id UUID REFERENCES recipes(id),
    notes TEXT,
    servings INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Shopping list
CREATE TABLE IF NOT EXISTS shopping_list (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ingredient_id UUID REFERENCES ingredients(id),
    name TEXT NOT NULL,
    quantity NUMERIC,
    unit TEXT,
    category TEXT,
    is_purchased BOOLEAN DEFAULT false,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User preferences
CREATE TABLE IF NOT EXISTS preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    dietary_restrictions TEXT[] DEFAULT '{}',
    allergies TEXT[] DEFAULT '{}',
    favorite_cuisines TEXT[] DEFAULT '{}',
    disliked_ingredients TEXT[] DEFAULT '{}',
    cooking_skill_level TEXT DEFAULT 'intermediate',
    household_size INT DEFAULT 1,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Flavor preferences
CREATE TABLE IF NOT EXISTS flavor_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ingredient_id UUID REFERENCES ingredients(id),
    preference_score NUMERIC DEFAULT 0,
    times_used INT DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, ingredient_id)
);

-- Conversation memory
CREATE TABLE IF NOT EXISTS conversation_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    memory_type TEXT,
    embedding VECTOR(1536),
    metadata JSONB DEFAULT '{}',
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Vector indexes for semantic search
CREATE INDEX IF NOT EXISTS idx_ingredients_embedding ON ingredients 
    USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_recipes_embedding ON recipes 
    USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_conversation_memory_embedding ON conversation_memory 
    USING ivfflat (embedding vector_cosine_ops);

-- Standard indexes
CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id);
CREATE INDEX IF NOT EXISTS idx_recipes_user ON recipes(user_id);
CREATE INDEX IF NOT EXISTS idx_meal_plans_user_date ON meal_plans(user_id, date);
CREATE INDEX IF NOT EXISTS idx_shopping_list_user ON shopping_list(user_id);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Auto-create missing ingredients when adding recipes
CREATE OR REPLACE FUNCTION auto_create_ingredients()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO ingredients (name, is_system)
    SELECT DISTINCT ri.name, false
    FROM recipe_ingredients ri
    WHERE ri.recipe_id = NEW.id
      AND NOT EXISTS (SELECT 1 FROM ingredients i WHERE i.name = ri.name)
    ON CONFLICT (name) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_auto_create_ingredients ON recipes;
CREATE TRIGGER trigger_auto_create_ingredients
    AFTER INSERT ON recipes
    FOR EACH ROW
    EXECUTE FUNCTION auto_create_ingredients();

-- =============================================================================
-- DEV USER (for development)
-- =============================================================================

INSERT INTO users (id, email)
VALUES ('00000000-0000-0000-0000-000000000001', 'dev@alfred.local')
ON CONFLICT (id) DO NOTHING;

INSERT INTO preferences (user_id, cooking_skill_level, household_size)
VALUES ('00000000-0000-0000-0000-000000000001', 'intermediate', 2)
ON CONFLICT (user_id) DO NOTHING;

