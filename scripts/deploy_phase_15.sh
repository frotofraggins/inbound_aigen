#!/bin/bash
#
# Phase 15 Deployment Script
# Deploys options trading foundation to production
#
# This script:
# 1. Applies database migration 008
# 2. Builds and pushes Docker images
# 3. Updates ECS services
# 4. Verifies deployment
#

set -e  # Exit on error

echo "========================================================================"
echo "PHASE 15 OPTIONS TRADING - DEPLOYMENT"
echo "========================================================================"
echo ""
echo "This will deploy options trading foundation to production."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
AWS_REGION="us-west-2"
AWS_ACCOUNT="160027201036"
ECR_REPO="$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
CLUSTER_NAME="ops-pipeline-cluster"

# Verify prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

if [ -z "$DB_HOST" ] || [ -z "$DB_PASSWORD" ]; then
    echo -e "${RED}❌ Missing database credentials${NC}"
    echo "Set DB_HOST, DB_NAME, DB_USER, DB_PASSWORD"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not installed${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites OK${NC}"
echo ""

# Step 1: Apply Migration 008
echo "========================================================================"
echo "STEP 1: Apply Database Migration 008"
echo "========================================================================"
echo ""

echo "Applying migration to add options support..."
python3 scripts/apply_migration_008_direct.py

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Migration 008 applied successfully${NC}"
else
    echo -e "${RED}❌ Migration failed${NC}"
    exit 1
fi

echo ""
read -p "Press ENTER to continue to Docker builds, or Ctrl+C to cancel..."

# Step 2: Build and Push Dispatcher
echo ""
echo "========================================================================"
echo "STEP 2: Build and Push Dispatcher Image"
echo "========================================================================"
echo ""

echo "Building dispatcher image..."
cd services/dispatcher
docker build -t dispatcher:phase15 -t dispatcher:latest .

echo "Tagging for ECR..."
docker tag dispatcher:phase15 $ECR_REPO/dispatcher:phase15
docker tag dispatcher:latest $ECR_REPO/dispatcher:latest

echo "Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $ECR_REPO

echo "Pushing to ECR..."
docker push $ECR_REPO/dispatcher:phase15
docker push $ECR_REPO/dispatcher:latest

echo -e "${GREEN}✅ Dispatcher image pushed${NC}"
cd ../..

# Step 3: Build and Push Signal Engine
echo ""
echo "========================================================================"
echo "STEP 3: Build and Push Signal Engine Image"
echo "========================================================================"
echo ""

echo "Building signal engine image..."
cd services/signal_engine_1m
docker build -t signal-engine:phase15 -t signal-engine:latest .

echo "Tagging for ECR..."
docker tag signal-engine:phase15 $ECR_REPO/signal-engine:phase15
docker tag signal-engine:latest $ECR_REPO/signal-engine:latest

echo "Pushing to ECR..."
docker push $ECR_REPO/signal-engine:phase15
docker push $ECR_REPO/signal-engine:latest

echo -e "${GREEN}✅ Signal engine image pushed${NC}"
cd ../..

# Step 4: Update ECS Services
echo ""
echo "========================================================================"
echo "STEP 4: Update ECS Services"
echo "========================================================================"
echo ""

echo "Forcing new deployment of dispatcher..."
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service dispatcher-service \
    --force-new-deployment \
    --region $AWS_REGION

echo "Forcing new deployment of signal engine..."
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service signal-engine-service \
    --force-new-deployment \
    --region $AWS_REGION

echo -e "${GREEN}✅ ECS services updating${NC}"

# Step 5: Wait for deployments
echo ""
echo "========================================================================"
echo "STEP 5: Wait for Deployments"
echo "========================================================================"
echo ""

echo "Waiting for dispatcher deployment..."
aws ecs wait services-stable \
    --cluster $CLUSTER_NAME \
    --services dispatcher-service \
    --region $AWS_REGION

echo -e "${GREEN}✅ Dispatcher deployed${NC}"

echo "Waiting for signal engine deployment..."
aws ecs wait services-stable \
    --cluster $CLUSTER_NAME \
    --services signal-engine-service \
    --region $AWS_REGION

echo -e "${GREEN}✅ Signal engine deployed${NC}"

# Step 6: Verification
echo ""
echo "========================================================================"
echo "STEP 6: Verification"
echo "========================================================================"
echo ""

echo "Checking ECS task status..."
aws ecs list-tasks \
    --cluster $CLUSTER_NAME \
    --service-name dispatcher-service \
    --region $AWS_REGION

aws ecs list-tasks \
    --cluster $CLUSTER_NAME \
    --service-name signal-engine-service \
    --region $AWS_REGION

echo ""
echo "Checking recent logs (last 5 minutes)..."
echo "Dispatcher logs:"
aws logs tail /ecs/dispatcher --since 5m --region $AWS_REGION | head -20

echo ""
echo "Signal engine logs:"
aws logs tail /ecs/signal-engine-1m --since 5m --region $AWS_REGION | head -20

# Step 7: Verification Queries
echo ""
echo "========================================================================"
echo "STEP 7: Database Verification"
echo "========================================================================"
echo ""

echo "Querying for options recommendations..."
python3 -c "
import psycopg2
import os

conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    database=os.environ.get('DB_NAME', 'ops_pipeline'),
    user=os.environ.get('DB_USER', 'ops_user'),
    password=os.environ['DB_PASSWORD']
)

