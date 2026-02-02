-- Migration 005: Add missing columns to dispatch_recommendations
-- Adds instrument_type and created_at columns

ALTER TABLE dispatch_recommendations
  ADD COLUMN IF NOT EXISTS instrument_type TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;

-- Set created_at to ts for existing rows
UPDATE dispatch_recommendations
SET created_at = ts
WHERE created_at IS NULL;
