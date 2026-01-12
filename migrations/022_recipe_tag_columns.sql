-- Migration: Replace generic tags with 4 specific tag columns
-- Run this in Supabase SQL editor

-- Add new columns
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS occasions text[];
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS health_tags text[];
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS flavor_tags text[];
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS equipment_tags text[];

-- Add check constraints for valid values
-- Drop existing constraints first (in case re-running)
ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_occasions;
ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_health_tags;
ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_flavor_tags;
ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_equipment_tags;

ALTER TABLE recipes ADD CONSTRAINT valid_occasions 
  CHECK (occasions IS NULL OR occasions <@ ARRAY['weeknight', 'batch-prep', 'hosting', 'weekend', 'comfort']::text[]);

ALTER TABLE recipes ADD CONSTRAINT valid_health_tags
  CHECK (health_tags IS NULL OR health_tags <@ ARRAY['high-protein', 'low-carb', 'vegetarian', 'vegan', 'light', 'gluten-free', 'dairy-free', 'keto']::text[]);

ALTER TABLE recipes ADD CONSTRAINT valid_flavor_tags
  CHECK (flavor_tags IS NULL OR flavor_tags <@ ARRAY['spicy', 'mild', 'savory', 'sweet', 'tangy', 'rich', 'light', 'umami']::text[]);

ALTER TABLE recipes ADD CONSTRAINT valid_equipment_tags
  CHECK (equipment_tags IS NULL OR equipment_tags <@ ARRAY['air-fryer', 'instant-pot', 'one-pot', 'one-pan', 'grill', 'no-cook', 'slow-cooker', 'oven', 'stovetop']::text[]);

-- Index for filtering
CREATE INDEX IF NOT EXISTS idx_recipes_occasions ON recipes USING GIN (occasions);
CREATE INDEX IF NOT EXISTS idx_recipes_health_tags ON recipes USING GIN (health_tags);
CREATE INDEX IF NOT EXISTS idx_recipes_flavor_tags ON recipes USING GIN (flavor_tags);
CREATE INDEX IF NOT EXISTS idx_recipes_equipment_tags ON recipes USING GIN (equipment_tags);

-- Note: Don't drop old tags column yet - keep for reference until data migrated
-- ALTER TABLE recipes DROP COLUMN IF EXISTS tags;
