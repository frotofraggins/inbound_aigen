#!/bin/bash
# Run Pattern Analysis on Historical Trades
# Author: AI System Owner
# Date: 2026-02-07

set -e

REGION="us-west-2"
ACCOUNT_ID="160027201036"
ECR_REPO="ops-pipeline/pattern-analyzer"
CLUSTER_NAME="ops-pipeline-cluster"

echo "========================================"
echo "Historical Pattern Analyzer"
echo "========================================"

# Parse arguments
DAYS=30
if [ $# -gt 0 ]; then
    DAYS=$1
fi

echo "Analyzing last $DAYS days of trades..."
echo ""

# Option 1: Run locally (if Docker installed)
if command -v docker &> /dev/null; then
    echo "Option 1: Running locally with Docker..."
    cd services/pattern_analyzer
    
    # Build image
    docker build -t pattern-analyzer:local .
    
    # Run analysis
    docker run --rm \
        -e AWS_DEFAULT_REGION=us-west-2 \
        -e AWS_ACCESS_KEY_ID \
        -e AWS_SECRET_ACCESS_KEY \
        -e AWS_SESSION_TOKEN \
        pattern-analyzer:local --days $DAYS
    
    cd ../..
else
    echo "Docker not found. To run analysis:"
    echo ""
    echo "1. Install dependencies:"
    echo "   cd services/pattern_analyzer"
    echo "   pip install -r requirements.txt"
    echo ""
    echo "2. Run analyzer:"
    echo "   python main.py --days $DAYS"
    echo ""
fi

echo ""
echo "========================================"
echo "Analysis complete!"
echo "========================================"
