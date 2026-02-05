-- Minimal version of migration 013 - just the critical columns for trailing stops
-- Can be run via any SQL client or Lambda

-- Add peak_price and trailing_stop_price to active_positions
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS entry_underlying_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS original_quantity INTEGER;

-- Verify columns added
SELECT 
    column_name, 
    data_type, 
    character_maximum_length,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'active_positions' 
AND column_name IN ('peak_price', 'trailing_stop_price', 'entry_underlying_price', 'original_quantity')
ORDER BY column_name;
