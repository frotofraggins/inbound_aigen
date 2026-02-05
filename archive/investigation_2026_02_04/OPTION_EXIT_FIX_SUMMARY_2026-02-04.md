# Option Exit Fix Summary - 2026-02-04

## Problem Identified

Options positions were closing within 1-2 minutes of entry due to:

1. **Exit thresholds too tight** for option premium volatility (-25%/+50%)
2. **No minimum hold time** - exiting on bid-ask spread noise
3. **Duplicate exit checking** - options could exit on EITHER premium OR underlying price

## Root Cause

Options premiums are EXTREMELY volatile and can swing ±25% in minutes due to:
- Bid-ask spread volatility
- Delta/gamma changes  
- Implied volatility shifts
- Market maker adjustments

The old thresholds (-25% stop / +50% target) were treating normal premium noise as real losses/gains.

## Fix Applied (Already in Code)

### 1. Widened Exit Thresholds

**Before:**
- Stop loss: -25%
- Profit target: +50%

**After:**
- Stop loss: -40%
- Profit target: +80%

### 2. Added Minimum Hold Time

```python
# MINIMUM HOLD TIME: Don't exit options in first 30 minutes
# Options premiums are volatile - give them room to breathe
# Exception: Allow exit if catastrophic loss (>50%)
if hold_minutes < 30:
    if option_pnl_pct > -50:
        return []  # Don't exit yet - too early
```

### 3. Removed Duplicate Exit Checking

Options now use ONLY option-specific exit logic (premium-based), not underlying stock price.

### 4. Updated Sync Function

When syncing positions from Alpaca, use the new wider stops:
- Options: -40% stop / +80% target
- Stocks: -2% stop / +3% target

## Impact

**Before Fix:**
- Average hold time: 1-2 minutes
- Exiting on ±10-20% premium noise
- Capturing bid-ask spread volatility, not real moves

**After Fix:**
- Minimum hold time: 30 minutes (unless catastrophic loss >50%)
- Only exit on real moves (±40%+)
- Expected hold time: 30-240 minutes

## Why CRM PUT When Stock is Rising?

The signal engine generates BUY_PUT when it detects bearish technical indicators:
- RSI divergence
- Momentum shift
- Overbought reversal

CRM may be up +0.17% NOW, but the signal was generated earlier when technicals showed bearish setup. This is normal - signals are forward-looking based on technical analysis, not reactive to current price.

## Deployment Status

**Code Status:** ✅ FIXED (already in monitor.py)

**Deployment Status:** ⏳ PENDING

The fix is in the code but needs to be deployed to ECS services.

### To Deploy:

```bash
./deploy_option_exit_fix.sh
```

This will:
1. Build new Docker image with fixes
2. Push to ECR
3. Force new deployment of both position manager services (large and tiny)

### Verification After Deployment:

Monitor next trades and verify:
- Options held for at least 30 minutes (unless >50% loss)
- No exits on small premium swings (±10-20%)
- Exits only on real moves (±40%+) or time-based triggers

## Files Modified

- `services/position_manager/monitor.py` - Updated exit logic
- `CRITICAL_OPTION_EXIT_FIX_2026-02-04.md` - Detailed analysis
- `deploy_option_exit_fix.sh` - Deployment script
- `OPTION_EXIT_FIX_SUMMARY_2026-02-04.md` - This summary

## Next Steps

1. Run `./deploy_option_exit_fix.sh` to deploy the fix
2. Monitor next trades for improved hold times
3. Verify positions hold for at least 30 minutes
4. Check that exits only occur on real moves (±40%+)

## Expected Results

After deployment, you should see:
- Options holding for 30+ minutes before any exit
- No more 1-2 minute exits on small premium swings
- Exits only when:
  - Real profit (+80% or more)
  - Real loss (-40% or more)
  - Time-based triggers (max hold time, day trade close, expiry risk)
  - Catastrophic loss (>50% in first 30 minutes)
