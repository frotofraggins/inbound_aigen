-- Migration 1003: Sync tiny account positions from Alpaca
-- These positions exist in Alpaca but not in database
-- Need to be monitored and closed at 3:55 PM ET

-- AMD PUT: Current $7.00, P&L -$350 = entry was $10.50
INSERT INTO active_positions (
    ticker, instrument_type, strategy_type, side, quantity,
    entry_price, entry_time, strike_price, expiration_date, option_symbol,
    stop_loss, take_profit, max_hold_minutes,
    current_price, status, account_name
) VALUES (
    'AMD', 'PUT', 'swing_trade', 'long', 1,
    10.50, NOW() - INTERVAL '24 hours', 205.0, '2026-02-20', 'AMD260220P00205000',
    6.30, 18.90, 240,
    7.00, 'open', 'tiny'
) ON CONFLICT DO NOTHING;

-- CRM CALL: Current $1.88, P&L -$417 = entry was $6.05
INSERT INTO active_positions (
    ticker, instrument_type, strategy_type, side, quantity,
    entry_price, entry_time, strike_price, expiration_date, option_symbol,
    stop_loss, take_profit, max_hold_minutes,
    current_price, status, account_name
) VALUES (
    'CRM', 'CALL', 'swing_trade', 'long', 1,
    6.05, NOW() - INTERVAL '24 hours', 200.0, '2026-02-13', 'CRM260213C00200000',
    3.63, 10.89, 240,
    1.88, 'open', 'tiny'
) ON CONFLICT DO NOTHING;

-- BAC CALL: Current $1.36, P&L +$26 = entry was $1.10
INSERT INTO active_positions (
    ticker, instrument_type, strategy_type, side, quantity,
    entry_price, entry_time, strike_price, expiration_date, option_symbol,
    stop_loss, take_profit, max_hold_minutes,
    current_price, status, account_name
) VALUES (
    'BAC', 'CALL', 'swing_trade', 'long', 1,
    1.10, NOW() - INTERVAL '24 hours', 56.0, '2026-02-20', 'BAC260220C00056000',
    0.66, 1.98, 240,
    1.36, 'open', 'tiny'
) ON CONFLICT DO NOTHING;

-- PFE CALL: Current $0.34, P&L +$4 = entry was $0.30
INSERT INTO active_positions (
    ticker, instrument_type, strategy_type, side, quantity,
    entry_price, entry_time, strike_price, expiration_date, option_symbol,
    stop_loss, take_profit, max_hold_minutes,
    current_price, status, account_name
) VALUES (
    'PFE', 'CALL', 'swing_trade', 'long', 1,
    0.30, NOW() - INTERVAL '24 hours', 27.5, '2026-02-20', 'PFE260220C00027500',
    0.18, 0.54, 240,
    0.34, 'open', 'tiny'
) ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (version) VALUES ('1003_sync_tiny_positions') ON CONFLICT (version) DO NOTHING;
