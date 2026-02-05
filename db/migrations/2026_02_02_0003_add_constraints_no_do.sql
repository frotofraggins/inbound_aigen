-- Migration: 2026_02_02_0003_add_constraints_no_do
-- Re-adds constraints that were removed when DO blocks were stripped
-- Idempotent: checks if constraint exists before adding

-- Check and add constraint for active_positions.side
-- Includes: long, short, call, put (for options)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_active_positions_side'
    ) THEN
        ALTER TABLE active_positions 
        ADD CONSTRAINT chk_active_positions_side 
        CHECK (side IN ('long', 'short', 'call', 'put'))
        NOT VALID;
    END IF;
END $$;

-- Check and add constraint for active_positions.strategy_type
-- Includes: day_trade, swing_trade, conservative (NULL allowed for stocks)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_active_positions_strategy_type'
    ) THEN
        ALTER TABLE active_positions 
        ADD CONSTRAINT chk_active_positions_strategy_type 
        CHECK (strategy_type IN ('day_trade', 'swing_trade', 'conservative') OR strategy_type IS NULL)
        NOT VALID;
    END IF;
END $$;

-- Check and add constraint for position_history.side
-- Includes: long, short, call, put (for options)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_position_history_side'
    ) THEN
        ALTER TABLE position_history 
        ADD CONSTRAINT chk_position_history_side 
        CHECK (side IN ('long', 'short', 'call', 'put'))
        NOT VALID;
    END IF;
END $$;

-- Check and add constraint for position_history.strategy_type
-- Includes: day_trade, swing_trade, conservative (NULL allowed for stocks)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_position_history_strategy_type'
    ) THEN
        ALTER TABLE position_history 
        ADD CONSTRAINT chk_position_history_strategy_type 
        CHECK (strategy_type IN ('day_trade', 'swing_trade', 'conservative') OR strategy_type IS NULL)
        NOT VALID;
    END IF;
END $$;

-- Record migration
INSERT INTO schema_migrations (version) VALUES ('2026_02_02_0003_add_constraints_no_do') ON CONFLICT (version) DO NOTHING;
