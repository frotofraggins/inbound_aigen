-- Migration 016: Create lane_features_clean view
-- Purpose: provide a stable, training-safe feature source that excludes incomplete rows
--          (e.g., rows missing volume_ratio during backfills or early ticker warmup).
--
-- NOTE: This does NOT change feature computation/writes; it only adds a read-only view.

CREATE OR REPLACE VIEW lane_features_clean AS
SELECT *
FROM lane_features
WHERE volume_ratio IS NOT NULL;

