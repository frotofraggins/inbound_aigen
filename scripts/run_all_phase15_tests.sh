#!/bin/bash
#
# Phase 15 Master Test Runner
# Runs all tests for options trading foundation
#
# Prerequisites:
# 1. Set environment variables for Alpaca API
# 2. Set environment variables for database
# 3. Apply migration 008 to database
#

set -e  # Exit on error

echo "========================================================================"
echo "PHASE 15 OPTIONS TRADING - MASTER TEST SUITE"
echo "========================================================================"
echo ""
echo "This will run all tests for Phase 15A options trading foundation."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Function to run a test
run_test() {
    local test_name=$1
    local test_script=$2
    local required_env=$3
    
    echo ""
    echo "========================================================================"
    echo "Running: $test_name"
    echo "========================================================================"
    
    # Check if required environment variables are set
    if [ ! -z "$required_env" ]; then
        IFS=',' read -ra ENVVARS <<< "$required_env"
        for var in "${ENVVARS[@]}"; do
            if [ -z "${!var}" ]; then
                echo -e "${YELLOW}⚠️  SKIPPED: Missing environment variable $var${NC}"
                ((TESTS_SKIPPED++))
                return
            fi
        done
    fi
    
    # Run the test
    if python3 "$test_script"; then
        echo -e "${GREEN}✅ PASSED: $test_name${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ FAILED: $test_name${NC}"
        ((TESTS_FAILED++))
    fi
}

# Print environment check
echo "Checking environment..."
echo ""

if [ -z "$ALPACA_KEY_ID" ] || [ -z "$ALPACA_SECRET_KEY" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Alpaca API credentials not set${NC}"
    echo "  Set ALPACA_KEY_ID and ALPACA_SECRET_KEY to run options API tests"
fi

if [ -z "$DB_HOST" ] || [ -z "$DB_PASSWORD" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Database credentials not set${NC}"
    echo "  Set DB_HOST, DB_NAME, DB_USER, DB_PASSWORD to run database tests"
fi

echo ""
echo "Press ENTER to continue, or Ctrl+C to cancel..."
read

# Run Test 1: Options API Module
run_test \
    "Options API Module" \
    "scripts/test_options_api.py" \
    "ALPACA_KEY_ID,ALPACA_SECRET_KEY"

# Run Test 2: Database Migration 008
run_test \
    "Database Migration 008" \
    "scripts/test_migration_008.py" \
    "DB_HOST,DB_PASSWORD"

# Summary
echo ""
echo "========================================================================"
echo "TEST SUMMARY"
echo "========================================================================"
echo ""
echo -e "Total Tests:   $(($TESTS_PASSED + $TESTS_FAILED + $TESTS_SKIPPED))"
echo -e "${GREEN}Passed:        $TESTS_PASSED${NC}"
echo -e "${RED}Failed:        $TESTS_FAILED${NC}"
echo -e "${YELLOW}Skipped:       $TESTS_SKIPPED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ] && [ $TESTS_PASSED -gt 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo ""
    echo "Phase 15A foundation is ready for deployment."
    echo ""
    echo "Next steps:"
    echo "  1. Apply migration 008 to production database"
    echo "  2. Deploy updated dispatcher service to ECS"
    echo "  3. Monitor first options executions in CloudWatch"
    echo ""
    exit 0
elif [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}⚠️  SOME TESTS FAILED${NC}"
    echo ""
    echo "Please fix the failing tests before deploying."
    echo "Check the test output above for details."
    echo ""
    exit 1
else
    echo -e "${YELLOW}⚠️  NO TESTS RUN${NC}"
    echo ""
    echo "Make sure environment variables are set correctly."
    echo "See PHASE15_TESTING_GUIDE.md for details."
    echo ""
    exit 2
fi
