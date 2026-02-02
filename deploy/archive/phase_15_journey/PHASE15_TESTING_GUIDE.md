# Phase 15 Options Trading - Testing Guide

**Last Updated:** 2026-01-26  
**Status:** Ready for Testing

## Overview

This guide explains how to test the Phase 15 options trading foundation before deploying to production. All components must pass tests before deployment.

## Test Suite Components

### 1. Options API Module Test (`scripts/test_options_api.py`)
Tests the core options trading logic without requiring database.

**Tests:**
1. API Connection - Verifies Alpaca API credentials work
2. Fetch Option Chain - Tests fetching real option contracts
3. Strike Selection - Validates strike selection logic (ATM/OTM/ITM)
4. Liquidity Validation - Tests volume and spread checks
5. Position Sizing - Validates position size calculations
6. Symbol Formatting - Tests OCC symbol generation

**Duration:** ~30 seconds  
**Requirements:** Alpaca API credentials

### 2. Database Migration Test (`scripts/test_migration_008.py`)
Tests the database schema changes for options trading.

**Tests:**
1. New Columns Exist - Verifies 10 new columns added
2. Indexes Exist - Validates 3 new indexes created
3. Views Exist - Confirms 3 analytical views created
4. Options Constraint Works - Tests data integrity rules
5. Views Can Be Queried - Ensures views are functional
6. Backward Compatibility - Confirms stock trading still works

**Duration:** ~10 seconds  
**Requirements:** Database access, migration 008 applied

### 3. Master Test Runner (`scripts/run_all_phase15_tests.sh`)
Orchestrates all tests with proper error handling and reporting.

**Features:**
- Environment validation
- Colored output
- Clear pass/fail indicators
- Summary report
- Exit codes for CI/CD

## Prerequisites

### Environment Variables

**For Options API Tests:**
```bash
export ALPACA_KEY_ID="your_alpaca_key"
export ALPACA_SECRET_KEY="your_alpaca_secret"
```

Get these from SSM Parameter Store:
```bash
# On AWS (with proper IAM permissions)
aws ssm get-parameter --name /ops-pipeline/alpaca_key_id --with-decryption --region us-west-2
aws ssm get-parameter --name /ops-pipeline/alpaca_secret_key --with-decryption --region us-west-2
```

**For Database Tests:**
```bash
export DB_HOST="your-rds-endpoint.rds.amazonaws.com"
export DB_PORT="5432"
export DB_NAME="ops_pipeline"
export DB_USER="ops_user"
export DB_PASSWORD="your_db_password"
```

### Database Preparation

Migration 008 must be applied before running database tests:

```bash
# Set environment variables first (see above)

# Apply migration
python3 scripts/apply_migration_008_direct.py
```

Expected output:
```
✅ Migration 008 applied successfully!
New columns added: 10
New indexes created: 3
New views created: 3
```

## Running Tests

### Option 1: Run All Tests (Recommended)

```bash
# Make scripts executable (first time only)
chmod +x scripts/run_all_phase15_tests.sh
chmod +x scripts/test_options_api.py
chmod +x scripts/test_migration_008.py

# Set environment variables
export ALPACA_KEY_ID="..."
export ALPACA_SECRET_KEY="..."
export DB_HOST="..."
export DB_PASSWORD="..."

# Run all tests
./scripts/run_all_phase15_tests.sh
```

**Expected Output:**
```
========================================================================
PHASE 15 OPTIONS TRADING - MASTER TEST SUITE
========================================================================
...
✅ PASSED: Options API Module
✅ PASSED: Database Migration 008

========================================================================
TEST SUMMARY
========================================================================
Total Tests:   2
Passed:        2
Failed:        0
Skipped:       0

🎉 ALL TESTS PASSED!
```

### Option 2: Run Individual Tests

**Test Options API Only:**
```bash
export ALPACA_KEY_ID="..."
export ALPACA_SECRET_KEY="..."

python3 scripts/test_options_api.py
```

**Test Database Migration Only:**
```bash
export DB_HOST="..."
export DB_PASSWORD="..."

python3 scripts/test_migration_008.py
```

## Interpreting Results

### Success Indicators

✅ **All tests pass:** Ready to deploy to production  
- Migration 008 can be applied to production database
- Dispatcher service can be deployed to ECS
- Options trading is ready for paper trading

### Common Issues & Solutions

#### Issue: "Missing ALPACA_KEY_ID environment variable"
**Solution:** Set Alpaca API credentials (see Prerequisites section)

#### Issue: "No option contracts found"
**Reason:** Market is closed or testing outside trading hours  
**Solution:** This is OK - test will show ⚠️ WARN but still pass

#### Issue: "Missing columns: ['strike_price', 'contracts', ...]"
**Reason:** Migration 008 not applied to database  
**Solution:** Run `python3 scripts/apply_migration_008_direct.py`

#### Issue: "Cannot connect to database"
**Reason:** Wrong credentials or database not accessible  
**Solution:** Verify DB_HOST, DB_PASSWORD, and network access

#### Issue: "Constraint not working - invalid data accepted"
**Reason:** Migration 008 applied incorrectly  
**Solution:** Review migration logs, may need to rollback and reapply

## Test Coverage

### What's Tested ✅
- Options API connection and authentication
- Option chain fetching and parsing
- Strike selection algorithms (ATM/OTM/ITM)
- Liquidity validation (volume, spread)
- Position sizing calculations
- OCC symbol formatting
- Database schema changes (columns, indexes, views)
- Data integrity constraints
- Backward compatibility with stock trading

