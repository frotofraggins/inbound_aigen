# 🚨 SECURITY ISSUE: Credentials in Plain Text

**Status:** URGENT - Needs fix before production  
**Impact:** API keys and passwords exposed in ECS task definition  
**Risk Level:** HIGH (paper trading credentials, but still bad practice)

---

## ⚠️ THE PROBLEM

**Current deployment has credentials in PLAIN TEXT:**

```json
{
  "environment": [
    {
      "name": "ALPACA_API_KEY",
      "value": "PKXA0G2HI0WVTD0NXO8Y"    ← EXPOSED
    },
    {
      "name": "ALPACA_API_SECRET",
      "value": "OWmm3n3h6bkzkJQIRxHlJJFgIB0TrN2KwWwOkXsn"    ← EXPOSED  
    },
    {
      "name": "DB_PASSWORD",
      "value": "YourSecurePassword123!"    ← EXPOSED
    }
  ]
}
```

**Files with exposed credentials:**
- `deploy/trade-stream-task-definition.json` ← JUST DEPLOYED
- `deploy/position-manager-task-definition.json`
- `deploy/dispatcher-task-definition.json`
- All other ECS task definitions

---

## ✅ CORRECT SOLUTION: AWS Secrets Manager

### Step 1: Create Secrets (5 minutes)

```bash
# Create secret for Alpaca credentials
aws secretsmanager create-secret \
  --name ops-pipeline/alpaca/api-key \
  --secret-string "PKXA0G2HI0WVTD0NXO8Y" \
  --region us-west-2

aws secretsmanager create-secret \
  --name ops-pipeline/alpaca/api-secret \
  --secret-string "OWmm3n3h6bkzkJQIRxHlJJFgIB0TrN2KwWwOkXsn" \
  --region us-west-2

# Create secret for database password
aws secretsmanager create-secret \
  --name ops-pipeline/database/password \
  --secret-string "YourSecurePassword123!" \
  --region us-west-2
```

### Step 2: Update Task Definition (10 minutes)

**Replace `environment` with `secrets`:**

```json
{
  "secrets": [
    {
      "name": "ALPACA_API_KEY",
      "valueFrom": "arn:aws:secretsmanager:us-west-2:160027201036:secret:ops-pipeline/alpaca/api-key"
    },
    {
      "name": "ALPACA_API_SECRET",
      "valueFrom": "arn:aws:secretsmanager:us-west-2:160027201036:secret:ops-pipeline/alpaca/api-secret"
    },
    {
      "name": "DB_PASSWORD",
      "valueFrom": "arn:aws:secretsmanager:us-west-2:160027201036:secret:ops-pipeline/database/password"
    }
  ],
  "environment": [
    {
      "name": "ALPACA_BASE_URL",
      "value": "https://paper-api.alpaca.markets"
    },
    {
      "name": "DB_HOST",
      "value": "ops-pipeline-db.czow18p7ug2w.us-west-2.rds.amazonaws.com"
    }
  ]
}
```

### Step 3: Update IAM Role (5 minutes)

**Add Secrets Manager permissions to task role:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-west-2:160027201036:secret:ops-pipeline/*"
      ]
    }
  ]
}
```

### Step 4: Re-register & Deploy (10 minutes)

```bash
# Register updated task definition
aws ecs register-task-definition \
  --cli-input-json file://deploy/trade-stream-task-definition.json \
  --region us-west-2

# Update service to use new revision
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service trade-stream \
  --task-definition trade-stream:2 \
  --force-new-deployment \
  --region us-west-2
```

---

## 📋 ALL SERVICES THAT NEED THIS FIX

**Priority 1 (Already Deployed):**
- ✅ `trade-stream` ← JUST DEPLOYED WITH PLAIN TEXT
- ✅ `dispatcher` ← ALREADY DEPLOYED
- ✅ `position-manager` ← Task definition exists

**Priority 2 (Not yet deployed but have credentials):**
- `feature-computer-1m`
- `signal-engine-1m`
- `watchlist-engine-5m`
- `telemetry-ingestor-1m`
- `classifier-worker`

---

## 🔒 WHY THIS MATTERS

**Current Risk:**
1. ❌ Credentials visible in AWS Console
2. ❌ Credentials in Git history (if committed)
3. ❌ Credentials accessible to anyone with ECS read access
4. ❌ Can't rotate without redeploying
5. ❌ No audit trail of credential access

**With Secrets Manager:**
1. ✅ Credentials encrypted at rest
2. ✅ Credentials not in Git
3. ✅ Access controlled via IAM
4. ✅ Can rotate without redeployment
5. ✅ Full audit trail in CloudTrail

---

## ⏰ TIMELINE

**DO THIS BEFORE PRODUCTION:**
- Paper trading: OK to wait (low risk)
- Live trading: MUST FIX (high risk)

**Estimated Time:** 30 minutes total for all services

---

## 📖 FOR NEXT SESSION

1. Create secrets in Secrets Manager
2. Update all task definitions to use `secrets` instead of `environment`
3. Add Secrets Manager permissions to IAM role
4. Re-register all task definitions
5. Force new deployment of all services
6. Verify services still work
7. Remove credentials from all task definition files in Git

**Template script in:** `scripts/migrate_to_secrets_manager.sh` (needs to be created)

---

## 🎯 BOTTOM LINE

**Current Status:** Trade stream is WORKING but credentials are EXPOSED  
**Security Risk:** MEDIUM (paper trading, but still bad practice)  
**Fix Priority:** HIGH (before live trading)  
**Fix Time:** 30 minutes  

**The WebSocket service is running correctly - this is just a security improvement that should be made soon.** ✅🔒
