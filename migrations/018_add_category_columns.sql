-- Add category columns to user data tables for denormalized filtering
-- Run this BEFORE running the backfill script

-- Inventory: track pantry item categories
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS category TEXT;

-- Shopping list: track item categories for grouping
ALTER TABLE shopping_list ADD COLUMN IF NOT EXISTS category TEXT;

-- Recipe ingredients: track ingredient categories
ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS category TEXT;

-- Create indexes for category filtering
CREATE INDEX IF NOT EXISTS idx_inventory_category ON inventory(category);
CREATE INDEX IF NOT EXISTS idx_shopping_list_category ON shopping_list(category);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_category ON recipe_ingredients(category);

-- Note: The backfill script will populate these columns when linking ingredient_id

