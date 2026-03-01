"""
Learning Applier — AI-powered review and application of trade analyzer findings.

Uses Bedrock Claude to evaluate pending learning_recommendations, then:
- SSM-configurable params: auto-applies if AI approves (saves rollback value)
- Code-level params: marks as 'ai_approved' for human deploy
- Low-confidence findings: rejects with reasoning

Runs after trade_analyzer (daily after market close).
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import boto3
import psycopg2
import psycopg2.extras
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# SSM parameter paths that can be auto-applied (maps parameter_path → SSM key + YAML key)
SSM_APPLIER_MAP = {
    'dispatcher.risk.gates.confidence': {
        'ssm_params': ['/ops-pipeline/dispatcher_config_large', '/ops-pipeline/dispatcher_config_tiny'],
        'yaml_key': 'confidence_min_options_swing',
    },
    'dispatcher.risk.max_hold': {
        'ssm_params': ['/ops-pipeline/dispatcher_config_large', '/ops-pipeline/dispatcher_config_tiny'],
        'yaml_key': 'max_hold_minutes',
    },
    'dispatcher.risk.take_profit': {
        'ssm_params': ['/ops-pipeline/dispatcher_config_large', '/ops-pipeline/dispatcher_config_tiny'],
        'yaml_key': 'take_profit_pct',
    },
}

MIN_CONFIDENCE_TO_APPLY = 0.5
MIN_SAMPLE_TO_APPLY = 10


# ── Config ──────────────────────────────────────────────────────────────────

def load_db_config() -> Dict:
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    secret = json.loads(secrets.get_secret_value(SecretId='ops-pipeline/db')['SecretString'])
    return {
        'db_host': db_host, 'db_port': int(db_port), 'db_name': db_name,
        'db_user': secret['username'], 'db_password': secret['password'],
    }


def get_conn(cfg):
    return psycopg2.connect(
        host=cfg['db_host'], port=cfg['db_port'], dbname=cfg['db_name'],
        user=cfg['db_user'], password=cfg['db_password'],
    )


# ── Bedrock ─────────────────────────────────────────────────────────────────

def ask_bedrock(prompt: str) -> str:
    client = boto3.client('bedrock-runtime', region_name='us-west-2')
    response = client.invoke_model(
        modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
        body=json.dumps({
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 1500,
            'temperature': 0.1,
            'messages': [{'role': 'user', 'content': prompt}],
        }),
    )
    return json.loads(response['body'].read())['content'][0]['text']


def ai_evaluate(rec: Dict, trade_summary: Dict) -> Dict:
    """Ask Bedrock to evaluate a single recommendation. Returns {decision, reasoning}."""
    prompt = f"""You are a quantitative trading risk manager reviewing a statistical finding from a paper trading system.

SYSTEM CONTEXT:
- Paper trading account (~$122K across 2 accounts)
- Options trading (calls and puts), 1-7 day holds
- {trade_summary['total_trades']} total closed trades, {trade_summary['win_rate']:.0%} win rate, avg P&L {trade_summary['avg_pnl']:+.1f}%

FINDING TO EVALUATE:
- Parameter: {rec['parameter_name']}
- Location: {rec['parameter_path']}
- Current value: {rec['current_value']}
- Suggested value: {rec['suggested_value']}
- Sample size: {rec['sample_size']} trades
- Statistical confidence: {rec['confidence']:.2f} (0-1 scale, based on sample size)
- Expected improvement: {rec['avg_return_if_changed']}% avg return change
- Reasoning: {rec['recommendation_reason']}

RULES:
1. This is PAPER TRADING — we want to learn, so be moderately aggressive about trying changes
2. Reject if sample size < 10 (too little data)
3. Reject if the change could cause the system to stop trading entirely (e.g., threshold too high)
4. Approve if the statistical evidence is reasonable and the change is reversible
5. For borderline cases, approve — we learn more from trying than from waiting

