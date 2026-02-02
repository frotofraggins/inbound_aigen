-- Migration 006: Fix Dispatcher Status Constraint
-- The dispatcher_recommendations_status_check constraint was missing required status values

-- Drop the old constraint
ALTER TABLE dispatch_recommendations 
  DROP CONSTRAINT IF EXISTS dispatch_recommendations_status_check;

-- Add the correct constraint with all required status values
ALTER TABLE dispatch_recommendations
  ADD CONSTRAINT dispatch_recommendations_status_check 
  CHECK (status IN ('PENDING', 'PROCESSING', 'SIMULATED', 'SKIPPED', 'FAILED', 'EXECUTED', 'CANCELLED'));

-- Add comment to document the state machine
COMMENT ON COLUMN dispatch_recommendations.status IS 
  'State machine: PENDING → PROCESSING → (SIMULATED | SKIPPED | FAILED | EXECUTED | CANCELLED)';
