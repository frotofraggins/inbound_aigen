-- Nightly stats job (draft)
-- Computes strategy_stats from position_history

-- Configure lookback
-- Example: 90 days

WITH base AS (
    SELECT *
    FROM position_history
    WHERE exit_ts >= NOW() - INTERVAL '90 days'
),
agg AS (
    SELECT
        CURRENT_DATE AS as_of_date,
        90 AS lookback_days,
        ticker,
        strategy_type,
        asset_type,
        COUNT(*) AS n_trades,
        AVG(CASE WHEN pnl_dollars > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
        AVG(pnl_pct) AS avg_return,
        AVG(mae_pct) AS avg_mae,
        AVG(mfe_pct) AS avg_mfe,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY mae_pct) AS mae_p50,
        percentile_cont(0.70) WITHIN GROUP (ORDER BY mae_pct) AS mae_p70,
        percentile_cont(0.80) WITHIN GROUP (ORDER BY mae_pct) AS mae_p80,
        percentile_cont(0.90) WITHIN GROUP (ORDER BY mae_pct) AS mae_p90,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY mfe_pct) AS mfe_p50,
        percentile_cont(0.70) WITHIN GROUP (ORDER BY mfe_pct) AS mfe_p70,
        percentile_cont(0.80) WITHIN GROUP (ORDER BY mfe_pct) AS mfe_p80,
        percentile_cont(0.90) WITHIN GROUP (ORDER BY mfe_pct) AS mfe_p90,
        AVG(CASE WHEN pnl_dollars > 0 THEN holding_minutes END) AS avg_hold_win_min,
        AVG(CASE WHEN pnl_dollars <= 0 THEN holding_minutes END) AS avg_hold_loss_min
    FROM base
    GROUP BY ticker, strategy_type, asset_type
)
INSERT INTO strategy_stats (
    as_of_date, lookback_days, ticker, strategy_type, asset_type,
    n_trades, win_rate, avg_return, avg_mae, avg_mfe,
    mae_p50, mae_p70, mae_p80, mae_p90,
    mfe_p50, mfe_p70, mfe_p80, mfe_p90,
    avg_hold_win_min, avg_hold_loss_min,
    sharpe, max_drawdown, updated_at
)
SELECT
    a.*,
    CASE WHEN a.n_trades >= 30 THEN NULL ELSE NULL END AS sharpe,
    NULL AS max_drawdown,
    NOW() AS updated_at
FROM agg a
ON CONFLICT (as_of_date, lookback_days, ticker, strategy_type, asset_type)
DO UPDATE SET
    n_trades = EXCLUDED.n_trades,
    win_rate = EXCLUDED.win_rate,
    avg_return = EXCLUDED.avg_return,
    avg_mae = EXCLUDED.avg_mae,
    avg_mfe = EXCLUDED.avg_mfe,
    mae_p50 = EXCLUDED.mae_p50,
    mae_p70 = EXCLUDED.mae_p70,
    mae_p80 = EXCLUDED.mae_p80,
    mae_p90 = EXCLUDED.mae_p90,
    mfe_p50 = EXCLUDED.mfe_p50,
    mfe_p70 = EXCLUDED.mfe_p70,
    mfe_p80 = EXCLUDED.mfe_p80,
    mfe_p90 = EXCLUDED.mfe_p90,
    avg_hold_win_min = EXCLUDED.avg_hold_win_min,
    avg_hold_loss_min = EXCLUDED.avg_hold_loss_min,
    updated_at = NOW();
