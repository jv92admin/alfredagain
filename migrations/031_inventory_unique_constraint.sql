-- Migration 031: Add unique constraint on inventory(user_id, ingredient_id)
--
-- Enables upsert for onboarding inventory seeding.
-- Postgres treats NULLs as distinct in unique constraints, so rows with
-- ingredient_id IS NULL are unaffected.

-- Deduplicate existing rows: keep the one with the latest updated_at per
-- (user_id, ingredient_id) pair. Uses ctid to break ties when timestamps match.
DELETE FROM inventory
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, ingredient_id
                   ORDER BY updated_at DESC, created_at DESC, id DESC
               ) AS rn
        FROM inventory
        WHERE ingredient_id IS NOT NULL
    ) ranked
    WHERE rn > 1
);

ALTER TABLE inventory
  ADD CONSTRAINT inventory_user_ingredient_unique
  UNIQUE (user_id, ingredient_id);
