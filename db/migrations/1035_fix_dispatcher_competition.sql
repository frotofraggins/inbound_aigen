-- Migration 1035: Fix dispatcher competition
-- Allow both large and tiny dispatchers to execute the same recommendation
-- by changing the UNIQUE index from (recommendation_id) to (recommendation_id, account_name)

-- Drop the old unique index that prevents multi-account execution
DROP INDEX IF EXISTS ux_dispatch_execution_reco;

-- Create new unique index that allows one execution per recommendation per account
CREATE UNIQUE INDEX ux_dispatch_execution_reco_account 
ON dispatch_executions (recommendation_id, account_name);
