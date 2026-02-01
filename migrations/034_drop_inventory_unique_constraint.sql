-- Drop the (user_id, ingredient_id) unique constraint on inventory.
-- This was added in 031 for onboarding upsert convenience, but it prevents
-- legitimate multi-purchase scenarios (same ingredient bought on different
-- weeks with different expiry dates).

ALTER TABLE inventory
  DROP CONSTRAINT IF EXISTS inventory_user_ingredient_unique;
