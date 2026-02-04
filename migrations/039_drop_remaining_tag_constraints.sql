-- Migration 039: Drop remaining recipe tag constraints
-- valid_flavor_tags dropped in 038, valid_equipment_tags dropped in 023
-- This is a stopgap while the prompt fix rolls out to prevent DB errors

ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_occasions;
ALTER TABLE recipes DROP CONSTRAINT IF EXISTS valid_health_tags;
