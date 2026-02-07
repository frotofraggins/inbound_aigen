-- Close phantom positions identified by sync script
-- These positions don't exist in Alpaca but are still "open" in database

-- Large account phantom positions (5 positions)
UPDATE active_positions
SET 
    status = 'closed',
    close_reason = 'manual_reconciliation',
    closed_at = NOW(),
    exit_price = entry_price,
    current_pnl_dollars = 0,
    current_pnl_percent = 0
WHERE id IN (21, 16, 19, 24, 13)
AND status IN ('open', 'closing');

-- Tiny account phantom positions (2 additional positions)
UPDATE active_positions
SET 
    status = 'closed',
    close_reason = 'manual_reconciliation',
    closed_at = NOW(),
    exit_price = entry_price,
    current_pnl_dollars = 0,
    current_pnl_percent = 0
WHERE id IN (37, 36)
AND status IN ('open', 'closing');

-- Verify cleanup
SELECT 
    COUNT(*) as total_closed,
    COUNT(CASE WHEN id IN (21, 16, 19, 24, 13, 37, 36) THEN 1 END) as phantom_closed
FROM active_positions
WHERE status = 'closed'
AND close_reason = 'manual_reconciliation'
AND closed_at >= NOW() - INTERVAL '1 minute';
