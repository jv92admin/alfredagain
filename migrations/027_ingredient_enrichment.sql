-- Migration 027: Ingredient Enrichment
-- Adds parent_category, family, cuisines, and tier columns to ingredients table
-- Adds assumed_staples to preferences table for user-confirmed staples

-- New columns on ingredients table
-- NOTE: family is nullable initially; NOT NULL added in migration 028 after cleanup
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS parent_category TEXT NOT NULL DEFAULT 'pantry';
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS family TEXT DEFAULT '';
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS cuisines TEXT[] DEFAULT '{}';
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS tier INTEGER DEFAULT 2;

-- Constraints
ALTER TABLE ingredients ADD CONSTRAINT chk_parent_category
  CHECK (parent_category IN (
    'produce', 'protein', 'dairy', 'grains',
    'pantry', 'spices', 'baking', 'specialty'
  ));
ALTER TABLE ingredients ADD CONSTRAINT chk_tier CHECK (tier IN (1, 2, 3));

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_ingredients_parent_category ON ingredients(parent_category);
CREATE INDEX IF NOT EXISTS idx_ingredients_family ON ingredients(family);
CREATE INDEX IF NOT EXISTS idx_ingredients_cuisines ON ingredients USING GIN(cuisines);
CREATE INDEX IF NOT EXISTS idx_ingredients_tier ON ingredients(tier);

-- User staples (preferences table)
-- Stores UUIDs of ingredients the user always keeps stocked
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS assumed_staples UUID[] DEFAULT '{}';
