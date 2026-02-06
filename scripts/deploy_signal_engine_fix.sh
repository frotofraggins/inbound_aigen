#!/bin/bash
# Deploy signal engine with emergency quality improvements
# Fix: Tighten thresholds to prevent catastrophic losses

set -e

echo "🚨 DEPLOYING EMERGENCY SIGNAL ENGINE FIX"
echo "Fixes: Higher confidence (0.75), stronger volume (2.0x), block first hour"
echo ""

# Build and push signal-engine image
cd services/signal_engine_1m

echo "🔨 Building new Docker image..."
docker build -t 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest .

echo "🔑 Logging in to ECR..."
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com

echo "📤 Pushing image to ECR..."
docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/signal-engine-1m:latest

echo "✅ Docker image pushed"

echo ""
echo "🚀 Deploying signal-engine..."
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service signal-engine-1m \
  --force-new-deployment \
  --region us-west-2

echo "✅ Signal engine deployment initiated"

echo ""
echo "✅ DEPLOYMENT COMPLETE"
echo ""
echo "Changes:"
echo "  - Confidence: 0.60 → 0.75 (only trade STRONG signals)"
echo "  - Volume: 1.2x → 2.0x (require stronger confirmation)"
echo "  - First hour: BLOCKED (9:30-10:30 AM ET)"
echo ""
echo "Expected: FAR fewer trades, but much higher quality"
echo "Goal: Stop -50% losses in 10 minutes!"
