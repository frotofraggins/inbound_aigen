#!/bin/bash
# Test different Alpaca feed parameters to find what works

SECRET=$(aws secretsmanager get-secret-value --secret-id ops-pipeline/alpaca --region us-west-2 --query 'SecretString' --output text)
API_KEY=$(echo $SECRET | python3 -c "import sys, json; print(json.load(sys.stdin)['api_key'])")
API_SECRET=$(echo $SECRET | python3 -c "import sys, json; print(json.load(sys.stdin)['api_secret'])")

# Current time for testing
END=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
START=$(date -u -d "1 hour ago" +'%Y-%m-%dT%H:%M:%SZ')

echo "Testing Alpaca API with different feed parameters"
echo "Time range: $START to $END"
echo "="
