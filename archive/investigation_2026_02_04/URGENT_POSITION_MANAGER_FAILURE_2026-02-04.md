# 🚨 URGENT: Position Manager Service Complete Failure
**Time:** 2026-02-04 17:59 UTC
**Status:** CRITICAL - Service Dead, No Logs, Exit Protection OFFLINE

## 🔴 Current Situation

### Large Account Position Manager: DEAD
- **Last successful log:** 2026-02-04 16:20:47 UTC (97 minutes ago)
- **Service status:** Shows RUNNING (false positive)
- **Logs:** ZERO - Complete silence
- **Restart attempt:** New deployment also produces NO LOGS
- **Impact:** All positions closing in 1-5 minutes, no exit protection

### Tiny Account Position Manager: HEALTHY ✅
- Running normally every 1 minute
- Logging correctly
- Successfully monitoring (no positions currently)

## 🎯 Root Cause

The large account service is **failing immediately on startup** but:
1. ❌ No error logs being written
2. ❌ Container starts but application crashes instantly
3. ❌ ECS health check doesn't detect failure
4. ❌ Even restart produces no logs

This suggests **catastrophic startup failure** before logging can initialize.

## 🔍 Likely Causes (In Order of Probability)

### 1. Missing/Invalid SSM Parameter ⭐ MOST LIKELY
**The large account config references SSM parameters that don't exist or are invalid**

Check:
```bash
# Compare SSM parameters
aws ssm get-parameters \
  --names \
    /ops-pipeline/account/large/alpaca-api-key \
    /ops-pipeline/account/large/alpaca-api-secret \
  --with-decryption \
  --region us-west-2
```

If these are missing or wrong format, service crashes before logging starts.

### 2. Import Error in config.py
The large account config.py might have:
- Syntax error
- Import of non-existent module
- Reference to undefined variable

### 3. IAM Permission Issue
Task role lacks permission to:
- Read SSM parameters for large account
- Write to CloudWatch logs for this service
- Access secrets manager

### 4. Environment Variable Typo
Task definition might have typo in:
- `ACCOUNT_NAME` (should be "large")
- `ACCOUNT_TIER` (should be "large") 
- SSM parameter paths

## 🔧 IMMEDIATE ACTIONS

### Action 1: Compare Task Definitions
```bash
# Get both task definitions
aws ecs describe-task-definition \
  --task-definition position-manager-service \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  --region us-west-2 > /tmp/large-env.json

aws ecs describe-task-definition \
  --task-definition position-manager-tiny-service \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  --region us-west-2 > /tmp/tiny-env.json

# Compare
diff /tmp/large-env.json /tmp/tiny-env.json
```

Look for:
- Missing environment variables
- Typos in variable names
- Wrong SSM parameter paths

### Action 2: Verify SSM Parameters Exist
```bash
# Check if large account SSM parameters exist
aws ssm describe-parameters \
  --filters "Key=Name,Values=/ops-pipeline/account/large" \
  --region us-west-2
```

### Action 3: Check IAM Task Role
```bash
# Get task role ARN
aws ecs describe-task-definition \
  --task-definition position-manager-service \
  --query 'taskDefinition.taskRoleArn' \
  --region us-west-2

# Check policies attached to role
aws iam list-attached-role-policies \
  --role-name ops-pipeline-ecs-task-role
```

### Action 4: Check Container Definition
```bash
# Get full container definition
aws ecs describe-task-definition \
  --task-definition position-manager-service \
  --region us-west-2 \
  --output json > /tmp/large-task-full.json

# Check:
# - logConfiguration section
# - environment variables
# - command/entrypoint
```

### Action 5: Enable ECS Exec for Debugging
```bash
# Update service to allow exec
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --enable-execute-command \
  --region us-west-2

# Wait for task to start, then exec into it
TASK_ID=$(aws ecs list-tasks \
  --cluster ops-pipeline-cluster \
  --service-name position-manager-service \
  --query 'taskArns[0]' \
  --output text | cut -d'/' -f3)

aws ecs execute-command \
  --cluster ops-pipeline-cluster \
  --task $TASK_ID \
  --container position-manager \
  --interactive \
  --command "/bin/bash"
```

## 🎯 Quick Fix Options

### Option A: Copy Tiny Config (FASTEST)
If tiny is working, copy its exact configuration:

```bash
# Get tiny task definition
aws ecs describe-task-definition \
  --task-definition position-manager-tiny-service \
  --region us-west-2 > /tmp/tiny-full.json

# Modify for large account:
# 1. Change service name
# 2. Change ACCOUNT_NAME="large"
# 3. Change ACCOUNT_TIER="large"
# 4. Update SSM parameter paths to /ops-pipeline/account/large/*

# Register new task definition
aws ecs register-task-definition \
  --cli-input-json file:///tmp/large-fixed.json

# Update service
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --task-definition position-manager-service:10 \
  --force-new-deployment \
  --region us-west-2
```

### Option B: Create Missing SSM Parameters
If SSM parameters are missing:

```bash
# Get tiny account parameters as template
aws ssm get-parameters \
  --names \
    /ops-pipeline/account/tiny/alpaca-api-key \
    /ops-pipeline/account/tiny/alpaca-api-secret \
  --with-decryption \
  --region us-west-2

# Create large account parameters
# (Use same values as tiny for paper trading)
aws ssm put-parameter \
  --name /ops-pipeline/account/large/alpaca-api-key \
  --value "YOUR_KEY" \
  --type SecureString \
  --region us-west-2

aws ssm put-parameter \
  --name /ops-pipeline/account/large/alpaca-api-secret \
  --value "YOUR_SECRET" \
  --type SecureString \
  --region us-west-2
```

### Option C: Temporary Workaround
Redirect large account to use tiny account SSM params:

```bash
# Update task definition environment:
# - ACCOUNT_NAME=large
# - ACCOUNT_TIER=large
# But SSM paths point to /ops-pipeline/account/tiny/*

# This gets service running with large account logic
# but tiny account API keys (safe for testing)
```

## 📊 Why This Is Critical

**Without position manager running:**
1. ❌ No 30-minute minimum hold enforcement
2. ❌ No -40%/+80% exit threshold protection
3. ❌ Positions close in 1-5 minutes (Alpaca defaults)
4. ❌ All exit logic bypassed
5. ❌ System loses 66% of intended value

**Large account has been unprotected for 97 minutes!**

## ✅ Success Criteria

Service is fixed when we see:
```
2026-02-04 18:XX:XX,XXX - __main__ - INFO - Position Manager starting
2026-02-04 18:XX:XX,XXX - __main__ - INFO - Managing positions for account: large
2026-02-04 18:XX:XX,XXX - __main__ - INFO - Sleeping for 1 minute until next check...
```

## 🚀 Recommended Next Steps

1. **[NOW]** Run Action 1 (compare task definitions)
2. **[NOW]** Run Action 2 (verify SSM parameters)
3. **[5 MIN]** If SSM missing → Option B (create them)
4. **[5 MIN]** If config wrong → Option A (copy tiny config)
5. **[10 MIN]** If still failing → Option C (temporary workaround)
6. **[15 MIN]** If all else fails → Enable ECS exec and debug directly

## 📝 Notes for Next Session

- Document what fixed it
- Add health checks to prevent this
- Add startup verification to deployments
- Consider consolidating configs
- Add CloudWatch alarms for log silence

---

**PRIORITY: Get this service running in next 15 minutes**
**METHOD: Start with quickest options first (compare configs, check SSM)**
