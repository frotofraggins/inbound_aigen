-- Migration 015: Add option_symbol column to active_positions
-- Fixes Position Manager error when syncing from Alpaca
-- Date: 2026-01-30

BEGIN;

-- Add option_symbol column to active_positions table
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS option_symbol TEXT;

-- Add comment
COMMENT ON COLUMN active_positions.option_symbol IS 'Full OCC option symbol for options positions (e.g., QCOM260206C00150000)';

-- Create index for faster lookups by option symbol
CREATE INDEX IF NOT EXISTS idx_active_positions_option_symbol 
ON active_positions(option_symbol) 
WHERE option_symbol IS NOT NULL;

COMMIT;
