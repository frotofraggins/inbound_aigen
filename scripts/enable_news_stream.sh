#!/bin/bash
# Enable News Stream Service
# Provides real-time news via Alpaca WebSocket API

set -e

echo "=========================================="
echo "ENABLING NEWS STREAM SERVICE"
echo "=========================================="

CLUSTER="ops-pipeline-cluster"
SERVICE="news-stream"
REGION="us-west-2"

echo ""
echo "Updating service to desired count = 1..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 1 \
  --region "$REGION"

echo ""
echo "✅ News stream service enabled!"
echo ""
echo "To verify it's running:"
echo "  aws ecs describe-services --cluster $CLUSTER --services $SERVICE --region $REGION"
echo ""
echo "To view logs:"
echo "  aws logs tail /ecs/ops-pipeline/news-stream --region $REGION --follow"
echo ""
echo "This service provides:"
echo "  - Real-time breaking news from Alpaca WebSocket"
echo "  - Professional sources: Benzinga, Reuters, etc."
echo "  - Instant article delivery (vs 1-min RSS delay)"
echo "  - Complements existing RSS feeds"
echo ""
