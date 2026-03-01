#!/bin/bash
# Test Alpaca API manually to diagnose telemetry issue

# Get keys from Secrets Manager
SECRET=$(aws secretsmanager get-secret-value --secret-id ops-pipeline/alpaca --region us-west-2 --query 'SecretString' --output text)
API_KEY=$(echo $SECRET | python3 -c "import sys, json; print(json.load(sys.stdin)['api_key'])")
API_SECRET=$(echo $SECRET | python3 -c "import sys, json; print(json.load(sys.stdin)['api_secret'])")

echo "Testing Alpaca Market Data API..."
echo "Endpoint: https://data.alpaca.markets/v2/stocks/AAPL/bars"
echo "Timeframe: 1Min"
echo ""

# Test API call for AAPL
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -H "APCA-API-KEY-ID: $API_KEY" \
  -H "APCA-API-SECRET-KEY: $API_SECRET" \
  "https://data.alpaca.markets/v2/stocks/AAPL/bars?timeframe=1Min&start=2026-02-16T15:00:00Z&end=2026-02-16T16:00:00Z&feed=iex&limit=10")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE/d')

echo "HTTP Status: $HTTP_CODE"
echo ""
echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
    BARS=$(echo "$BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('bars', [])))")
    echo "Bars returned: $BARS"
    
    if [ "$BARS" = "0" ]; then
        echo ""
        echo "❌ API returned 200 OK but 0 bars"
        echo "Possible causes:"
        echo "  - Market closed (bars only during market hours)"
        echo "  - Feed parameter issue"
        echo "  - Time range issue"
    else
        echo ""
        echo "✅ API working! Bars returned: $BARS"
    fi
else
    echo ""
    echo "❌ API Error - HTTP $HTTP_CODE"
    echo "Check response body above for error message"
fi
