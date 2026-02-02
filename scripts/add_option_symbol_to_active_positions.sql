-- Add option_symbol column to active_positions table
-- This was in migration 008 for dispatch_executions but missed for active_positions

ALTER TABLE active_positions ADD COLUMN IF NOT EXISTS option_symbol TEXT;

COMMENT ON COLUMN active_positions.option_symbol IS 'Full OCC option symbol for options positions (e.g., QCOM260206C00150000)';
