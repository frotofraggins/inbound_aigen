"""
Trade Analyzer — Statistical analysis of trade outcomes.

Joins recommendations → executions → position_history to find patterns,
then writes actionable findings to learning_recommendations for human review.
Never auto-applies changes.

Designed to run on a schedule (e.g., daily after market close).
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import boto3

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

MIN_SAMPLE = 5  # Minimum trades to draw any conclusion


# ── Config ──────────────────────────────────────────────────────────────────

def load_config() -> Dict:
    region = 'us-west-2'
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)

    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']

    secret = json.loads(
        secrets.get_secret_value(SecretId='ops-pipeline/db')['SecretString']
    )
    return {
        'db_host': db_host, 'db_port': int(db_port), 'db_name': db_name,
        'db_user': secret['username'], 'db_password': secret['password'],
    }


def get_conn(cfg: Dict):
    return psycopg2.connect(
        host=cfg['db_host'], port=cfg['db_port'], dbname=cfg['db_name'],
        user=cfg['db_user'], password=cfg['db_password'],
    )


# ── Data Loading ────────────────────────────────────────────────────────────

TRADE_QUERY = """
SELECT
    ph.id, ph.ticker, ph.instrument_type, ph.strategy_type,
    ph.pnl_pct::float   AS pnl_pct,
    ph.pnl_dollars::float AS pnl_dollars,
    ph.exit_reason,
    ph.holding_seconds,
    ph.best_unrealized_pnl_pct::float  AS mfe,
    ph.worst_unrealized_pnl_pct::float AS mae,
    ph.entry_price::float AS entry_price,
    ph.exit_price::float  AS exit_price,
    dr.features_snapshot,
    dr.confidence::float AS signal_confidence,
    de.account_name
