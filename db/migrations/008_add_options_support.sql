-- Migration 008: Add Options Trading Support
-- Adds columns to dispatch_executions and dispatch_recommendations tables
-- to support options trading alongside stocks
-- Maintains backward compatibility with existing stock trades

-- Add strategy_type column to dispatch_recommendations (for signal engine)
ALTER TABLE dispatch_recommendations
ADD COLUMN IF NOT EXISTS strategy_type TEXT CHECK (strategy_type IN ('day_trade', 'swing_trade', 'conservative'));

-- Add index for querying by strategy type in recommendations
CREATE INDEX IF NOT EXISTS idx_dispatch_reco_strategy_type 
ON dispatch_recommendations(strategy_type) 
WHERE strategy_type IS NOT NULL;

COMMENT ON COLUMN dispatch_recommendations.strategy_type IS 'Options strategy: day_trade (0-1 DTE), swing_trade (7-30 DTE), conservative (ITM)';

-- Add columns for options metadata to dispatch_executions
ALTER TABLE dispatch_executions
ADD COLUMN IF NOT EXISTS instrument_type TEXT DEFAULT 'STOCK' CHECK (instrument_type IN ('STOCK', 'CALL', 'PUT')),
ADD COLUMN IF NOT EXISTS strike_price NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS expiration_date DATE,
ADD COLUMN IF NOT EXISTS contracts INT,
ADD COLUMN IF NOT EXISTS premium_paid NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS delta NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS theta NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS implied_volatility NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS option_symbol TEXT,
ADD COLUMN IF NOT EXISTS strategy_type TEXT CHECK (strategy_type IN ('day_trade', 'swing_trade', 'conservative'));

-- Add index for querying by instrument type
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_instrument_type 
ON dispatch_executions(instrument_type);

-- Add index for querying by expiration date (useful for managing positions)
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_expiration_date 
ON dispatch_executions(expiration_date) 
WHERE expiration_date IS NOT NULL;

-- Add index for querying by strategy type
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_strategy_type 
ON dispatch_executions(strategy_type) 
WHERE strategy_type IS NOT NULL;

-- Add comment explaining the schema changes
COMMENT ON COLUMN dispatch_executions.instrument_type IS 'Type of instrument: STOCK (default), CALL, or PUT';
COMMENT ON COLUMN dispatch_executions.strike_price IS 'Strike price for options (NULL for stocks)';
COMMENT ON COLUMN dispatch_executions.expiration_date IS 'Expiration date for options (NULL for stocks)';
COMMENT ON COLUMN dispatch_executions.contracts IS 'Number of option contracts (NULL for stocks, 1 contract = 100 shares)';
COMMENT ON COLUMN dispatch_executions.premium_paid IS 'Premium paid per contract (NULL for stocks)';
COMMENT ON COLUMN dispatch_executions.delta IS 'Option delta (sensitivity to price changes)';
COMMENT ON COLUMN dispatch_executions.theta IS 'Option theta (time decay)';
COMMENT ON COLUMN dispatch_executions.implied_volatility IS 'Implied volatility of the option';
COMMENT ON COLUMN dispatch_executions.option_symbol IS 'OCC formatted option symbol (e.g., AAPL250131C00150000)';
COMMENT ON COLUMN dispatch_executions.strategy_type IS 'Trading strategy: day_trade (0-1 DTE), swing_trade (7-30 DTE), conservative (ITM)';

-- Validation: For options, strike_price and expiration_date must be set
ALTER TABLE dispatch_executions 
ADD CONSTRAINT check_options_metadata 
CHECK (
    (instrument_type = 'STOCK') OR 
    (instrument_type IN ('CALL', 'PUT') AND strike_price IS NOT NULL AND expiration_date IS NOT NULL)
);

-- Create view for active options positions (not expired)
CREATE OR REPLACE VIEW active_options_positions AS
SELECT 
    execution_id,
    ticker,
    instrument_type,
    strike_price,
    expiration_date,
    contracts,
    premium_paid,
    delta,
    theta,
    implied_volatility,
    option_symbol,
    strategy_type,
    entry_price,
    qty,
    notional,
    stop_loss_price,
    take_profit_price,
    simulated_ts,
    EXTRACT(EPOCH FROM (expiration_date - CURRENT_DATE)) / 86400 AS days_to_expiration
FROM dispatch_executions
WHERE instrument_type IN ('CALL', 'PUT')
    AND expiration_date >= CURRENT_DATE
    AND execution_mode IN ('ALPACA_PAPER', 'LIVE')
ORDER BY expiration_date ASC, simulated_ts DESC;

-- Create view for options performance by strategy
CREATE OR REPLACE VIEW options_performance_by_strategy AS
SELECT 
    strategy_type,
    instrument_type,
    COUNT(*) AS total_trades,
    AVG(notional) AS avg_position_size,
    AVG(premium_paid) AS avg_premium,
    AVG(delta) AS avg_delta,
    AVG(EXTRACT(EPOCH FROM (expiration_date - simulated_ts::date)) / 86400) AS avg_days_held,
    MIN(simulated_ts) AS first_trade,
    MAX(simulated_ts) AS last_trade
FROM dispatch_executions
WHERE instrument_type IN ('CALL', 'PUT')
    AND strategy_type IS NOT NULL
GROUP BY strategy_type, instrument_type
ORDER BY strategy_type, instrument_type;

-- Create summary view for daily options activity
CREATE OR REPLACE VIEW daily_options_summary AS
SELECT 
    DATE(simulated_ts) AS trade_date,
    instrument_type,
    strategy_type,
    COUNT(*) AS num_trades,
    SUM(notional) AS total_notional,
    SUM(contracts) AS total_contracts,
    AVG(premium_paid) AS avg_premium,
    AVG(delta) AS avg_delta
FROM dispatch_executions
WHERE instrument_type IN ('CALL', 'PUT')
GROUP BY DATE(simulated_ts), instrument_type, strategy_type
ORDER BY trade_date DESC, instrument_type, strategy_type;
