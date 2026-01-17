-- Migration: Remove equipment_tags constraint
-- Equipment is too varied to normalize into an enum
-- Examples: air-fryer, instant-pot, sous-vide, blender, food-processor, grill, etc.
-- Let Act use freeform values that match user's actual equipment

ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_equipment_tags;

-- Note: Keep the column and index, just remove the value restriction
-- CREATE INDEX IF NOT EXISTS idx_recipes_equipment_tags ON recipes USING GIN (equipment_tags);
-- (already exists from migration 022)
