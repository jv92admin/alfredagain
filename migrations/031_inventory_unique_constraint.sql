-- Migration 031: Add unique constraint on inventory(user_id, ingredient_id)
--
-- Enables upsert for onboarding inventory seeding.
-- Postgres treats NULLs as distinct in unique constraints, so rows with
-- ingredient_id IS NULL are unaffected.

-- Deduplicate any existing rows before adding constraint
-- (keeps the row with the latest updated_at)
DELETE FROM inventory a
USING inventory b
WHERE a.user_id = b.user_id
  AND a.ingredient_id = b.ingredient_id
  AND a.ingredient_id IS NOT NULL
  AND a.updated_at < b.updated_at;

ALTER TABLE inventory
  ADD CONSTRAINT inventory_user_ingredient_unique
  UNIQUE (user_id, ingredient_id);
