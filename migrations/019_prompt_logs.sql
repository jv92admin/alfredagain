-- Prompt Logs Table
-- Stores LLM prompts and responses for debugging online sessions
-- Auto-cleans old sessions to save space

CREATE TABLE IF NOT EXISTS prompt_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,           -- e.g., "20260104_160725"
    user_id UUID REFERENCES users(id),  -- Optional: tie to user for filtering
    call_number INTEGER NOT NULL,       -- Order within session (1, 2, 3...)
    node TEXT NOT NULL,                 -- router, understand, think, act, reply
    model TEXT NOT NULL,                -- gpt-4.1-mini, gpt-4.1, etc.
    response_model TEXT,                -- Pydantic model name
    config JSONB,                       -- reasoning_effort, verbosity, etc.
    system_prompt TEXT,                 -- Full system prompt
    user_prompt TEXT,                   -- Full user prompt
    response JSONB,                     -- Parsed response
    error TEXT,                         -- Error message if failed
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast session lookups
CREATE INDEX IF NOT EXISTS idx_prompt_logs_session ON prompt_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_prompt_logs_created ON prompt_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_prompt_logs_user ON prompt_logs(user_id);

-- Function to cleanup old sessions (keep last N)
CREATE OR REPLACE FUNCTION cleanup_old_prompt_logs(keep_sessions INTEGER DEFAULT 4)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
    cutoff_session TEXT;
BEGIN
    -- Find the Nth most recent session
    SELECT session_id INTO cutoff_session
    FROM (
        SELECT DISTINCT session_id 
        FROM prompt_logs 
        ORDER BY session_id DESC 
        LIMIT keep_sessions
    ) recent
    ORDER BY session_id ASC
    LIMIT 1;
    
    -- Delete everything older than that session
    IF cutoff_session IS NOT NULL THEN
        DELETE FROM prompt_logs WHERE session_id < cutoff_session;
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
    ELSE
        deleted_count := 0;
    END IF;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Comment explaining usage
COMMENT ON TABLE prompt_logs IS 'Stores LLM prompts for debugging. Call cleanup_old_prompt_logs(4) periodically.';

