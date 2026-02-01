-- Split household_size into household_adults / household_kids / household_babies.
-- This lets Alfred compute more accurate portions:
--   adults * 1.0 + kids * 0.5 + babies * 0.0

-- 1. Add new columns
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS household_adults INT DEFAULT 1;
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS household_kids INT DEFAULT 0;
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS household_babies INT DEFAULT 0;

-- 2. Migrate existing data
UPDATE preferences
SET household_adults = COALESCE(household_size, 1)
WHERE household_adults = 1 AND household_size IS NOT NULL AND household_size != 1;

-- 3. Drop old column
ALTER TABLE preferences DROP COLUMN IF EXISTS household_size;

-- 4. Update the auto-create-preferences trigger to use new column
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, display_name, created_at)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1)),
        NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        display_name = COALESCE(EXCLUDED.display_name, public.users.display_name);

    -- Create default preferences for new users
    INSERT INTO public.preferences (user_id, cooking_skill_level, household_adults)
    VALUES (NEW.id, 'intermediate', 1)
    ON CONFLICT (user_id) DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
