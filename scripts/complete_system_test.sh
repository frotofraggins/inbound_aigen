#!/bin/bash
# Complete System Test - February 4, 2026
# Tests all components after exit fix deployment

echo "======================================================================"
echo "COMPLETE SYSTEM TEST - Post-Deployment Verification"
echo "======================================================================"
echo "Time: $(date)"
echo ""

AWS_REGION="us-west-2"

echo "Step 1: Verify all services are running..."
echo "----------------------------------------------------------------------"
aws ecs describe-services --cluster ops-pipeline-cluster \
  --services position-manager-service dispatcher-service dispatcher-tiny-service \
  --region $AWS_REGION \
  --query 'services[].{name:serviceName,status:deployments[0].rolloutState,running:runningCount}' \
  --output table

echo ""
echo "Step 2: Check position manager is using 1-minute interval..."
echo "----------------------------------------------------------------------"
echo "Looking for 'Sleeping for 1 minute' in logs..."
aws logs tail /ecs/ops-pipeline/position-manager --since 2m --region $AWS_REGION 2>&1 | grep -i "sleeping" | tail -3

if [ $? -eq 0 ]; then
    echo "✅ Position manager logs found"
else
    echo "⚠️ No recent position manager logs - service may be starting up"
fi

echo ""
echo "Step 3: Check dispatcher is not using bracket orders..."
echo "----------------------------------------------------------------------"
echo "Looking for 'order_class' in dispatcher logs..."
aws logs tail /ecs/ops-pipeline/dispatcher --since 2m --region $AWS_REGION 2>&1 | grep -i "order_class" | tail -3

echo ""
echo "Step 4: Check for any open positions in Alpaca..."
echo "----------------------------------------------------------------------"
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({'sql': 'SELECT COUNT(*) as count FROM active_positions WHERE status = \'open\''})
)
result = json.loads(json.load(response['Payload'])['body'])
count = result.get('rows', [{}])[0].get('count', 0)
print(f"Open positions in database: {count}")
EOF

echo ""
echo "Step 5: Check recent executions were saved..."
echo "----------------------------------------------------------------------"
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')
response = client.invoke(
    FunctionName='ops-pipeline-db-query',
    Payload=json.dumps({
        'sql': """
        SELECT ticker, instrument_type, created_at, execution_mode
        FROM dispatch_executions
        WHERE created_at > NOW() - INTERVAL '1 hour'
        ORDER BY created_at DESC
        LIMIT 5
        """
    })
)
result = json.loads(json.load(response['Payload'])['body'])
rows = result.get('rows', [])
if rows:
    print(f"Found {len(rows)} recent executions:")
    for row in rows:
        print(f"  {row['ticker']} {row.get('instrument_type', 'STOCK')} - {row['created_at']} ({row['execution_mode']})")
else:
    print("⚠️ No executions in last hour")
EOF

echo ""
echo "Step 6: Data pipeline health check..."
echo "----------------------------------------------------------------------"
python3 << 'EOF'
import boto3, json
client = boto3.client('lambda', region_name='us-west-2')

# Check each component
checks = [
    ("RSS Events (24h)", "SELECT COUNT(*) as c FROM inbound_events_raw WHERE created_at > NOW() - INTERVAL '24 hours'"),
    ("Classified Events (24h)", "SELECT COUNT(*) as c FROM inbound_events_classified WHERE created_at > NOW() - INTERVAL '24 hours'"),
    ("Telemetry Bars (6h)", "SELECT COUNT(*) as c FROM lane_telemetry WHERE ts > NOW() - INTERVAL '6 hours'"),
    ("Features (6h)", "SELECT COUNT(*) as c FROM lane_features WHERE computed_at > NOW() - INTERVAL '6 hours'"),
    ("Signals (24h)", "SELECT COUNT(*) as c FROM dispatch_recommendations WHERE created_at > NOW() - INTERVAL '24 hours'"),
]

for name, sql in checks:
    response = client.invoke(
        FunctionName='ops-pipeline-db-query',
        Payload=json.dumps({'sql': sql})
    )
    result = json.loads(json.load(response['Payload'])['body'])
    count = result.get('rows', [{}])[0].get('c', 0)
    status = "✅" if count > 0 else "❌"
    print(f"{status} {name}: {count}")
EOF

echo ""
echo "======================================================================"
echo "Test Complete"
echo "======================================================================"
echo ""
echo "Next: Monitor for new positions with:"
echo "  python3 scripts/monitor_exit_fix.py"
echo ""
echo "Or watch logs:"
echo "  aws logs tail /ecs/ops-pipeline/dispatcher --follow --region us-west-2"
echo "  aws logs tail /ecs/ops-pipeline/position-manager --follow --region us-west-2"
echo ""
