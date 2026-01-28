-- Migration: 029_conversations_table.sql
-- Purpose: Persist conversation state in DB to survive deployments/restarts
-- Date: 2026-01-28

-- =============================================================================
-- Conversations Table
-- =============================================================================
-- Stores conversation state (recent_turns, session metadata).
-- One row per user. Updated on every chat turn.

CREATE TABLE IF NOT EXISTS conversations (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    state JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    title TEXT,
    is_archived BOOLEAN NOT NULL DEFAULT false
);

-- Index for finding stale/expired sessions
CREATE INDEX IF NOT EXISTS idx_conversations_last_active
    ON conversations(last_active_at);

-- Index for archived sessions (future use)
CREATE INDEX IF NOT EXISTS idx_conversations_archived
    ON conversations(is_archived) WHERE is_archived = true;

-- Auto-update last_active_at trigger
CREATE OR REPLACE FUNCTION update_conversations_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_active_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_conversations_timestamp ON conversations;
CREATE TRIGGER update_conversations_timestamp
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_conversations_timestamp();

-- RLS: Users can only access their own conversation
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY conversations_select_policy ON conversations
    FOR SELECT USING (user_id = (SELECT auth.uid()));

CREATE POLICY conversations_insert_policy ON conversations
    FOR INSERT WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY conversations_update_policy ON conversations
    FOR UPDATE USING (user_id = (SELECT auth.uid()));

CREATE POLICY conversations_delete_policy ON conversations
    FOR DELETE USING (user_id = (SELECT auth.uid()));


-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE conversations IS 'Stores conversation state for each user. Survives deployments/restarts.';
COMMENT ON COLUMN conversations.state IS 'Full conversation dict as JSONB (recent_turns, created_at, etc.)';
COMMENT ON COLUMN conversations.last_active_at IS 'Updated on every chat turn. Used for stale session detection.';
COMMENT ON COLUMN conversations.title IS 'Optional title for future multi-conversation support.';
COMMENT ON COLUMN conversations.is_archived IS 'Flag for archived conversations (future use).';
