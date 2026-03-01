-- Migration 1039: Close phantom DE position
-- Created: 2026-02-13
-- Reason: User manually closed DE position in Alpaca, but database still shows it as open in large account

UPDATE active_positions
SET status = 'closed',
    close_reason = 'manual_reconciliation',
    closed_at = NOW()
WHERE id = 13481
  AND status = 'open';
