#!/bin/bash
# Test Alpaca API Credentials
# Tests both Trading API and Data API for each account

set -e

REGION="us-west-2"

echo "=================================="
echo "ALPACA API CREDENTIAL TEST"
echo "=================================="
echo ""

# Function to test credentials
test_account() {
    local SECRET_NAME=$1
    local ACCOUNT_NAME=$2
    
    echo "Testing: $ACCOUNT_NAME ($SECRET_NAME)"
    echo "-----------------------------------"
    
    # Get credentials
    SECRET=$(aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --region "$REGION" --query 'SecretString' --output text 2>&1)
    
    if echo "$SECRET" | grep -q "ResourceNotFoundException"; then
        echo "❌ Secret not found: $SECRET_NAME"
        echo ""
        return 1
    fi
    
    API_KEY=$(echo "$SECRET" | jq -r '.api_key // .APCA_API_KEY_ID // empty')
    API_SECRET=$(echo "$SECRET" | jq -r '.api_secret // .APCA_API_SECRET_KEY // empty')
    
    if [ -z "$API_KEY" ] || [ -z "$API_SECRET" ]; then
        echo "❌ Invalid secret format (missing api_key or api_secret)"
        echo ""
        return 1
    fi
    
    echo "API Key: ${API_KEY:0:20}..."
    
    # Test 1: Trading API - Get Account
    echo ""
    echo "Test 1: Trading API - GET /v2/account"
    ACCOUNT_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "APCA-API-KEY-ID: $API_KEY" \
        -H "APCA-API-SECRET-KEY: $API_SECRET" \
        "https://paper-api.alpaca.markets/v2/account")
    
    HTTP_CODE=$(echo "$ACCOUNT_RESPONSE" | tail -1)
    BODY=$(echo "$ACCOUNT_RESPONSE" | head -n -1)
    
    if [ "$HTTP_CODE" == "200" ]; then
        ACCOUNT_NUM=$(echo "$BODY" | jq -r '.account_number')
        BUYING_POWER=$(echo "$BODY" | jq -r '.buying_power')
        CASH=$(echo "$BODY" | jq -r '.cash')
        echo "✅ Trading API Working"
        echo "   Account: $ACCOUNT_NUM"
        echo "   Buying Power: \$$BUYING_POWER"
        echo "   Cash: \$$CASH"
    elif [ "$HTTP_CODE" == "401" ]; then
        echo "❌ Trading API - Unauthorized (credentials invalid or expired)"
    else
        echo "❌ Trading API - HTTP $HTTP_CODE"
        echo "   Response: ${BODY:0:100}"
    fi
    
    # Test 2: Data API - Get Latest Bar
    echo ""
    echo "Test 2: Data API - GET /v2/stocks/SPY/bars"
    DATA_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "APCA-API-KEY-ID: $API_KEY" \
        -H "APCA-API-SECRET-KEY: $API_SECRET" \
        "https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Min&limit=1")
    
    HTTP_CODE=$(echo "$DATA_RESPONSE" | tail -1)
    BODY=$(echo "$DATA_RESPONSE" | head -n -1)
    
    if [ "$HTTP_CODE" == "200" ]; then
        BAR_COUNT=$(echo "$BODY" | jq -r '.bars | length')
        echo "✅ Data API Working"
        echo "   Bars returned: $BAR_COUNT"
        if [ "$BAR_COUNT" -gt 0 ]; then
            LAST_CLOSE=$(echo "$BODY" | jq -r '.bars[0].c')
            echo "   SPY last close: \$$LAST_CLOSE"
        fi
    elif [ "$HTTP_CODE" == "401" ]; then
        echo "❌ Data API - Unauthorized (credentials invalid or expired)"
    else
        echo "❌ Data API - HTTP $HTTP_CODE"
        echo "   Response: ${BODY:0:100}"
    fi
    
    # Test 3: Options API - Get Option Chain
    echo ""
    echo "Test 3: Options API - GET /v1beta1/options/snapshots/SPY"
    OPTIONS_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "APCA-API-KEY-ID: $API_KEY" \
        -H "APCA-API-SECRET-KEY: $API_SECRET" \
        "https://data.alpaca.markets/v1beta1/options/snapshots/SPY?limit=5")
    
    HTTP_CODE=$(echo "$OPTIONS_RESPONSE" | tail -1)
    BODY=$(echo "$OPTIONS_RESPONSE" | head -n -1)
    
    if [ "$HTTP_CODE" == "200" ]; then
        CONTRACT_COUNT=$(echo "$BODY" | jq -r '.snapshots | length')
        echo "✅ Options API Working"
        echo "   Contracts returned: $CONTRACT_COUNT"
    elif [ "$HTTP_CODE" == "401" ]; then
        echo "❌ Options API - Unauthorized (credentials invalid or expired)"
    elif [ "$HTTP_CODE" == "403" ]; then
        echo "⚠️  Options API - Forbidden (may need upgraded Alpaca plan)"
    else
        echo "❌ Options API - HTTP $HTTP_CODE"
        echo "   Response: ${BODY:0:100}"
    fi
    
    echo ""
    echo ""
}

# Test both accounts
test_account "ops-pipeline/alpaca" "DEFAULT/LARGE Account"
test_account "ops-pipeline/alpaca/tiny" "TINY Account"

echo "=================================="
echo "SUMMARY"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. If credentials expired: Update in Secrets Manager"
echo "2. If working: System ready to trade"
echo "3. Check dispatcher logs for which account it's using"
echo ""
echo "To check active account:"
echo "  aws logs tail /ecs/ops-pipeline/dispatcher --region us-west-2 --since 5m | grep 'account_name\\|api_key'"
echo ""
