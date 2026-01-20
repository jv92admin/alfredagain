-- Migration: 026_onboarding_tables.sql
-- Purpose: Create tables for onboarding session state and final payload storage
-- Date: 2026-01-18

-- =============================================================================
-- Onboarding Sessions Table
-- =============================================================================
-- Stores in-progress onboarding state. Deleted when onboarding completes.

CREATE TABLE IF NOT EXISTS onboarding_sessions (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    state JSONB NOT NULL DEFAULT '{}',
    current_phase TEXT NOT NULL DEFAULT 'constraints',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for phase-based queries (e.g., finding abandoned sessions)
CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_phase 
    ON onboarding_sessions(current_phase);

-- Index for finding stale sessions
CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_updated 
    ON onboarding_sessions(updated_at);

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_onboarding_sessions_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_onboarding_sessions_timestamp ON onboarding_sessions;
CREATE TRIGGER update_onboarding_sessions_timestamp
    BEFORE UPDATE ON onboarding_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_onboarding_sessions_timestamp();

-- RLS: Users can only access their own session
ALTER TABLE onboarding_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY onboarding_sessions_select_policy ON onboarding_sessions
    FOR SELECT USING (user_id = (SELECT auth.uid()));

CREATE POLICY onboarding_sessions_insert_policy ON onboarding_sessions
    FOR INSERT WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY onboarding_sessions_update_policy ON onboarding_sessions
    FOR UPDATE USING (user_id = (SELECT auth.uid()));

CREATE POLICY onboarding_sessions_delete_policy ON onboarding_sessions
    FOR DELETE USING (user_id = (SELECT auth.uid()));


-- =============================================================================
-- Onboarding Data Table
-- =============================================================================
-- Stores completed onboarding payloads. Persists after onboarding for reference.

CREATE TABLE IF NOT EXISTS onboarding_data (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    payload JSONB NOT NULL DEFAULT '{}',
    version TEXT NOT NULL DEFAULT '1.0',
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-update timestamp trigger
DROP TRIGGER IF EXISTS update_onboarding_data_timestamp ON onboarding_data;
CREATE TRIGGER update_onboarding_data_timestamp
    BEFORE UPDATE ON onboarding_data
    FOR EACH ROW
    EXECUTE FUNCTION update_onboarding_sessions_timestamp();

-- RLS: Users can only access their own data
ALTER TABLE onboarding_data ENABLE ROW LEVEL SECURITY;

CREATE POLICY onboarding_data_select_policy ON onboarding_data
    FOR SELECT USING (user_id = (SELECT auth.uid()));

CREATE POLICY onboarding_data_insert_policy ON onboarding_data
    FOR INSERT WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY onboarding_data_update_policy ON onboarding_data
    FOR UPDATE USING (user_id = (SELECT auth.uid()));

CREATE POLICY onboarding_data_delete_policy ON onboarding_data
    FOR DELETE USING (user_id = (SELECT auth.uid()));


-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE onboarding_sessions IS 'Stores in-progress onboarding state. Deleted when onboarding completes.';
COMMENT ON COLUMN onboarding_sessions.state IS 'Serialized OnboardingState as JSONB';
COMMENT ON COLUMN onboarding_sessions.current_phase IS 'Current phase: constraints, pantry, ingredient_discovery, cuisine_selection, style_*, habits, preview, complete';

COMMENT ON TABLE onboarding_data IS 'Stores completed onboarding payloads for reference and future re-processing.';
COMMENT ON COLUMN onboarding_data.payload IS 'Full OnboardingPayload as JSONB - preferences, subdomain_guidance, stylistic_examples, etc.';
COMMENT ON COLUMN onboarding_data.version IS 'Onboarding spec version used to generate this payload';
