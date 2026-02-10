#!/bin/bash
# Deploy Risk State Machine - SAFE ROLLOUT
# Phase 1: Database only, feature DISABLED by default

set -e

echo "=========================================="
echo "DEPLOYING RISK STATE MACHINE"
echo "Phase 1: Database Migration Only"
echo "Feature Flag: DISABLED (safe deployment)"
echo "=========================================="

REGION="us-west-2"
CLUSTER="ops-pipeline-cluster"

echo ""
echo "Step 1: Rebuild db-migrator with new migration..."
cd /home/nflos/workplace/inbound_aigen

docker build --no-cache \
  -f services/db_migrator/Dockerfile \
  -t 160027201036.dkr.ecr.${REGION}.amazonaws.com/ops-pipeline/db-migrator:latest .

echo ""
echo "Step 2: Push to ECR..."
aws ecr get-login-password --region ${REGION} | \
  docker login --username AWS --password-stdin 160027201036.dkr.ecr.${REGION}.amazonaws.com

docker push 160027201036.dkr.ecr.${REGION}.amazonaws.com/ops-pipeline/db-migrator:latest

echo ""
echo "Step 3: Run migration task..."
TASK_ARN=$(aws ecs run-task \
  --cluster ${CLUSTER} \
  --task-definition ops-pipeline-db-migrator \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c182a149eeef918a],securityGroups=[sg-0cd16a909f4e794ce],assignPublicIp=ENABLED}" \
  --region ${REGION} \
  --query 'tasks[0].taskArn' \
  --output text)

echo "Migration task started: ${TASK_ARN}"
echo ""
echo "Step 4: Waiting for migration to complete (30 seconds)..."
sleep 30

echo ""
echo "Step 5: Check migration logs..."
aws logs tail /ecs/ops-pipeline/db-migrator --since 2m --region ${REGION}

echo ""
echo "=========================================="
echo "DATABASE MIGRATION COMPLETE"
echo "=========================================="
echo ""
echo "✅ New columns added to active_positions:"
echo "   - lifecycle_state (default: OPEN)"
echo "   - peak_price, trail_price, trail_level"
echo "   - partial_taken, breakeven_armed"
echo "   - state transition tracking"
echo ""
echo "✅ New tables created:"
echo "   - position_state_history (audit log)"
echo "   - trade_management_config (settings)"
echo ""
echo "✅ Feature flag status: DISABLED"
echo "   (System still using legacy exit logic)"
echo ""
echo "Next steps:"
echo "  1. Verify migration succeeded (check logs above)"
echo "  2. Deploy position manager code (feature still OFF)"
echo "  3. Test with paper trading"
echo "  4. Enable feature flag when ready"
echo ""
echo "To verify schema:"
echo "  python3 scripts/check_database_tables.py"
echo ""
