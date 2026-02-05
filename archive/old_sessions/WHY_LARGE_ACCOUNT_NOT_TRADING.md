# Why Large Account Not Trading - Diagnostic

## 📊 What You're Seeing

**Tiny Account (1 contract each):**
- ✅ AMD PUT: +$125 (+10.6%)
- ❌ CRM CALL: -$195 (-47.6%)
- ✅ BAC CALL: +$10 (+8.3%)

**Large Account:**
- ❌ No trades visible

---

## 🔍 Possible Reasons

### Reason 1: Both Accounts Using Same Recommendations
**Current behavior:**
- Both dispatchers pull from same `dispatch_recommendations` table
- Tiny dispatcher might be claiming them first (faster/less restrictive)
- Large dispatcher finds nothing left to claim

**Check:**
```sql
SELECT 
    claimed_by,
    COUNT(*) as count
FROM dispatch_recommendations
WHERE created_at >= CURRENT_DATE
AND status IN ('EXECUTED', 'SIMULATED')
GROUP BY claimed_by
```

**If tiny is claiming all recommendations:**
- Need to create separate recommendation streams
- Or use priority system

### Reason 2: Large Account Has Stricter Gates
**Possible:**
- Large account has higher confidence threshold
- Large account has stricter risk limits
- Signals that pass tiny gates fail large gates

**Check large dispatcher config:**
```bash
aws ssm get-parameter --name /ops-pipeline/dispatcher_config_large --query 'Parameter.Value' --region us-west-2
```

**Compare to tiny:**
```bash
aws ssm get-parameter --name /ops-pipeline/dispatcher_config_tiny --query 'Parameter.Value' --region us-west-2
```

### Reason 3: Large Account Hit Daily Limits
**Possible:**
- Max positions reached (5 for large, 2 for tiny)
- Max exposure reached ($10K for large, $1.5K for tiny)
- Daily loss limit hit

**Check:**
```sql
SELECT 
    account_name,
    COUNT(*) as open_positions,
    SUM(quantity * entry_price) as total_exposure
FROM active_positions
WHERE status = 'open'
GROUP BY account_name
```

### Reason 4: Ticker List Mismatch (We Saw This Earlier!)
**Remember:** AMD, BAC, CRM might not be in large account's ticker universe

**Check:**
```bash
# Large account ticker list
