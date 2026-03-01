-- Migration 1037: Clean up stuck 'closing' positions in tiny account
-- These accumulated because position manager couldn't close them (no alpaca_order_id)
-- and kept creating duplicate closing records every cycle.
-- Total: ~8,851 rows for QCOM, CRM, PFE, BAC, AMD, PG stuck in 'closing' with null alpaca_order_id

-- Move them to 'closed' status with appropriate exit reason
UPDATE active_positions
SET status = 'closed',
    closed_at = NOW(),
    close_reason = 'cleanup_stuck_closing'
WHERE account_name = 'tiny'
  AND status = 'closing';
