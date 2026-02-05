# CRITICAL: Dispatcher Not Tracking Positions

**Date:** February 3, 2026 18:15 UTC  
**Severity:** 🔴 CRITICAL - Risk Management Failure  
**Status:** ⚠️ ACTIVE BUG - System Over-Trading

---

## 🚨 Problem Summary

**The Dispatcher opened 11 positions when the limit is 5!**

**Root Cause:** `get_account_state()` in `services/dispatcher/db/repositories.py` is NOT filtering by `account_name`, so it's either:
1. Counting positions from ALL accounts (wrong)
2. Finding no positions because table is empty (wrong)

**Evidence from Logs:**
```
"max_positions": "Positions 0/5"  ❌ WRONG - Actually had 11 positions!
"max_exposure": "Exposure $0"     ❌ WRONG - Actually had $98,630 exposure!
```

**Result:** Risk gates were bypassed, system over-traded massively.

---

## 📊 What Actually Happened

### Timeline
```
17:29-17:42 - Dispatcher opened 11 option positions
              Total: $98,630 in exposure
              Limit: 5 positions, $10,000 exposure
              
17:46      - Position Manager correctly closed 5 positions
              (stop loss / take profit triggers)
              
Current    - 6 positions still open (~$61,000)
```

### Positions Opened (All Options)
1. MSFT PUT - $7,200
2. CRM PUT - $6,700
3. META PUT - $17,100
4. AVGO PUT - $14,400
5. AMD PUT - $12,550
6. AAPL PUT - $3,050
7. QCOM PUT #1 - $8,450 (CLOSED by PM)
8. QCOM PUT #2 - $8,050 (CLOSED by PM)
9. GOOGL PUT - $12,750 (CLOSED by PM)
10. NVDA PUT - $5,750 (CLOSED by PM)
11. ORCL PUT - $8,450 (CLOSED by PM)
12. INTC PUT - $1,640 (CLOSED by PM)

**Total Opened:** $98,630 (should have stopped at $10,000!)  
**Currently Open:** ~$61,000 (still 6x over limit!)

---

## 🔍 Root Cause Analysis

### The Bug in `get_account_state()`

**File:** `services/dispatcher/db/repositories.py`

**Current Code (BROKEN):**
```python
def get_account_state(conn) -> Dict[str, Any]:
    """Get account-level state for kill switch gates."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get active position count and total notional
        cur.execute("""
            SELECT 
                COUNT(*) as position_count,
                COALESCE(SUM(ABS(quantity * entry_price)), 0) as total_notional
            FROM active_positions
            WHERE status IN ('open', 'OPEN')
        """)
        # ❌ NO ACCOUNT_NAME FILTER!
```

**Problems:**
1. ❌ No `account_name` filter in WHERE clause
2. ❌ Counts positions from ALL accounts (or none if table empty)
3. ❌ Dispatcher has no idea which account it's managing

---

## ✅ The Fix

### Step 1: Pass Account Name to `get_account_state()`

**Update Function Signature:**
```python
def get_account_state(conn, account_name: str) -> Dict[str, Any]:
    """
    Get account-level state for kill switch gates.
    
    Args:
        conn: Database connection
        account_name: Account name to filter by (e.g., 'large', 'tiny')
    
    Returns:
        Dict with daily_pnl, active_position_count, total_notional
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get today's P&L from executions FOR THIS ACCOUNT
        cur.execute("""
            SELECT COALESCE(SUM(notional), 0) as total_traded_today
            FROM dispatch_executions
            WHERE simulated_ts >= CURRENT_DATE
              AND account_name = %s  -- ✅ FILTER BY ACCOUNT
        """, (account_name,))
        result = cur.fetchone()
        total_traded = float(result['total_traded_today']) if result else 0.0
        
        # Get active position count and total notional FOR THIS ACCOUNT
        cur.execute("""
            SELECT 
                COUNT(*) as position_count,
                COALESCE(SUM(ABS(quantity * entry_price)), 0) as total_notional
            FROM active_positions
            WHERE status IN ('open', 'OPEN')
              AND account_name = %s  -- ✅ FILTER BY ACCOUNT
        """, (account_name,))
        result = cur.fetchone()
        
        position_count = int(result['position_count']) if result else 0
        total_notional = float(result['total_notional']) if result else 0.0
        
        # For now, daily P&L is approximated
        daily_pnl = 0.0  # TODO: Calculate from position_events
        
        return {
            'daily_pnl': daily_pnl,
            'active_position_count': position_count,
            'total_notional': total_notional,
            'total_traded_today': total_traded
        }
```

