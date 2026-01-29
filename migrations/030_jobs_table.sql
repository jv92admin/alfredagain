-- Migration 030: Jobs table for background agent execution
-- Phase 2.5: Job durability — responses survive client disconnects

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, complete, failed
    input JSONB NOT NULL,                    -- {message, mode, ui_changes}
    output JSONB,                            -- {response, active_context, log_dir}
    error TEXT,
    steps JSONB DEFAULT '[]',               -- Phase 3: step checkpointing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ             -- NULL = not yet seen by client
);

-- RLS
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY jobs_select ON jobs
    FOR SELECT USING (user_id = (SELECT auth.uid()));

CREATE POLICY jobs_insert ON jobs
    FOR INSERT WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY jobs_update ON jobs
    FOR UPDATE USING (user_id = (SELECT auth.uid()));

-- Indexes
CREATE INDEX idx_jobs_user_status ON jobs(user_id, status);

CREATE INDEX idx_jobs_user_unacked ON jobs(user_id)
    WHERE acknowledged_at IS NULL AND status IN ('running', 'complete');

CREATE INDEX idx_jobs_created ON jobs(created_at DESC);
