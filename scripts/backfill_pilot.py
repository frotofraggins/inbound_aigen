#!/usr/bin/env python3
"""
Pilot Historical Data Backfill
Loads last 3 trading days for top 10 AI-recommended tickers
"""
import boto3
import json
import psycopg2
from datetime import datetime, timedelta
from alpaca_trade_api.rest import REST, TimeFrame

def load_config():
    """Load credentials from AWS"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    # Database
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    secret_data = json.loads(secrets.get_secret_value(SecretId='ops-pipeline/db')['SecretString'])
    
    # Alpaca
    alpaca_secret = json.loads(secrets.get_secret_value(SecretId='ops-pipeline/alpaca-paper')['SecretString'])
    
    # Get top 10 AI tickers
    tickers_raw = ssm.get_parameter(Name='/ops-pipeline/tickers')['Parameter']['Value']
    tickers = tickers_raw.split(',')[:10]  # Top 10 only for pilot
    
    return {
        'db': {
            'host': db_host,
            'database': db_name,
            'user': secret_data['username'],
            'password': secret_data['password']
        },
        'alpaca': {
            'key_id': alpaca_secret['key_id'],
            'secret_key': alpaca_secret['secret_key']
        },
        'tickers': tickers
    }

def backfill_ticker(api, ticker, start_date, end_date, conn):
    """Backfill historical bars for one ticker"""
    print(f"\n📥 Backfilling {ticker}...")
    
    try:
        # Get 1-minute bars from Alpaca
        bars = api.get_bars(
            ticker,
            TimeFrame.Minute,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            limit=10000
        ).df
        
        if bars.empty:
            print(f"  ⚠️ No data returned for {ticker}")
            return 0
        
        # Reset index to get timestamp as column
        bars = bars.reset_index()
        
        # Insert into database
        cur = conn.cursor()
        inserted = 0
        
        for _, row in bars.iterrows():
            try:
                cur.execute("""
                    INSERT INTO lane_telemetry (ticker, ts, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, ts) DO NOTHING
                """, (
                    ticker,
                    row['timestamp'],
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close']),
                    int(row['volume'])
                ))
                inserted += 1
            except Exception as e:
                print(f"  Error inserting bar: {e}")
                continue
        
        conn.commit()
        cur.close()
        
        print(f"  ✅ {ticker}: {inserted} bars inserted ({len(bars)} total)")
        return inserted
        
    except Exception as e:
        print(f"  ❌ {ticker} failed: {e}")
        return 0

def main():
    print("=" * 60)
    print("PHASE 14: HISTORICAL DATA BACKFILL - PILOT")
    print("=" * 60)
    print("\nLoading configuration...")
    
    config = load_config()
    
    print(f"✅ Top 10 AI tickers: {', '.join(config['tickers'])}")
    print(f"✅ Database: {config['db']['host']}")
    
    # Initialize Alpaca API
    print("\n📡 Connecting to Alpaca...")
    api = REST(
        config['alpaca']['key_id'],
        config['alpaca']['secret_key'],
        base_url='https://paper-api.alpaca.markets'
    )
    print("✅ Connected to Alpaca Paper API")
    
    # Connect to database
    print("\n💾 Connecting to database...")
    conn = psycopg2.connect(**config['db'])
    print("✅ Connected to database")
    
    # Backfill last 3 trading days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=4)  # 4 days to ensure 3 trading days
    
    print(f"\n📅 Backfill period:")
    print(f"  Start: {start_date.strftime('%Y-%m-%d %H:%M')} ")
    print(f"  End:   {end_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Duration: ~3 trading days")
    
    # Backfill each ticker
    total_bars = 0
    for ticker in config['tickers']:
        bars_inserted = backfill_ticker(api, ticker, start_date, end_date, conn)
        total_bars += bars_inserted
    
    conn.close()
    
    print("\n" + "=" * 60)
    print(f"✅ BACKFILL COMPLETE")
    print("=" * 60)
    print(f"Total bars inserted: {total_bars:,}")
    print(f"Tickers processed: {len(config['tickers'])}")
    print(f"Average per ticker: {total_bars // len(config['tickers']):,}")
    
    print("\n📊 Next Steps:")
    print("1. Run feature_computer_1m on historical data")
    print("2. Analyze historical volume surges")
    print("3. Use Bedrock to identify patterns")
    print("4. Optimize signal thresholds")
    
    print("\n💡 To compute features on historical data:")
    print("   python scripts/compute_historical_features.py")

if __name__ == '__main__':
    main()
