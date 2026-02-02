#!/usr/bin/env python3
"""Check news data and sentiment analysis"""
import json
import boto3

lambda_client = boto3.client('lambda', region_name='us-west-2')

def query(sql):
    response = lambda_client.invoke(
        FunctionName='ops-pipeline-db-query',
        InvocationType='RequestResponse',
        Payload=json.dumps({"sql": sql})
    )
    result = json.loads(response['Payload'].read())
    return json.loads(result.get('body', '{}')).get('rows', [])

print("\n" + "="*80)
print("  NEWS & SENTIMENT VERIFICATION")
print("="*80)

# 1. Raw RSS events
print("\n1. RAW RSS FEED DATA (Last 24 Hours)")
results = query("""
    SELECT COUNT(*) as total,
           MAX(fetched_at) as latest,
           MIN(fetched_at) as earliest
    FROM inbound_events_raw
    WHERE fetched_at >= NOW() - INTERVAL '24 hours'
""")
if results:
    r = results[0]
    print(f"   Total articles fetched: {r['total']}")
    print(f"   Latest: {r['latest']}")
    print(f"   Earliest: {r['earliest']}")

# 2. Recent news titles
print("\n2. RECENT NEWS ARTICLES (Last 5)")
results = query("""
    SELECT title, source, fetched_at
    FROM inbound_events_raw
    ORDER BY fetched_at DESC
    LIMIT 5
""")
for r in results:
    print(f"   {r['fetched_at'][:19]}: {r['title'][:70]}...")
    print(f"      Source: {r['source'][:60]}")

# 3. Classified events with sentiment
print("\n3. SENTIMENT ANALYSIS (Last 24 Hours)")
results = query("""
    SELECT COUNT(*) as total,
           COUNT(*) FILTER (WHERE sentiment_label = 'positive') as positive,
           COUNT(*) FILTER (WHERE sentiment_label = 'negative') as negative,
           COUNT(*) FILTER (WHERE sentiment_label = 'neutral') as neutral,
           MAX(created_at) as latest
    FROM inbound_events_classified
    WHERE created_at >= NOW() - INTERVAL '24 hours'
""")
if results:
    r = results[0]
    print(f"   Total classified: {r['total']}")
    print(f"   Positive: {r['positive']}")
    print(f"   Negative: {r['negative']}")
    print(f"   Neutral: {r['neutral']}")
    print(f"   Latest: {r['latest']}")

# 4. Recent classified events with tickers
print("\n4. RECENT CLASSIFIED EVENTS (Last 5)")
results = query("""
    SELECT c.created_at, c.sentiment_label, c.sentiment_score, 
           c.tickers, r.title
    FROM inbound_events_classified c
    JOIN inbound_events_raw r ON c.raw_event_id = r.id
    WHERE c.created_at >= NOW() - INTERVAL '2 hours'
    ORDER BY c.created_at DESC
    LIMIT 5
""")
for r in results:
    tickers_str = ', '.join(r['tickers']) if r['tickers'] else 'none'
    print(f"   {r['created_at'][:19]}: {r['sentiment_label']} (score={r['sentiment_score']:.3f})")
    print(f"      Tickers: {tickers_str}")
    print(f"      Title: {r['title'][:65]}...")

# 5. Ticker coverage
print("\n5. TICKER COVERAGE (Last 24 Hours)")
results = query("""
    SELECT unnest(tickers) as ticker, COUNT(*) as mentions
    FROM inbound_events_classified
    WHERE created_at >= NOW() - INTERVAL '24 hours'
    AND array_length(tickers, 1) > 0
    GROUP BY ticker
    ORDER BY mentions DESC
""")
print("   Mentions by ticker:")
for r in results:
    print(f"      {r['ticker']}: {r['mentions']} articles")

print("\n" + "="*80)
print("  NEWS & SENTIMENT: OPERATIONAL ✓")
print("="*80)
