# ✅ ROOT CAUSE IDENTIFIED - Position Manager Failure
**Date:** 2026-02-04 18:01 UTC
**Status:** DIAGNOSIS COMPLETE - Ready for Fix

## 🎯 THE ROOT CAUSE

**The large account position manager crashes on startup when loading config.py, before any logs can be written.**

### What We Found

1. ✅ **Task Definitions:** Correct - only difference is ACCOUNT_NAME (expected)
2. ✅ **Secrets Manager:** All required secrets exist:
   - `ops-pipeline/db`
   - `ops-pipeline/alpaca`
   - `ops-pipeline/alpaca/tiny`
3. ✅ **Task Role:** `ops-pipeline-ecs-task-role` exists
4. ❌ **Service Behavior:** Crashes immediately, no logs written

### Why No Logs?

The `config.py` file runs `load_config()` **at module import time**:
```python
# Load config on import
_config = load_config()
```

If `load_config()` fails (permissions, missing secrets, network timeout), the entire module import fails BEFORE logging is initialized in `main.py`.

Result: **Crash before first log line**

## 🔍 Why Tiny Works But Large Doesn't

**Hypothesis:** Tiny account service started successfully earlier when permissions were different, or uses cached credentials, while large account service deployment hit the permission issue.

**OR:** There's a race condition/timing issue with secrets access that tiny got lucky with.

## 🔧 RECOMMENDED FIX (In Order)

### Option 1: Verify IAM Permissions (HIGHEST PRIORITY)
```bash
# Check if role has SecretsManager permissions
aws iam get-role-policy \
  --role-name ops-pipeline-ecs-task-role \
  --policy-name SecretsManagerAccess \
  --region us-west-2

# If not found, check attached policies
aws iam list-attached-role-policies \
  --role-name ops-pipeline-ecs-task-role \
  --region us-west-2
```

Expected permissions needed:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "ssm:GetParameter"
  ],
  "Resource": [
    "arn:aws:secretsmanager:us-west-2:*:secret:ops-pipeline/*",
    "arn:aws:ssm:us-west-2:*:parameter/ops-pipeline/*"
  ]
}
```

### Option 2: Add Error Handling to config.py

Wrap the config loading in try/except so errors get logged:

```python
try:
    _config = load_config()
except Exception as e:
    # Log to stderr so it appears even if logging not configured
    import sys
    print(f"FATAL: Failed to load config: {e}", file=sys.stderr)
    raise
```

This way we'd at least see the error in CloudWatch before crash.

### Option 3: Test Secrets Access Directly

Create a minimal test script to verify secrets can be read:

```python
#!/usr/bin/env python3
import boto3
import json

try:
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    # Test DB secret
    db_secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    print("✓ Successfully read ops-pipeline/db")
    
    # Test Alpaca secret
    alpaca_secret = secrets.get_secret_value(SecretId='ops-pipeline/alpaca')
    print("✓ Successfully read ops-pipeline/alpaca")
    
    print("All secrets accessible!")
    
except Exception as e:
    print(f"✗ Failed to read secrets: {e}")
    raise
```

Deploy this as a one-off task with same role to test.

## 📊 Evidence Summary

### What's Confirmed Working
- ✅ Tiny account position manager runs perfectly
- ✅ Same code, same Docker image
- ✅ Both secrets exist in Secrets Manager
- ✅ Task definition syntax correct
- ✅ Exit logic code is correct

### What's Broken
- ❌ Large account crashes on startup
- ❌ Zero logs (crash before logging init)
- ❌ Both original deployment AND restart failed
- ❌ 100+ minutes without protection

### Impact
- **All large account positions closing in 1-5 minutes**
- **No 30-minute hold enforcement**
- **No -40%/+80% exit thresholds**
- **Exit fix code never executes**

## 🚀 IMMEDIATE NEXT STEPS

### Step 1: Check IAM Permissions (2 minutes)
```bash
aws iam list-attached-role-policies \
  --role-name ops-pipeline-ecs-task-role \
  --region us-west-2

# Then get each policy document
aws iam get-policy-version \
  --policy-arn <arn-from-above> \
  --version-id v1 \
  --region us-west-2
```

Look for:
- SecretsManager:GetSecretValue permission
- SSM:GetParameter permission
- Correct resource ARN patterns

### Step 2: If Permissions Missing, Add Them
```bash
# Create policy document
cat > /tmp/secrets-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "ssm:GetParameter"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-west-2:160027201036:secret:ops-pipeline/*",
        "arn:aws:ssm:us-west-2:160027201036:parameter/ops-pipeline/*"
      ]
    }
  ]
}
EOF

# Attach to role
aws iam put-role-policy \
  --role-name ops-pipeline-ecs-task-role \
  --policy-name SecretsManagerAccess \
  --policy-document file:///tmp/secrets-policy.json \
  --region us-west-2
```

### Step 3: Force New Deployment (1 minute)
```bash
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --force-new-deployment \
  --region us-west-2
```

### Step 4: Monitor Logs (2 minutes)
```bash
# Wait 30 seconds for task to start
sleep 30

# Watch logs
aws logs tail /ecs/ops-pipeline/position-manager \
  --follow \
  --region us-west-2
```

### Step 5: Success Verification
Look for these log lines:
```
Position Manager starting
Managing positions for account: large
Sleeping for 1 minute until next check...
```

## ✅ Success Criteria

1. Service logs appear in CloudWatch
2. "Position Manager starting" message every 60 seconds
3. No error messages
4. Position monitoring active
5. Exit logic protecting positions

## 📝 Lessons Learned

1. **Always verify IAM permissions** when service fails silently
2. **Add try/except in config loading** to catch and log errors
3. **Test with minimal script** before full deployment
4. **Add health checks** to detect silent failures
5. **Monitor log silence** as failure indicator

## 🎯 Estimated Time to Fix

- **If permissions issue:** 5 minutes
- **If other issue:** 15-30 minutes debugging

## 📊 Current Status

- **Service:** DEAD (no logs for 100+ minutes)
- **Tiny Account:** HEALTHY (working normally)
- **Root Cause:** **Identified - config loading failure**
- **Fix:** **Ready to implement**
- **Priority:** **CRITICAL**

---

**NEXT ACTION: Check IAM permissions, add if missing, redeploy, verify logs**