### Step 2: Update Dispatcher to Pass Account Name

**File:** `services/dispatcher/main.py`

**Current Code (BROKEN):**
```python
# Get account-level state for kill switch gates
account_state = get_account_state(conn)  # ❌ No account_name!
```

**Fixed Code:**
```python
# Get account-level state for kill switch gates
account_name = config.get('account_name', 'large')  # ✅ Get from config
account_state = get_account_state(conn, account_name)  # ✅ Pass account_name
```

---

## 🎯 Expected Behavior After Fix

### Large Account
```
Account: large
Buying Power: $209,000
Max Positions: 5
Max Exposure: $10,000

Dispatcher checks:
- Query: SELECT COUNT(*) FROM active_positions WHERE account_name = 'large'
- Result: Actual count for large account only
- Gate: Blocks when count >= 5
```

### Tiny Account
```
Account: tiny
Buying Power: $1,500
Max Positions: 1
Max Exposure: $2,000 (estimated)

Dispatcher checks:
- Query: SELECT COUNT(*) FROM active_positions WHERE account_name = 'tiny'
- Result: Actual count for tiny account only
- Gate: Blocks when count >= 1
```

---

## 📝 Files to Modify

1. **`services/dispatcher/db/repositories.py`**
   - Update `get_account_state()` signature to accept `account_name`
   - Add `WHERE account_name = %s` to both queries
   - Add parameter binding

2. **`services/dispatcher/main.py`**
   - Extract `account_name` from config
   - Pass `account_name` to `get_account_state()`

---

## 🚀 Deployment Steps

1. **Update Code:**
   ```bash
   # Edit files above
   ```

2. **Build New Image:**
   ```bash
   docker build -t ops-pipeline/dispatcher:position-tracking-fix services/dispatcher
   docker tag ops-pipeline/dispatcher:position-tracking-fix \
     160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-tracking-fix
   ```

3. **Push to ECR:**
   ```bash
   aws ecr get-login-password --region us-west-2 | \
     docker login --username AWS --password-stdin 160027201036.dkr.ecr.us-west-2.amazonaws.com
   docker push 160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/dispatcher:position-tracking-fix
   ```

4. **Update Task Definitions:**
   ```bash
   # Update image tag in both task definitions
   sed -i 's|account-tier-v5|position-tracking-fix|g' deploy/dispatcher-task-definition.json
   sed -i 's|account-tier-v5|position-tracking-fix|g' deploy/dispatcher-task-definition-tiny-service.json
   ```

5. **Register and Deploy:**
   ```bash
   # Large account
   aws ecs register-task-definition \
     --cli-input-json file://deploy/dispatcher-task-definition.json \
     --region us-west-2
   
   aws ecs update-service \
     --cluster ops-pipeline-cluster \
     --service dispatcher-service \
     --task-definition ops-pipeline-dispatcher:34 \
     --force-new-deployment \
     --region us-west-2
   
   # Tiny account
   aws ecs register-task-definition \
     --cli-input-json file://deploy/dispatcher-task-definition-tiny-service.json \
     --region us-west-2
   
   aws ecs update-service \
     --cluster ops-pipeline-cluster \
     --service dispatcher-tiny-service \
     --task-definition ops-pipeline-dispatcher-tiny-service:14 \
     --force-new-deployment \
     --region us-west-2
   ```

---

## ✅ Verification

After deployment, check logs for:

```
# Should see correct position counts
"max_positions": "Positions 3/5"  ✅ Actual count
"max_exposure": "Exposure $25000/$10000"  ✅ Actual exposure

# Should see gates blocking when limits reached
"max_positions": {"passed": false, "reason": "At position limit: 5/5"}
```

---

## 🎊 Impact

**Before Fix:**
- ❌ Opened 11 positions (limit: 5)
- ❌ $98,630 exposure (limit: $10,000)
- ❌ Risk gates completely bypassed
- ❌ No account isolation

**After Fix:**
- ✅ Respects 5 position limit
- ✅ Respects $10,000 exposure limit
- ✅ Risk gates work correctly
- ✅ Accounts properly isolated

---

## 🔥 URGENT

**This is a CRITICAL risk management bug!**

The system is currently over-trading by 2x on positions and 10x on exposure. This must be fixed immediately before market open tomorrow.

**Priority:** P0 - Deploy ASAP

---

**Status:** Ready to fix - all changes identified and documented.
