#!/bin/bash
# Deploy Position Manager - Phase 15C
# This script deploys migration 009 and the Position Manager service

set -e

echo "========================================"
echo "Phase 15C: Position Manager Deployment"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

#
# Step 1: Deploy Migration Lambda
#
echo -e "${YELLOW}Step 1: Deploying Migration Lambda with Migration 009...${NC}"
cd services/db_migration_lambda

# Package Lambda
if [ -d "package" ]; then
    rm -rf package
fi
mkdir -p package
pip install -r requirements.txt -t package/ --quiet
cp lambda_function.py package/
cd package
zip -r ../migration_lambda.zip . -q
cd ..

# Deploy Lambda
echo "Updating Lambda function..."
aws lambda update-function-code \
    --function-name ops-pipeline-db-migration \
    --zip-file fileb://migration_lambda.zip \
    --region us-west-2 > /dev/null

echo -e "${GREEN}✓ Lambda deployed${NC}"
echo ""

# Wait for Lambda to be ready
echo "Waiting for Lambda to be ready..."
sleep 5

#
# Step 2: Apply Migration 009
#
echo -e "${YELLOW}Step 2: Applying Migration 009...${NC}"
cd ../..
MIGRATION_RESULT=$(aws lambda invoke \
    --function-name ops-pipeline-db-migration \
    --region us-west-2 \
    --output json \
    /tmp/migration_response.json 2>&1)

if [ -f "/tmp/migration_response.json" ]; then
    cat /tmp/migration_response.json | python3 -m json.tool
    echo ""
    echo -e "${GREEN}✓ Migration 009 applied${NC}"
else
    echo -e "${RED}✗ Migration failed${NC}"
    exit 1
fi
echo ""

#
# Step 3: Build Position Manager Docker Image
#
echo -e "${YELLOW}Step 3: Building Position Manager Docker image...${NC}"
docker build -f services/position_manager/Dockerfile -t position-manager:latest .
echo -e "${GREEN}✓ Docker image built${NC}"
echo ""

#
# Step 4: Push to ECR
#
echo -e "${YELLOW}Step 4: Pushing to ECR...${NC}"

# Login to ECR
aws ecr get-login-password --region us-west-2 | \
    docker login --username AWS --password-stdin \
    160027201036.dkr.ecr.us-west-2.amazonaws.com

# Tag image
docker tag position-manager:latest \
    160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

# Push image
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

echo -e "${GREEN}✓ Image pushed to ECR${NC}"
echo ""

echo "========================================"
echo -e "${GREEN}Deployment Complete!${NC}"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Verify migration: Check the query output above"
echo "2. Register ECS task definition (see deploy/PHASE_15C_POSITION_MANAGER_READY.md)"
echo "3. Configure EventBridge schedule"
echo "4. Monitor CloudWatch logs: /ecs/ops-pipeline/position-manager"
echo ""
