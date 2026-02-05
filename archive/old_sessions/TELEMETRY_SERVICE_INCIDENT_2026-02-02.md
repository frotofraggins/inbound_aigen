# Telemetry Service Crash-Loop Incident

**Date:** February 2, 2026 2:46 PM UTC  
**Severity:** MEDIUM (not blocking trades)  
**Status:** INVESTIGATING

---

## 🚨 Issue

Telemetry service is crash-looping:
- ECS keeps starting tasks (14:45:46, 14:44:41, 14:43:40)
- Tasks exit immediately
- No logs created (crashed before logging)
- Running count: 0/1 (unhealthy)

## 🔍 Investigation

### **What We Know:**
- ✅ Other services running fine (dispatcher, position-manager, trade-stream)
- ✅ Database accessible (dispatcher connects successfully)
- ✅ Signal engine generating signals (HOLD - correct)
- ❌ Telemetry container exits with: "EssentialContainerExited"
- ❌ No log group created (crashed before first log)

### **What's Still Working:**
- ✅ **Signal generation** - Signal engine is working
- ✅ **Trading** - Dispatcher operational
- ✅ **Position monitoring** - Position manager running

**Conclusion:** Telemetry failure is NOT blocking trading system.

---

## 💡 Possible Causes

### **1. Alpaca Data API Credentials Issue** (Most Likely)
```
Telemetry uses different Alpaca endpoint (data.alpaca.markets)
May have different credentials or permissions
```

### **2. Missing Environment Variable**
```
Task definition may be missing:
- ALPACA_API_KEY
- ALPACA_API_SECRET
- AWS_REGION
```

### **3. Code Error in telemetry_ingestor_1m/main.py**
```
Import error
Configuration error
Immediate crash on startup
```

### **4. Network/Firewall Issue**
```
Can't reach data.alpaca.markets
Security group blocking outbound HTTPS
```

---

## 🔧 Troubleshooting Steps

### **Step 1: Check Task Definition**
```bash
aws ecs describe-task-definition \
  --task-definition ops-pipeline-telemetry-service \
  --region us-west-2 \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  --output json
```

Look for:
- ALPACA_API_KEY_ID
- ALPACA_SECRET_KEY
- AWS_REGION

### **Step 2: Check Secret Exists**
```bash
aws secretsmanager get-secret-value \
  --secret-id ops-pipeline/alpaca \
  --region us-west-2 \
  --query 'SecretString' \
  --output text
```

Verify credentials are valid.

### **Step 3: Test Alpaca Data API Manually**
```bash
curl -H "APCA-API-KEY-ID: YOUR_KEY" \
     -H "APCA-API-SECRET-KEY: YOUR_SECRET" \
     "https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Min&limit=10"
```

If this fails, credentials are wrong.

### **Step 4: Review Task Definition**
```bash
cat deploy/telemetry-service-task-definition.json
```

Check:
- Container definition
- Secrets mapping
- Environment variables
- Log configuration

---

## 🚑 Quick Fixes

### **Fix 1: Restart with Force Deploy**
```bash
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service telemetry-service \
  --force-new-deployment \
  --region us-west-2
```

May fix transient issues.

### **Fix 2: Stop Service (Not Critical)**
```bash
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service telemetry-service \
  --desired-count 0 \
  --region us-west-2
```

Since signal engine is working without it, can investigate later.

### **Fix 3: Check Feature Compute Service**

If telemetry is down but signals work, maybe **feature-computer** is generating the data instead. Check:

```bash
aws ecs describe-services \
  --cluster ops-pipeline-cluster \
  --services feature-computer-service \
  --region us-west-2 2>&1
```

---

## 📊 Impact Analysis

### **Services Affected:**
- ❌ Telemetry ingestor (price data fetching)

### **Services Working:**
- ✅ Signal engine (generating HOLD signals)
- ✅ Dispatcher (processing signals, options-only mode)
- ✅ Position manager (monitoring positions)
- ✅ Trade stream (WebSocket)

### **Data Flow:**

**Expected:**
```
Telemetry → lane_telemetry table → Features → Signals
```

**Current (if telemetry down):**
```
??? → lane_telemetry table → Features → Signals
(Signal engine still works, so data is coming from somewhere!)
```

**Hypothesis:** Either:
1. Feature-computer service is fetching data
2. Old telemetry data still in database
3. Different scheduled task handling it

---

## ✅ Recommendations

### **Immediate (Do Now):**

1. **Don't panic** - Trading still works
2. **Check if features are recent:**
   ```python
   # Via Lambda
   SELECT MAX(computed_at) FROM lane_features;
   # If recent (< 5 min) then data is flowing
   ```
3. **Check if telemetry is recent:**
   ```python
   SELECT MAX(ts) FROM lane_telemetry;
   # If recent, then telemetry IS being inserted somehow
   ```

### **Short Term (This Session):**

Option A: **Stop telemetry service** (not critical if data flowing)
```bash
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service telemetry-service \
  --desired-count 0 \
  --region us-west-2
```

Option B: **Investigate task definition** (find root cause)
- Check secrets mapping
- Verify Alpaca credentials
- Test Alpaca Data API access

### **Long Term (Next Session):**

1. **Find alternative data source** (if telemetry truly broken)
2. **Fix telemetry service** (proper credentials, error handling)
3. **Add health checks** (detect failures faster)
4. **Add alerting** (email/Slack when service down)

---

## 🎯 Status Update

**Current State:**
- ❌ Telemetry service crash-looping
- ✅ Signal engine generating (data must be coming from somewhere)
- ✅ Dispatcher operational (options-only mode)
- ✅ 4/6 services healthy

**Next Steps:**
1. Verify lane_telemetry has recent data
2. If yes: Stop telemetry service (not needed)
3. If no: Investigate why signal engine still works

**Priority:** MEDIUM - Not blocking trades, but should fix

---

**Recommendation:** Focus on verifying the system still trades when volume picks up. Fix telemetry in next session if needed.