FROM position_history ph
LEFT JOIN LATERAL (
    -- Match execution by execution_id first, fall back to ticker+price
    SELECT de2.execution_id, de2.recommendation_id, de2.account_name
    FROM dispatch_executions de2
    WHERE de2.execution_mode IN ('ALPACA_PAPER', 'LIVE')
      AND (
          (ph.execution_id IS NOT NULL AND de2.execution_id::text = ph.execution_id::text)
          OR (ph.execution_id IS NULL AND de2.ticker = ph.ticker
              AND ABS(de2.entry_price::float - ph.entry_price::float) < 0.01)
      )
    ORDER BY de2.simulated_ts DESC
    LIMIT 1
) de ON true
LEFT JOIN dispatch_recommendations dr ON dr.id = de.recommendation_id
WHERE de.execution_id IS NOT NULL
ORDER BY ph.created_at
"""


def load_trades(conn) -> List[Dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(TRADE_QUERY)
        rows = [dict(r) for r in cur.fetchall()]
    # Parse features_snapshot JSON
    for r in rows:
        fs = r.get('features_snapshot')
        if isinstance(fs, str):
            r['features_snapshot'] = json.loads(fs)
        elif fs is None:
            r['features_snapshot'] = {}
    logger.info(f"Loaded {len(rows)} trades with recommendation features")
    return rows


# ── Analysis Helpers ────────────────────────────────────────────────────────

def _stats(values: List[float]) -> Dict:
    """Mean, median, win-rate for a list of pnl values."""
    if not values:
        return {'mean': 0, 'median': 0, 'win_rate': 0, 'n': 0}
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return {
        'mean': sum(s) / n,
        'median': s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2,
        'win_rate': sum(1 for v in s if v > 0) / n,
        'n': n,
    }


def _split(trades: List[Dict], key, val) -> Tuple[List[Dict], List[Dict]]:
    """Split trades into (matches, non-matches) by a simple equality test."""
    yes, no = [], []
    for t in trades:
        (yes if t.get(key) == val else no).append(t)
    return yes, no


def _split_feature(trades: List[Dict], feat_key, threshold) -> Tuple[List[Dict], List[Dict]]:
    """Split trades by a numeric feature threshold (above vs at-or-below)."""
    above, below = [], []
    for t in trades:
        v = (t.get('features_snapshot') or {}).get(feat_key)
        if v is None:
            continue
        (above if float(v) > threshold else below).append(t)
    return above, below


# ── Analyses ────────────────────────────────────────────────────────────────

def analyze_instrument_type(trades: List[Dict]) -> List[Dict]:
    """Compare CALL vs PUT performance."""
    findings = []
    for inst in ('CALL', 'PUT'):
        group, rest = _split(trades, 'instrument_type', inst)
        if len(group) < MIN_SAMPLE:
            continue
        gs, rs = _stats([t['pnl_pct'] for t in group]), _stats([t['pnl_pct'] for t in rest])
        diff = gs['mean'] - rs['mean']
        if abs(diff) > 3:  # >3% difference is noteworthy
            findings.append({
                'parameter_name': f'{inst}_bias',
                'parameter_path': 'signal_engine.rules.instrument_selection',
                'current_value': 0.5,  # equal weighting
                'suggested_value': round(0.5 + (0.1 if diff > 0 else -0.1), 2),
                'sample_size': gs['n'],
                'confidence': min(gs['n'] / 50, 1.0),
                'avg_return_if_changed': round(diff, 2),
                'reason': (
                    f"{inst}s avg {gs['mean']:+.1f}% (n={gs['n']}, "
                    f"win {gs['win_rate']:.0%}) vs others {rs['mean']:+.1f}% "
                    f"(n={rs['n']}, win {rs['win_rate']:.0%})"
                ),
            })
    return findings


def analyze_confidence_threshold(trades: List[Dict]) -> List[Dict]:
    """Find the confidence threshold that best separates winners from losers."""
    findings = []
    best_threshold, best_diff = None, 0
    for thresh in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]:
        above = [t for t in trades if (t.get('signal_confidence') or 0) > thresh]
        below = [t for t in trades if (t.get('signal_confidence') or 0) <= thresh]
        if len(above) < MIN_SAMPLE or len(below) < MIN_SAMPLE:
            continue
        a_mean = sum(t['pnl_pct'] for t in above) / len(above)
        b_mean = sum(t['pnl_pct'] for t in below) / len(below)
        diff = a_mean - b_mean
        if diff > best_diff:
            best_diff, best_threshold = diff, thresh

    if best_threshold is not None and best_diff > 3:
        above = [t for t in trades if (t.get('signal_confidence') or 0) > best_threshold]
        below = [t for t in trades if (t.get('signal_confidence') or 0) <= best_threshold]
        a_s, b_s = _stats([t['pnl_pct'] for t in above]), _stats([t['pnl_pct'] for t in below])
        findings.append({
            'parameter_name': 'min_confidence_threshold',
            'parameter_path': 'dispatcher.risk.gates.confidence',
            'current_value': 0.3,  # current gate threshold
            'suggested_value': best_threshold,
            'sample_size': a_s['n'] + b_s['n'],
            'confidence': min((a_s['n'] + b_s['n']) / 50, 1.0),
            'avg_return_if_changed': round(best_diff, 2),
            'reason': (
                f"Trades above {best_threshold} confidence: {a_s['mean']:+.1f}% avg "
                f"(n={a_s['n']}, win {a_s['win_rate']:.0%}). "
                f"Below: {b_s['mean']:+.1f}% (n={b_s['n']}, win {b_s['win_rate']:.0%}). "
                f"Raising threshold would filter {b_s['n']} losing trades."
            ),
        })
    return findings


def analyze_volume_surge(trades: List[Dict]) -> List[Dict]:
    """Do trades entered during volume surges perform better?"""
    surge, no_surge = _split_feature(trades, 'volume_surge', 0.5)
    if len(surge) < MIN_SAMPLE or len(no_surge) < MIN_SAMPLE:
        return []
    ss, ns = _stats([t['pnl_pct'] for t in surge]), _stats([t['pnl_pct'] for t in no_surge])
    diff = ss['mean'] - ns['mean']
    if abs(diff) < 2:
        return []
    return [{
        'parameter_name': 'volume_surge_weight',
        'parameter_path': 'signal_engine.rules.volume_mult',
        'current_value': 1.25,
        'suggested_value': round(1.25 + (0.1 if diff > 0 else -0.15), 2),
        'sample_size': ss['n'] + ns['n'],
        'confidence': min((ss['n'] + ns['n']) / 50, 1.0),
        'avg_return_if_changed': round(diff, 2),
        'reason': (
            f"Volume surge trades: {ss['mean']:+.1f}% avg (n={ss['n']}, "
            f"win {ss['win_rate']:.0%}). No surge: {ns['mean']:+.1f}% "
            f"(n={ns['n']}, win {ns['win_rate']:.0%})."
        ),
    }]


def analyze_exit_reasons(trades: List[Dict]) -> List[Dict]:
    """Are time_stop exits a sign the hold time is wrong?"""
    findings = []
    time_stops = [t for t in trades if t.get('exit_reason') == 'time_stop']
    if len(time_stops) < MIN_SAMPLE:
        return findings

    ts_stats = _stats([t['pnl_pct'] for t in time_stops])
    # Check MFE — if time_stop trades had high MFE, we're holding too long
    mfe_vals = [t['mfe'] for t in time_stops if t.get('mfe') is not None]
    avg_mfe = sum(mfe_vals) / len(mfe_vals) if mfe_vals else 0

    if avg_mfe > 15:  # Had >15% unrealized gain but exited at time_stop
        findings.append({
            'parameter_name': 'take_profit_pct',
            'parameter_path': 'dispatcher.risk.take_profit',
            'current_value': 80,
            'suggested_value': round(avg_mfe * 0.6, 0),  # Capture 60% of avg MFE
            'sample_size': len(time_stops),
            'confidence': min(len(time_stops) / 30, 1.0),
            'avg_return_if_changed': round(avg_mfe * 0.6 - ts_stats['mean'], 2),
            'reason': (
                f"{len(time_stops)} time_stop exits avg {ts_stats['mean']:+.1f}% P&L "
                f"but avg MFE was {avg_mfe:+.1f}%. Trades reached profit but "
                f"gave it back. Consider lower take-profit target ~{avg_mfe * 0.6:.0f}%."
            ),
        })

    # Check if hold time is too short (MAE still improving at exit)
    mae_vals = [t['mae'] for t in time_stops if t.get('mae') is not None]
    avg_mae = sum(mae_vals) / len(mae_vals) if mae_vals else 0
    avg_hold_hrs = sum(t.get('holding_seconds', 0) for t in time_stops) / len(time_stops) / 3600

    if ts_stats['mean'] > 0 and avg_hold_hrs < 6:
        findings.append({
            'parameter_name': 'max_hold_minutes',
            'parameter_path': 'dispatcher.risk.max_hold',
            'current_value': 240,
            'suggested_value': 360,
            'sample_size': len(time_stops),
            'confidence': min(len(time_stops) / 30, 1.0),
            'avg_return_if_changed': round(ts_stats['mean'] * 0.3, 2),
            'reason': (
                f"{len(time_stops)} time_stop exits avg {ts_stats['mean']:+.1f}% "
                f"after {avg_hold_hrs:.1f}h hold. Avg MAE {avg_mae:+.1f}%. "
                f"Positions were still profitable — extending hold time may help."
            ),
        })

    return findings


def analyze_trend_state(trades: List[Dict]) -> List[Dict]:
    """Does trend alignment actually predict outcomes?"""
    bull, bear = [], []
    for t in trades:
        ts = (t.get('features_snapshot') or {}).get('trend_state')
        if ts is None:
            continue
        (bull if int(ts) == 1 else bear).append(t)
    if len(bull) < MIN_SAMPLE or len(bear) < MIN_SAMPLE:
        return []
    bs, brs = _stats([t['pnl_pct'] for t in bull]), _stats([t['pnl_pct'] for t in bear])
    diff = bs['mean'] - brs['mean']
    if abs(diff) < 2:
        return []
    return [{
        'parameter_name': 'trend_alignment_weight',
        'parameter_path': 'signal_engine.rules.base_confidence.trend_alignment',
        'current_value': 0.35,
        'suggested_value': round(0.35 + (0.05 if diff > 0 else -0.05), 2),
        'sample_size': bs['n'] + brs['n'],
        'confidence': min((bs['n'] + brs['n']) / 50, 1.0),
        'avg_return_if_changed': round(diff, 2),
        'reason': (
            f"Bull-trend entries: {bs['mean']:+.1f}% avg (n={bs['n']}, "
            f"win {bs['win_rate']:.0%}). Bear-trend: {brs['mean']:+.1f}% "
            f"(n={brs['n']}, win {brs['win_rate']:.0%}). "
            f"Trend weight {'validated' if diff > 0 else 'may be overweighted'}."
        ),
    }]


def analyze_vol_ratio(trades: List[Dict]) -> List[Dict]:
    """Does volatility regime affect outcomes?"""
    high_vol, low_vol = _split_feature(trades, 'vol_ratio', 1.5)
    if len(high_vol) < MIN_SAMPLE or len(low_vol) < MIN_SAMPLE:
        return []
    hs, ls = _stats([t['pnl_pct'] for t in high_vol]), _stats([t['pnl_pct'] for t in low_vol])
    diff = hs['mean'] - ls['mean']
    if abs(diff) < 2:
        return []
    return [{
        'parameter_name': 'high_vol_penalty',
        'parameter_path': 'signal_engine.rules.vol_appropriateness',
        'current_value': 0.5,
        'suggested_value': round(0.5 + (0.1 if diff > 0 else -0.1), 2),
        'sample_size': hs['n'] + ls['n'],
        'confidence': min((hs['n'] + ls['n']) / 50, 1.0),
        'avg_return_if_changed': round(diff, 2),
        'reason': (
            f"High-vol entries (ratio>1.5): {hs['mean']:+.1f}% avg (n={hs['n']}, "
            f"win {hs['win_rate']:.0%}). Low-vol: {ls['mean']:+.1f}% "
            f"(n={ls['n']}, win {ls['win_rate']:.0%})."
        ),
    }]


# ── Write Findings ──────────────────────────────────────────────────────────

INSERT_FINDING = """
INSERT INTO learning_recommendations (
    parameter_name, parameter_path, current_value, suggested_value,
    sample_size, confidence, avg_return_if_changed,
    recommendation_reason, status, generated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
"""


def write_findings(conn, findings: List[Dict]) -> int:
    now = datetime.now(timezone.utc)
    written = 0
    with conn.cursor() as cur:
        for f in findings:
            try:
                cur.execute(INSERT_FINDING, (
                    f['parameter_name'], f['parameter_path'],
                    f['current_value'], f['suggested_value'],
                    f['sample_size'], round(f['confidence'], 4),
                    f.get('avg_return_if_changed'),
                    f['reason'], now,
                ))
                written += 1
            except Exception as e:
                logger.error(f"Failed to write finding {f['parameter_name']}: {e}")
                conn.rollback()
                continue
    conn.commit()
    return written


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 80)
    logger.info("Trade Analyzer starting")
    logger.info(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 80)

    cfg = load_config()
    conn = get_conn(cfg)

    try:
        trades = load_trades(conn)
        if len(trades) < MIN_SAMPLE:
            logger.info(f"Only {len(trades)} trades with features — need {MIN_SAMPLE}+. Exiting.")
            return

        # Log summary
        pnls = [t['pnl_pct'] for t in trades]
        s = _stats(pnls)
        logger.info(
            f"Dataset: {s['n']} trades, avg {s['mean']:+.1f}%, "
            f"median {s['median']:+.1f}%, win rate {s['win_rate']:.0%}"
        )

        # Run all analyses
        all_findings = []
        analyses = [
            ('Instrument Type', analyze_instrument_type),
            ('Confidence Threshold', analyze_confidence_threshold),
            ('Volume Surge', analyze_volume_surge),
            ('Exit Reasons', analyze_exit_reasons),
            ('Trend State', analyze_trend_state),
            ('Volatility Ratio', analyze_vol_ratio),
        ]

        for name, fn in analyses:
            logger.info(f"\n── {name} ──")
            findings = fn(trades)
            if findings:
                for f in findings:
                    logger.info(f"  FINDING: {f['parameter_name']}")
                    logger.info(f"    {f['reason']}")
                all_findings.extend(findings)
            else:
                logger.info(f"  No significant findings (need {MIN_SAMPLE}+ samples per group)")

        # Write to learning_recommendations
        if all_findings:
            written = write_findings(conn, all_findings)
            logger.info(f"\n✓ Wrote {written} findings to learning_recommendations (status=pending)")
        else:
            logger.info("\nNo actionable findings yet — need more trades.")

        logger.info("\n" + "=" * 80)
        logger.info("Trade Analyzer completed")
        logger.info("=" * 80)

    finally:
        conn.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"FATAL: {e}", exc_info=True)
        raise
