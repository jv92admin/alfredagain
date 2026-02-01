-- Migration: Add notes column to inventory
-- Useful for color variants ("red"), state ("opened", "half used"),
-- source ("Costco"), and qualifiers the LLM naturally wants to track.

ALTER TABLE inventory ADD COLUMN IF NOT EXISTS notes text;
