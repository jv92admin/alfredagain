-- Migration 028: Add NOT NULL constraint to family column
-- Run this AFTER running cleanup_ingredients.py families to populate all family values

-- First, fix any remaining empty families (safety net)
UPDATE ingredients
SET family = name
WHERE family IS NULL OR family = '';

-- Remove the default empty string and add NOT NULL constraint
ALTER TABLE ingredients
ALTER COLUMN family SET NOT NULL,
ALTER COLUMN family DROP DEFAULT;
