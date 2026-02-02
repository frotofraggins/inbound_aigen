-- Cleanup historical unfinished dispatcher runs from debugging period
-- These are runs that crashed before calling finalize_run()

UPDATE dispatcher_runs
SET finished_at = started_at + INTERVAL '1 minute',
    run_summary_json = '{"note": "Historical run from debugging period", "cleaned": true}'::jsonb
WHERE finished_at IS NULL
  AND started_at < NOW() - INTERVAL '5 minutes';

-- Verify cleanup
SELECT COUNT(*) as cleaned_count FROM dispatcher_runs WHERE finished_at IS NOT NULL AND run_summary_json->>'cleaned' = 'true';
