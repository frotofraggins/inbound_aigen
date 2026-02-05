-- Migration 1001: Add account_name column to active_positions table
-- Date: 2026-02-03
-- Purpose: Enable per-account position tracking for multi-account support

-- Add account_name column with default value
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50) DEFAULT 'large';

-- Create index for efficient filtering by account
CREATE INDEX IF NOT EXISTS idx_active_positions_account_name 
ON active_positions(account_name);

-- Create composite index for common query pattern (status + account)
CREATE INDEX IF NOT EXISTS idx_active_positions_status_account 
ON active_positions(status, account_name);

-- Update existing rows to have account_name (if any exist without it)
UPDATE active_positions 
SET account_name = 'large' 
WHERE account_name IS NULL;
