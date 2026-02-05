-- Migration 1002: Add account_name column to dispatch_executions table
-- Date: 2026-02-03
-- Purpose: Enable per-account execution tracking for multi-account support

-- Add account_name column with default value
ALTER TABLE dispatch_executions 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50) DEFAULT 'large-default';

-- Create index for efficient filtering by account
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_account_name 
ON dispatch_executions(account_name);

-- Create composite index for common query pattern (date + account)
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_date_account 
ON dispatch_executions(simulated_ts, account_name);

-- Update existing rows to have account_name (if any exist without it)
UPDATE dispatch_executions 
SET account_name = 'large-default' 
WHERE account_name IS NULL;
