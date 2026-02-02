-- Migration 012: Add Account Tracking for Multi-Account Support
-- Enables tracking which Alpaca paper account made each trade

-- Add account_name column to dispatch_executions
ALTER TABLE dispatch_executions 
ADD COLUMN IF NOT EXISTS account_name VARCHAR(50);

-- Add index for efficient queries by account
CREATE INDEX IF NOT EXISTS idx_dispatch_executions_account_name 
ON dispatch_executions(account_name, simulated_ts DESC);

-- Create account metadata table
CREATE TABLE IF NOT EXISTS account_metadata (
    account_name VARCHAR(50) PRIMARY KEY,
    tier VARCHAR(20) NOT NULL,
    alpaca_account_id VARCHAR(100),
    initial_balance DECIMAL(12,2) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_trade_at TIMESTAMP,
    notes TEXT
);

-- Insert known accounts
INSERT INTO account_metadata (account_name, tier, initial_balance, notes)
VALUES 
    ('tiny-1k', 'tiny', 1000.00, 'Aggressive growth testing (25% risk, 1-2 contracts)'),
    ('large-100k', 'large', 100000.00, 'Professional tier testing (1% risk, 4-10 contracts)')
ON CONFLICT (account_name) DO NOTHING;