cur = conn.cursor()

# Check for options recommendations
cur.execute('''
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE instrument_type = 'CALL') as calls,
        COUNT(*) FILTER (WHERE instrument_type = 'PUT') as puts,
        COUNT(*) FILTER (WHERE strategy_type = 'day_trade') as day_trades,
        COUNT(*) FILTER (WHERE strategy_type = 'swing_trade') as swing_trades
    FROM dispatch_recommendations
    WHERE created_at >= CURRENT_DATE;
''')

row = cur.fetchone()
print(f'Today\\'s recommendations:')
print(f'  Total: {row[0]}')
print(f'  CALLs: {row[1]}')
print(f'  PUTs: {row[2]}')
print(f'  Day trades: {row[3]}')
print(f'  Swing trades: {row[4]}')

# Check for options executions
cur.execute('''
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE instrument_type = 'CALL') as calls,
        COUNT(*) FILTER (WHERE instrument_type = 'PUT') as puts
    FROM dispatch_executions
    WHERE simulated_ts >= CURRENT_DATE;
''')

row = cur.fetchone()
print(f'\\nToday\\'s executions:')
print(f'  Total: {row[0]}')
print(f'  CALLs: {row[1]}')
print(f'  PUTs: {row[2]}')

conn.close()
"

# Final Summary
echo ""
echo "========================================================================"
echo "DEPLOYMENT COMPLETE"
echo "========================================================================"
echo ""
echo -e "${GREEN}✅ Phase 15 deployed successfully!${NC}"
echo ""
echo "What was deployed:"
echo "  ✅ Migration 008 (options columns + strategy_type)"
echo "  ✅ Updated dispatcher (options execution)"
echo "  ✅ Updated signal engine (options signals)"
echo ""
echo "Monitoring checklist:"
echo "  1. Check CloudWatch logs for both services"
echo "  2. Monitor for OPTIONS signals in recommendations"
echo "  3. Watch for first options execution"
echo "  4. Query active_options_positions view"
echo "  5. Verify no errors in execution flow"
echo ""
echo "Next steps:"
echo "  - Wait for strong market signals (confidence >= 0.7 + volume_ratio >= 3.0)"
echo "  - Watch for first CALL or PUT recommendation"
echo "  - Verify options execution writes to database correctly"
echo "  - Collect 5-10 options trades for initial validation"
echo ""
echo "Documentation:"
echo "  - Status: deploy/PHASE_15A_OPTIONS_FOUNDATION_STATUS.md"
echo "  - Testing: deploy/PHASE15_TESTING_GUIDE.md"
echo "  - Main plan: deploy/PHASE_15_OPTIONS_AND_DUAL_TIMEFRAME.md"
echo ""
