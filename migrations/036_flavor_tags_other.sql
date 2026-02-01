-- Migration: Add "other" to flavor_tags constraint as graceful fallback
-- This prevents constraint violations when LLM generates a flavor tag
-- that doesn't fit the existing categories.

ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_flavor_tags;
ALTER TABLE recipes ADD CONSTRAINT valid_flavor_tags
  CHECK (flavor_tags IS NULL OR flavor_tags <@ ARRAY['spicy','mild','savory','sweet','tangy','rich','light','umami','other']::text[]);
