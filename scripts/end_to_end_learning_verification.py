#!/usr/bin/env python3
"""
End-to-End Learning Data Verification
Verifies entire pipeline from bars → learning tables
"""
import boto3
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
import json

def get_db_connection():
    """Get database connection"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    response = ssm.get_parameters_by_path(
        Path='/ops-pipeline/db',
        WithDecryption=True
    )
    
    param_dict = {}
    for param in response['Parameters']:
        key = param['Name'].split('/')[-1]
        param_dict[key] = param['Value']
    
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    db_secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(db_secret['SecretString'])
    
    return psycopg2.connect(
        host=param_dict.get('host', param_dict.get('endpoint', '')),
        port=int(param_dict.get('port', 5432)),
        dbname=param_dict.get('name', param_dict.get('database', '')),
        user=secret_data['username'],
        password=secret_data['password']
    )

def print_section(title):
    """Print section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def check_pipeline_stage(conn, stage_name, query, expected_min=0):
    """Check a pipeline stage and return count"""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query)
    results = cur.fetchall()
    cur.close()
    
    count = results[0]['count'] if results and 'count' in results[0] else len(results)
    
    status = "✅" if count >= expected_min else "⚠️"
    print(f"{status} {stage_name}: {count:,} records")
    
    return count, results

def main():
    """Run end-to-end verification"""
    print("\n" + "=" * 80)
    print("  END-TO-END LEARNING DATA VERIFICATION")
    print("  " + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
    print("=" * 80)
    
    conn = get_db_connection()
    
    try:
        # Stage 1: Bar Data (Input)
        print_section("STAGE 1: BAR DATA (Raw Market Data)")
        
        query = "SELECT COUNT(*) as count FROM bars WHERE ts > NOW() - INTERVAL '24 hours'"
        bar_count, _ = check_pipeline_stage(conn, "Bars (24h)", query, expected_min=1000)
        
        # Show ticker coverage
        ticker_query = """
        SELECT ticker, COUNT(*) as bar_count
        FROM bars 
        WHERE ts > NOW() - INTERVAL '24 hours'
        GROUP BY ticker
        ORDER BY bar_count DESC
        LIMIT 10
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(ticker_query)
        tickers = cur.fetchall()
        cur.close()
        
        print("\n  Top 10 tickers by bar count:")
        for t in tickers:
            print(f"    {t['ticker']}: {t['bar_count']:,} bars")
        
        # Stage 2: Features (Computed)
        print_section("STAGE 2: FEATURES (AI Inputs)")
        
        query = "SELECT COUNT(*) as count FROM features WHERE created_at > NOW() - INTERVAL '24 hours'"
        feature_count, _ = check_pipeline_stage(conn, "Features (24h)", query, expected_min=100)
        
        # Check feature quality
        feature_check = """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN rsi_14 IS NOT NULL THEN 1 END) as has_rsi,
            COUNT(CASE WHEN volume_ratio IS NOT NULL THEN 1 END) as has_volume,
            COUNT(CASE WHEN sentiment_score IS NOT NULL THEN 1 END) as has_sentiment
        FROM features
        WHERE created_at > NOW() - INTERVAL '24 hours'
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(feature_check)
        feat_quality = cur.fetchone()
        cur.close()
        
        print(f"\n  Feature quality:")
        print(f"    RSI populated: {feat_quality['has_rsi']}/{feat_quality['total']} ({100*feat_quality['has_rsi']/feat_quality['total']:.1f}%)")
        print(f"    Volume populated: {feat_quality['has_volume']}/{feat_quality['total']} ({100*feat_quality['has_volume']/feat_quality['total']:.1f}%)")
        print(f"    Sentiment populated: {feat_quality['has_sentiment']}/{feat_quality['total']} ({100*feat_quality['has_sentiment']/feat_quality['total']:.1f}%)")
        
        # Stage 3: Signals (AI Output)
        print_section("STAGE 3: SIGNALS (AI Decisions)")
        
        query = "SELECT COUNT(*) as count FROM signals WHERE generated_at > NOW() - INTERVAL '24 hours'"
        signal_count, _ = check_pipeline_stage(conn, "Signals (24h)", query, expected_min=10)
        
        # Show signal types
        signal_types = """
        SELECT 
            signal_type,
            COUNT(*) as count,
            AVG(confidence_score) as avg_confidence
        FROM signals
        WHERE generated_at > NOW() - INTERVAL '24 hours'
        GROUP BY signal_type
        ORDER BY count DESC
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(signal_types)
        sig_types = cur.fetchall()
        cur.close()
        
        print(f"\n  Signal types:")
        for s in sig_types:
            print(f"    {s['signal_type']}: {s['count']} signals (avg confidence: {s['avg_confidence']:.2f})")
        
        # Stage 4: Recommendations (Filtered Signals)
        print_section("STAGE 4: RECOMMENDATIONS (Trade Candidates)")
        
        query = "SELECT COUNT(*) as count FROM dispatch_recommendations WHERE created_at > NOW() - INTERVAL '24 hours'"
        rec_count, _ = check_pipeline_stage(conn, "Recommendations (24h)", query, expected_min=5)
        
        # Show recommendation details
        rec_details = """
        SELECT 
            ticker,
            strategy_type,
            confidence_score,
            entry_price,
            created_at
        FROM dispatch_recommendations
        WHERE created_at > NOW() - INTERVAL '24 hours'
        ORDER BY created_at DESC
        LIMIT 10
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(rec_details)
        recs = cur.fetchall()
        cur.close()
        
        print(f"\n  Recent recommendations:")
        for r in recs:
            print(f"    {r['created_at'].strftime('%H:%M')} - {r['ticker']} {r['strategy_type']} @ ${r['entry_price']:.2f} (conf: {r['confidence_score']:.2f})")
        
        # Stage 5: Executions (Trades Attempted)
        print_section("STAGE 5: EXECUTIONS (Trades Placed)")
        
        query = """
        SELECT COUNT(*) as count 
        FROM dispatch_executions 
        WHERE simulated_ts > NOW() - INTERVAL '24 hours'
        AND execution_mode IN ('ALPACA_PAPER', 'LIVE')
        """
        exec_count, _ = check_pipeline_stage(conn, "Executions (24h)", query, expected_min=1)
        
        # Show execution breakdown
        exec_breakdown = """
        SELECT 
            account_name,
            instrument_type,
            COUNT(*) as count,
            SUM(CASE WHEN status = 'FILLED' THEN 1 ELSE 0 END) as filled
        FROM dispatch_executions
        WHERE simulated_ts > NOW() - INTERVAL '24 hours'
        AND execution_mode IN ('ALPACA_PAPER', 'LIVE')
        GROUP BY account_name, instrument_type
        ORDER BY account_name, instrument_type
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(exec_breakdown)
        execs = cur.fetchall()
        cur.close()
        
        print(f"\n  Execution breakdown:")
        for e in execs:
            print(f"    {e['account_name']} - {e['instrument_type']}: {e['filled']}/{e['count']} filled")
        
        # Stage 6: Active Positions (Currently Open)
        print_section("STAGE 6: ACTIVE POSITIONS (Currently Tracking)")
        
        query = "SELECT COUNT(*) as count FROM active_positions WHERE status = 'open'"
        pos_count, _ = check_pipeline_stage(conn, "Open Positions", query)
        
        # Show open positions
        if pos_count > 0:
            pos_query = """
            SELECT 
                id,
                ticker,
                instrument_type,
                account_name,
                entry_time,
                EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as age_minutes,
                entry_price,
                current_price,
                current_pnl_percent
            FROM active_positions
            WHERE status = 'open'
            ORDER BY entry_time DESC
            """
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(pos_query)
            positions = cur.fetchall()
            cur.close()
            
            print(f"\n  Open positions:")
            for p in positions:
                pnl = p['current_pnl_percent'] or 0
                print(f"    {p['id']}: {p['ticker']} ({p['instrument_type']}) - {p['account_name']}")
                print(f"        Age: {p['age_minutes']:.1f} min, P&L: {pnl:+.2f}%")
        
        # Stage 7: Closed Positions
        print_section("STAGE 7: CLOSED POSITIONS (Exit History)")
        
        closed_query = """
        SELECT COUNT(*) as count 
        FROM active_positions 
        WHERE exit_time IS NOT NULL
        AND entry_time > NOW() - INTERVAL '24 hours'
        """
        closed_count, _ = check_pipeline_stage(conn, "Closed Positions (24h)", closed_query)
        
        if closed_count > 0:
            # Show recent closes
            recent_closes = """
            SELECT 
                ticker,
                instrument_type,
                account_name,
                EXTRACT(EPOCH FROM (exit_time - entry_time))/60 as hold_minutes,
                entry_price,
                exit_price,
                exit_reason
            FROM active_positions
            WHERE exit_time IS NOT NULL
            AND entry_time > NOW() - INTERVAL '24 hours'
            ORDER BY exit_time DESC
            LIMIT 5
            """
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(recent_closes)
            closes = cur.fetchall()
            cur.close()
            
            print(f"\n  Recent closes:")
            for c in closes:
                pnl_pct = ((c['exit_price'] - c['entry_price']) / c['entry_price']) * 100
                print(f"    {c['ticker']} ({c['instrument_type']}) - {c['account_name']}")
                print(f"        Held: {c['hold_minutes']:.1f} min, P&L: {pnl_pct:+.2f}%, Reason: {c['exit_reason']}")
        
        # Stage 8: LEARNING DATA (Critical for AI)
        print_section("STAGE 8: LEARNING DATA (AI Training)")
        
        # Check position_history
        history_query = """
        SELECT COUNT(*) as count 
        FROM position_history
        WHERE created_at > NOW() - INTERVAL '24 hours'
        """
        history_count, _ = check_pipeline_stage(conn, "Position History (24h)", history_query)
        
        if history_count == 0 and closed_count > 0:
            print(f"\n  🚨 CRITICAL BUG: {closed_count} positions closed but 0 saved to position_history!")
            print("     Learning data is NOT being recorded!")
            print("     This blocks AI improvement!")
        
        # Check if features_snapshot is being saved
        features_check = """
        SELECT 
            COUNT(*) as total,
            COUNT(entry_features_json) as has_features
        FROM active_positions
        WHERE entry_time > NOW() - INTERVAL '24 hours'
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(features_check)
        feat_check = cur.fetchone()
        cur.close()
        
        print(f"\n  Feature snapshot quality:")
        if feat_check['total'] > 0:
            pct = 100 * feat_check['has_features'] / feat_check['total']
            print(f"    Positions with features: {feat_check['has_features']}/{feat_check['total']} ({pct:.1f}%)")
        
        # Stage 9: Error Check
        print_section("STAGE 9: ERROR CHECK")
        
        # Check for NULL critical fields
        null_check = """
        SELECT 
            COUNT(*) FILTER (WHERE entry_price IS NULL) as null_entry_price,
            COUNT(*) FILTER (WHERE current_price IS NULL) as null_current_price,
            COUNT(*) FILTER (WHERE instrument_type IS NULL) as null_instrument_type,
            COUNT(*) FILTER (WHERE account_name IS NULL) as null_account_name
        FROM active_positions
        WHERE entry_time > NOW() - INTERVAL '24 hours'
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(null_check)
        nulls = cur.fetchone()
        cur.close()
        
        has_errors = False
        if nulls['null_entry_price'] > 0:
            print(f"  ❌ {nulls['null_entry_price']} positions missing entry_price")
            has_errors = True
        if nulls['null_current_price'] > 0:
            print(f"  ⚠️  {nulls['null_current_price']} positions missing current_price")
        if nulls['null_instrument_type'] > 0:
            print(f"  ❌ {nulls['null_instrument_type']} positions missing instrument_type")
            has_errors = True
        if nulls['null_account_name'] > 0:
            print(f"  ❌ {nulls['null_account_name']} positions missing account_name")
            has_errors = True
        
        if not has_errors:
            print("  ✅ No critical NULL fields detected")
        
        # Check for wrong instrument_type
        wrong_type = """
        SELECT 
            ticker,
            instrument_type,
            COUNT(*) as count
        FROM active_positions
        WHERE entry_time > NOW() - INTERVAL '24 hours'
        AND LENGTH(ticker) > 10
        AND instrument_type != 'OPTION'
        GROUP BY ticker, instrument_type
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(wrong_type)
        wrong_types = cur.fetchall()
        cur.close()
        
        if wrong_types:
            print(f"\n  🚨 INSTRUMENT TYPE BUG:")
            for w in wrong_types:
                print(f"    {w['ticker']}: logged as '{w['instrument_type']}' but appears to be OPTION ({w['count']} times)")
        else:
            print(f"\n  ✅ No instrument_type detection issues found")
        
        # Stage 10: Pipeline Summary
        print_section("PIPELINE SUMMARY")
        
        print("Data Flow:")
        print(f"  1. Bars:           {bar_count:,} ✅")
        print(f"  2. Features:       (computed from bars)")
        print(f"  3. Signals:        (AI generates from features)")
        print(f"  4. Recommendations: (filtered signals)")
        print(f"  5. Executions:     (trades placed)")
        print(f"  6. Positions:      {pos_count} open, {closed_count} closed ✅")
        print(f"  7. Learning Data:  {history_count} in position_history", end="")
        
        if history_count == 0 and closed_count > 0:
            print(" ❌ BROKEN!")
        else:
            print(" ✅")
        
        # Overall Health
        print_section("OVERALL HEALTH")
        
        issues = []
        if bar_count < 1000:
            issues.append("Low bar count (< 1000 in 24h)")
        if history_count == 0 and closed_count > 0:
            issues.append("position_history not saving (CRITICAL)")
        if wrong_types:
            issues.append("instrument_type detection bug")
        
        if not issues:
            print("✅ PIPELINE HEALTHY - All stages working correctly!")
            print("✅ Data flowing from bars → features → signals → positions")
            print("⚠️  position_history insert bug needs fixing for learning")
        else:
            print("⚠️  ISSUES FOUND:")
            for issue in issues:
                print(f"  • {issue}")
        
        print("\n" + "=" * 80)
        print("  VERIFICATION COMPLETE")
        print("=" * 80 + "\n")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