Respond with EXACTLY this JSON format, nothing else:
{{"decision": "approve" or "reject", "reasoning": "1-2 sentence explanation"}}"""

    try:
        raw = ask_bedrock(prompt)
        # Extract JSON from response
        text = raw.strip()
        if '```' in text:
            text = text.split('```')[1].strip()
            if text.startswith('json'):
                text = text[4:].strip()
        result = json.loads(text)
        return {
            'decision': result.get('decision', 'reject'),
            'reasoning': result.get('reasoning', 'No reasoning provided'),
        }
    except Exception as e:
        logger.error(f"Bedrock evaluation failed: {e}")
        return {'decision': 'reject', 'reasoning': f'AI evaluation error: {e}'}


# ── SSM Application ─────────────────────────────────────────────────────────

def apply_ssm_change(parameter_path: str, param_name: str, new_value: float) -> Optional[float]:
    """Apply a change to SSM parameter. Returns old value for rollback, or None on failure."""
    mapping = SSM_APPLIER_MAP.get(parameter_path)
    if not mapping:
        return None

    ssm = boto3.client('ssm', region_name='us-west-2')
    yaml_key = mapping['yaml_key']
    old_value = None

    for ssm_param in mapping['ssm_params']:
        try:
            current = ssm.get_parameter(Name=ssm_param)['Parameter']['Value']
            config = yaml.safe_load(current)
            old_value = config.get(yaml_key)

            # Skip if already at or beyond the suggested value (in the right direction)
            if old_value is not None and old_value == new_value:
                logger.info(f"  ⊘ {ssm_param}: {yaml_key} already at {new_value}, skipping")
                continue

            config[yaml_key] = new_value
            new_yaml = yaml.dump(config, default_flow_style=False)
            ssm.put_parameter(Name=ssm_param, Value=new_yaml, Type='String', Overwrite=True)
            logger.info(f"  ✓ Updated {ssm_param}: {yaml_key} = {old_value} → {new_value}")
        except Exception as e:
            logger.error(f"  ✗ Failed to update {ssm_param}: {e}")
            return None

    return old_value


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 80)
    logger.info("Learning Applier starting")
    logger.info(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 80)

    cfg = load_db_config()
    conn = get_conn(cfg)
    now = datetime.now(timezone.utc)

    try:
        # Get pending recommendations
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, parameter_name, parameter_path,
                       current_value::float, suggested_value::float,
                       sample_size, confidence::float,
                       avg_return_if_changed::float, recommendation_reason, status
                FROM learning_recommendations
                WHERE status = 'pending'
                ORDER BY confidence DESC
            """)
            pending = [dict(r) for r in cur.fetchall()]

        if not pending:
            logger.info("No pending recommendations to review.")
            return

        logger.info(f"Found {len(pending)} pending recommendation(s)")

        # Get trade summary for context
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT COUNT(*) as total,
                       AVG(pnl_pct::float) as avg_pnl,
                       SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) as win_rate
                FROM position_history
            """)
            ts = dict(cur.fetchone())
        trade_summary = {
            'total_trades': ts['total'] or 0,
            'avg_pnl': ts['avg_pnl'] or 0,
            'win_rate': ts['win_rate'] or 0,
        }

        applied = 0
        rejected = 0

        for rec in pending:
            logger.info(f"\n── Evaluating: {rec['parameter_name']} ──")
            logger.info(f"  Current: {rec['current_value']} → Suggested: {rec['suggested_value']}")
            logger.info(f"  Sample: {rec['sample_size']}, Confidence: {rec['confidence']:.2f}")

            # Pre-filter: hard reject if below minimums
            if rec['sample_size'] < MIN_SAMPLE_TO_APPLY:
                decision = 'reject'
                reasoning = f"Sample size {rec['sample_size']} below minimum {MIN_SAMPLE_TO_APPLY}"
            elif rec['confidence'] < MIN_CONFIDENCE_TO_APPLY:
                decision = 'reject'
                reasoning = f"Confidence {rec['confidence']:.2f} below minimum {MIN_CONFIDENCE_TO_APPLY}"
            else:
                # Ask AI
                result = ai_evaluate(rec, trade_summary)
                decision = result['decision']
                reasoning = result['reasoning']

            logger.info(f"  Decision: {decision.upper()}")
            logger.info(f"  Reasoning: {reasoning}")

            if decision == 'approve':
                # Check if this is an SSM-applicable parameter
                is_ssm = rec['parameter_path'] in SSM_APPLIER_MAP
                if is_ssm:
                    old_val = apply_ssm_change(
                        rec['parameter_path'], rec['parameter_name'], rec['suggested_value']
                    )
                    if old_val is not None:
                        new_status = 'applied'
                        rollback_val = old_val
                        applied += 1
                    else:
                        new_status = 'ai_approved'
                        rollback_val = None
                        reasoning += ' (SSM update failed, marked for manual apply)'
                else:
                    new_status = 'ai_approved'
                    rollback_val = rec['current_value']
                    reasoning += ' (requires code change, marked for manual deploy)'
            else:
                new_status = 'rejected'
                rollback_val = None
                rejected += 1

            # Update the recommendation
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE learning_recommendations
                    SET status = %s, reviewed_by = %s, reviewed_at = %s, rollback_value = %s
                    WHERE id = %s
                """, (new_status, f'bedrock-ai', now, rollback_val, rec['id']))
            conn.commit()
            logger.info(f"  → Status: {new_status} | AI: {reasoning[:120]}")

        logger.info(f"\n{'=' * 80}")
        logger.info(f"Learning Applier complete: {applied} applied, {rejected} rejected, "
                     f"{len(pending) - applied - rejected} flagged for manual review")
        logger.info("=" * 80)

    finally:
        conn.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"FATAL: {e}", exc_info=True)
        raise