### What's NOT Tested ⏸️
- End-to-end broker integration (requires manual testing)
- Signal generation for options (Phase 15B)
- Live order execution on Alpaca (requires deployment)
- Multiple concurrent executions (stress testing)
- Long-term position management (Week 2-3)

## Manual Testing Checklist

After automated tests pass, perform these manual validations:

### 1. Verify Options Module Import
```python
# In Python REPL or notebook
from services.dispatcher.alpaca.options import AlpacaOptionsAPI

api = AlpacaOptionsAPI(
    api_key=os.environ['ALPACA_KEY_ID'],
    api_secret=os.environ['ALPACA_SECRET_KEY']
)

# This should not raise any errors
print("✅ Import successful")
```

### 2. Verify Database Views
```sql
-- Connect to database
psql -h $DB_HOST -U $DB_USER -d $DB_NAME

-- Query views (should return empty results initially)
SELECT * FROM active_options_positions LIMIT 5;
SELECT * FROM options_performance_by_strategy;
SELECT * FROM daily_options_summary;

-- All queries should execute without errors
```

### 3. Verify Broker Can Import Options Module
```bash
# Navigate to dispatcher directory
cd services/dispatcher

# Start Python and import
python3 -c "from alpaca.broker import AlpacaPaperBroker; print('✅ Broker imports options module')"
```

## CI/CD Integration

The test suite is designed for CI/CD pipelines:

### Exit Codes
- `0` = All tests passed
- `1` = One or more tests failed
- `2` = No tests run (missing environment)

### Example GitHub Actions
```yaml
- name: Run Phase 15 Tests
  env:
    ALPACA_KEY_ID: ${{ secrets.ALPACA_KEY_ID }}
    ALPACA_SECRET_KEY: ${{ secrets.ALPACA_SECRET_KEY }}
    DB_HOST: ${{ secrets.DB_HOST }}
    DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
  run: |
    chmod +x scripts/run_all_phase15_tests.sh
    ./scripts/run_all_phase15_tests.sh
```

### Example AWS CodeBuild
```yaml
phases:
  test:
    commands:
      - export ALPACA_KEY_ID=$(aws ssm get-parameter --name /ops-pipeline/alpaca_key_id --with-decryption --query Parameter.Value --output text)
      - export ALPACA_SECRET_KEY=$(aws ssm get-parameter --name /ops-pipeline/alpaca_secret_key --with-decryption --query Parameter.Value --output text)
      - chmod +x scripts/run_all_phase15_tests.sh
      - ./scripts/run_all_phase15_tests.sh
```

## Post-Test Actions

### If All Tests Pass ✅

1. **Apply Migration to Production**
   ```bash
   # Set production DB credentials
   export DB_HOST="prod-rds-endpoint"
   export DB_PASSWORD="prod-password"
   
   # Apply migration
   python3 scripts/apply_migration_008_direct.py
   ```

2. **Deploy Dispatcher Service**
   ```bash
   # Build Docker image
   cd services/dispatcher
   docker build -t dispatcher:phase15a .
   
   # Push to ECR
   # Deploy to ECS
   ```

3. **Monitor First Execution**
   - Watch CloudWatch logs for dispatcher service
   - Look for options API calls
   - Verify no errors in execution

### If Tests Fail ❌

1. **Review test output** - Identify which test failed
2. **Check logs** - Look for detailed error messages
3. **Fix root cause** - Update code/schema as needed
4. **Re-run tests** - Verify fix works
5. **Document issue** - Add to known issues if needed

## Troubleshooting

### Test Scripts Won't Run

**Symptoms:** `Permission denied` or `command not found`

**Solution:**
```bash
# Make scripts executable
chmod +x scripts/run_all_phase15_tests.sh
chmod +x scripts/test_options_api.py
chmod +x scripts/test_migration_008.py

# Ensure Python 3 is installed
python3 --version  # Should be 3.8+
```

### Import Errors

**Symptoms:** `ModuleNotFoundError` or `ImportError`

**Solution:**
```bash
# Install dependencies
cd services/dispatcher
pip3 install -r requirements.txt

# Or use virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Database Connection Timeout

**Symptoms:** Tests hang or timeout on database operations

**Solution:**
- Verify security group allows your IP
- Check VPN connection if using private subnet
- Test connection: `psql -h $DB_HOST -U $DB_USER`

## Success Criteria

Before declaring Phase 15A complete:

- [ ] All automated tests pass (100% pass rate)
- [ ] Manual verifications complete
- [ ] Migration applied to production successfully
- [ ] No errors in test runs
- [ ] Documentation reviewed and accurate
- [ ] Team trained on running tests

## Getting Help

**For test failures:**
1. Review test output carefully
2. Check this guide's troubleshooting section
3. Review Phase 15A status document: `deploy/PHASE_15A_OPTIONS_FOUNDATION_STATUS.md`
4. Check code comments in test files

**For deployment issues:**
- See `deploy/RUNBOOK.md`
- Review system status: `deploy/SYSTEM_STATUS_2026-01-26.md`

## Next Steps

After all tests pass:
1. Proceed to Phase 15B (signal generation)
2. Update signal engine to recommend options
3. Deploy and verify first live options trade
4. Begin collecting trade data for analysis

---

**Document Version:** 1.0  
**Test Suite Version:** Phase 15A  
**Last Validated:** 2026-01-26
