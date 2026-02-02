-- Migration 007: Add Volume Features to lane_features
-- Purpose: Enable volume analysis for signal confirmation
-- Date: 2026-01-16
-- Context: Phase 12 - The #1 indicator all professional traders use

-- Add volume-related columns to lane_features
ALTER TABLE lane_features 
ADD COLUMN volume_current BIGINT,
ADD COLUMN volume_avg_20 BIGINT,
ADD COLUMN volume_ratio NUMERIC(10,4),
ADD COLUMN volume_surge BOOLEAN;

-- Add comments for documentation
COMMENT ON COLUMN lane_features.volume_current IS 
  'Current bar volume (number of shares traded)';

COMMENT ON COLUMN lane_features.volume_avg_20 IS 
  '20-period moving average of volume for baseline comparison';

COMMENT ON COLUMN lane_features.volume_ratio IS 
  'Current volume / 20-bar average. >2.0 = surge, <0.5 = dry, 1.0 = normal';

COMMENT ON COLUMN lane_features.volume_surge IS 
  'True if volume_ratio > 2.0 (indicates significant volume spike)';

-- Create index for efficient volume queries
CREATE INDEX idx_lane_features_volume 
ON lane_features(ticker, ts, volume_ratio);

-- Verify the changes
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'lane_features'
    AND column_name LIKE 'volume%'
ORDER BY ordinal_position;
