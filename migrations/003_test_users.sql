-- =============================================================================
-- Alfred V2 - Test Users for Alpha Testing
-- =============================================================================
-- Simple hardcoded passwords for buddy testing
-- Will be replaced with proper OAuth later

-- Add password_hash column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT;

-- Test users with simple passwords (bcrypt hashed)
-- Password for all: 'alfred123'
-- Generated with: python -c "import bcrypt; print(bcrypt.hashpw(b'alfred123', bcrypt.gensalt(12)).decode())"

-- Dev user (update existing)
UPDATE users 
SET password_hash = '$2b$12$M1Rt2GkHdqEeaXWwD9pDgOwtYdbkWAzjhiNnrWn9DXCkZ/cvHdbCC',
    display_name = 'Dev User'
WHERE id = '00000000-0000-0000-0000-000000000001';

-- Test user 1: Alice
INSERT INTO users (id, email, display_name, password_hash)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    'alice@test.local',
    'Alice',
    '$2b$12$M1Rt2GkHdqEeaXWwD9pDgOwtYdbkWAzjhiNnrWn9DXCkZ/cvHdbCC'
)
ON CONFLICT (id) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    display_name = EXCLUDED.display_name;

-- Test user 2: Bob
INSERT INTO users (id, email, display_name, password_hash)
VALUES (
    '00000000-0000-0000-0000-000000000003',
    'bob@test.local',
    'Bob',
    '$2b$12$M1Rt2GkHdqEeaXWwD9pDgOwtYdbkWAzjhiNnrWn9DXCkZ/cvHdbCC'
)
ON CONFLICT (id) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    display_name = EXCLUDED.display_name;

-- Test user 3: Carol
INSERT INTO users (id, email, display_name, password_hash)
VALUES (
    '00000000-0000-0000-0000-000000000004',
    'carol@test.local',
    'Carol',
    '$2b$12$M1Rt2GkHdqEeaXWwD9pDgOwtYdbkWAzjhiNnrWn9DXCkZ/cvHdbCC'
)
ON CONFLICT (id) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    display_name = EXCLUDED.display_name;

-- Create preferences for new test users
INSERT INTO preferences (user_id, cooking_skill_level, household_size)
VALUES 
    ('00000000-0000-0000-0000-000000000002', 'beginner', 1),
    ('00000000-0000-0000-0000-000000000003', 'intermediate', 2),
    ('00000000-0000-0000-0000-000000000004', 'advanced', 4)
ON CONFLICT (user_id) DO NOTHING;

