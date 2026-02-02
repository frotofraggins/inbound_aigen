-- Migration 014: Sync Active Positions from Dispatch Executions
-- Created: 2026-01-29
-- Purpose: Create active_position records for ALPACA_PAPER trades that aren't being tracked yet

BEGIN;

-- Insert active positions for options trades that aren't tracked
INSERT INTO active_positions (
    execution_id, ticker, instrument_type, strategy_type,
    side, quantity, entry_price, entry_time,
    strike_price, expiration_date,
    stop_loss, take_profit, max_hold_minutes,
    bracket_order_accepted, current_price, status,
    original_quantity
)
SELECT 
    de.execution_id,
    de.ticker,
    de.instrument_type,
    COALESCE(de.strategy_type, 'swing_trade'),  -- Default to swing_trade for options
    'long',  -- All our trades are long
    de.qty,
    de.entry_price,
    de.simulated_ts,
    de.strike_price,
    de.expiration_date,
    de.stop_loss_price,
    de.take_profit_price,
    COALESCE(de.max_hold_minutes, 240),
    false,  -- Bracket orders not used for options
    de.entry_price,  -- Initial current_price = entry_price
    'open',
    de.qty  -- original_quantity = initial quantity
FROM dispatch_executions de
LEFT JOIN active_positions ap ON ap.execution_id = de.execution_id
WHERE de.execution_mode = 'ALPACA_PAPER'
  AND de.instrument_type IN ('CALL', 'PUT')
  AND ap.id IS NULL  -- Not already tracked
ON CONFLICT (execution_id) DO NOTHING;

COMMIT;
