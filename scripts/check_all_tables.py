#!/usr/bin/env python3
import json
import boto3

lambda_client = boto3.client('lambda', region_name='us-west-2')

def run_query(name, sql):
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps({"sql": sql})
        )
        result = json.loads(response['Payload'].read())
        body = json.loads(result.get('body', '{}'))
        return body
    except Exception as e:
        return {"error": str(e)}

print("\n=== Checking All Tables ===\n")

# 1. Recommendations table
print("1. RECOMMENDATIONS TABLE")
result = run_query("recs", "SELECT * FROM dispatch_recommendations LIMIT 1")
if 'error' in result:
    print(f"   Error: {result['error']}")
elif result.get('rows'):
    print(f"   Columns: {list(result['rows'][0].keys())}")
    print(f"   Sample: {result['rows'][0]}")
else:
    print("   Table exists but empty (or wrong query)")

# Check total count
result2 = run_query("recs_count", "SELECT COUNT(*) as count FROM dispatch_recommendations")
print(f"   Total rows: {result2.get('rows', [{}])[0].get('count', 'unknown')}")

# 2. Classifier table  
print("\n2. CLASSIFIER TABLE")
result = run_query("classifier", "SELECT * FROM inbound_events_classified LIMIT 1")
if 'error' in result:
    print(f"   Error: {result['error']}")
elif result.get('rows'):
    print(f"   Columns: {list(result['rows'][0].keys())}")
else:
    print("   Table exists but empty")

result2 = run_query("classifier_count", "SELECT COUNT(*) as count FROM inbound_events_classified")
print(f"   Total rows: {result2.get('rows', [{}])[0].get('count', 'unknown')}")

# 3. Executions table
print("\n3. EXECUTIONS TABLE")
result = run_query("exec", "SELECT * FROM dispatch_executions LIMIT 1")
if 'error' in result:
    print(f"   Error: {result['error']}")
    # Table might not exist - check
    result_alt = run_query("exec_alt", """
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema='public' AND table_name LIKE '%exec%' OR table_name LIKE '%dispatch%'
    """)
    print(f"   Available tables: {result_alt.get('rows', [])}")
elif result.get('rows'):
    print(f"   Columns: {list(result['rows'][0].keys())}")
else:
    print("   Table exists but empty")

print("\n=== Schema Check ===")
result = run_query("tables", """
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema='public' 
    ORDER BY table_name
""")
print("All tables:")
for row in result.get('rows', []):
    print(f"   - {row['table_name']}")
