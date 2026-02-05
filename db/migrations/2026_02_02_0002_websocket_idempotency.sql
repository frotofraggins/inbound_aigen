-- Migration: 2026_02_02_0002_websocket_idempotency
-- Purpose: Add idempotency for WebSocket trade events
-- Phase: Behavior Learning Mode - Phase 3 (Bug Fixes & Hardening)

-- 1. Create dedupe table for Alpaca WebSocket events
CREATE TABLE IF NOT EXISTS alpaca_event_dedupe (
    event_id VARCHAR(255) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    order_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_alpaca_dedupe_order_id 
    ON alpaca_event_dedupe(order_id);

CREATE INDEX IF NOT EXISTS idx_alpaca_dedupe_processed_at 
    ON alpaca_event_dedupe(processed_at);

-- 2. Add partial unique index on execution_uuid (allows NULLs, enforces uniqueness for non-NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_positions_execution_uuid_unique
    ON active_positions(execution_uuid)
    WHERE execution_uuid IS NOT NULL;

-- 3. Add order_id to active_positions for WebSocket correlation
ALTER TABLE active_positions
    ADD COLUMN IF NOT EXISTS alpaca_order_id VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_active_positions_alpaca_order_id
    ON active_positions(alpaca_order_id)
    WHERE alpaca_order_id IS NOT NULL;

-- Record migration
INSERT INTO schema_migrations (migration_name, applied_at)
VALUES ('2026_02_02_0002_websocket_idempotency', NOW())
ON CONFLICT (migration_name) DO NOTHING;
