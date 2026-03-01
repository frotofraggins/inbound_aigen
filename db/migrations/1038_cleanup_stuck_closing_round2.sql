-- Migration 1038: Clean up stuck 'closing' records in tiny account (round 2)
-- Root cause: get_position_by_symbol() only matched status='open', so
-- sync_from_alpaca_positions() kept creating new records for positions
-- already in 'closing' status. Fixed in db.py to match 'open' OR 'closing'.

-- First, close all the duplicate 'closing' records
UPDATE active_positions
SET status = 'closed',
    closed_at = NOW(),
    close_reason = 'cleanup_stuck_closing_v2'
WHERE account_name = 'tiny'
  AND status = 'closing';

-- Also clean up any in the large account (shouldn't be many but just in case)
UPDATE active_positions
SET status = 'closed',
    closed_at = NOW(),
    close_reason = 'cleanup_stuck_closing_v2'
WHERE account_name = 'large'
  AND status = 'closing'
  AND created_at < NOW() - INTERVAL '1 hour';
