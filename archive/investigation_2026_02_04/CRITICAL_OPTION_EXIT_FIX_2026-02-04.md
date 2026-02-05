# CRITICAL: Option Positions Closing Too Quickly

**Date:** 2026-02-04 15:45 ET  
**Status:** IDENTIFIED - FIX READY

## Problem Summary

Options positions are closing within 1-2 minutes of entry due to:

1. **Exit thresholds too tight** for option premium volatility
2. **Duplicate exit checking** (both option premium AND underlying price)
3. **No minimum hold time** to filter out noise

## Current Behavior (BROKEN)

From `services/position_manager/monitor.py`:

```python
def check_exit_conditions_options(position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Option-specific exit conditions"""
    
    # Exit 1: Option profit target (+50%)
    if option_pnl_pct >= 50:
        exits.append({'reason': 'option_profit_target', ...})
    
    # Exit 2: Option stop loss (-25%)
    if option_pnl_pct <= -25:
        exits.append({'reason': 'option_stop_loss', ...})
```

**Problem:** Options premiums swing ±25% in MINUTES due to:
- Bid-ask spread volatility
- Delta/gamma changes
- Implied volatility shifts
- Market maker adjustments

**Result:** Positions exit on normal premium noise, not actual losses.

## Evidence

Recent trades (from user report):
- NVDA 260306P00175000: Held 2 minutes
- AMD 260213P00207500: Held 1 minute  
- QCOM 260220P00145000: Closed at market open
- NOW 260220P00110000: Closed at market open

All closed with small P&L ($0.05-$0.20 per contract = $5-$20 total).

## Root Causes

### 1. Exit Thresholds Too Tight

Options need wider bands:
- Current: -25% stop / +50% target
- Needed: -40% stop / +80% target (minimum)

### 2. Duplicate Exit Logic

In `check_exit_conditions()`:

```python
# PROBLEM: Checks BOTH option-specific AND regular exits
if position['instrument_type'] in ('CALL', 'PUT'):
    option_exits = check_exit_conditions_options(position)  # Option premium exits
    exits_to_trigger.extend(option_exits)

# Then ALSO checks these (based on underlying price):
if current_price <= stop_loss:  # Wrong for options!
    exits_to_trigger.append({'reason': 'stop_loss', ...})
```

Options can exit on EITHER condition, causing premature exits.

### 3. No Minimum Hold Time

Options need time to develop - exiting in first 30 minutes captures only noise.

## Recommended Fix

### Fix 1: Widen Option Exit Thresholds

```python
def check_exit_conditions_options(position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Option-specific exit conditions
    Uses option premium P&L instead of underlying stock price
    
    CRITICAL FIX (2026-02-04): Widened stops from -25%/+50% to -40%/+80%
    and added 30-minute minimum hold time to prevent premature exits
    """
    exits = []
    
    try:
        current_price = float(position['current_price'])
        entry_price = float(position['entry_price'])
        
        # Calculate option P&L percentage
        option_pnl_pct = ((current_price / entry_price) - 1) * 100
        
        # Calculate hold time
        entry_time = position['entry_time']
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        hold_minutes = (now_utc - entry_time).total_seconds() / 60
        
        # MINIMUM HOLD TIME: Don't exit options in first 30 minutes
        # Options premiums are volatile - give them room to breathe
        # Exception: Allow exit if catastrophic loss (>50%)
        if hold_minutes < 30:
            if option_pnl_pct > -50:
                logger.debug(
                    f"Position {position['id']}: Too early to exit "
                    f"(held {hold_minutes:.1f} min, P&L {option_pnl_pct:.1f}%)"
                )
                return []  # Don't exit yet - too early
            else:
                logger.warning(
                    f"Position {position['id']}: Catastrophic loss {option_pnl_pct:.1f}%, "
                    f"exiting early at {hold_minutes:.1f} minutes"
                )
        
        # Exit 1: Option profit target (+80%, was +50%)
        # Widened to account for option premium volatility
        if option_pnl_pct >= 80:
            exits.append({
                'reason': 'option_profit_target',
                'priority': 1,
                'message': f'Option +{option_pnl_pct:.1f}% profit (target +80%)'
            })
        
        # Exit 2: Option stop loss (-40%, was -25%)
        # Widened to give premiums room to move with normal volatility
        if option_pnl_pct <= -40:
            exits.append({
                'reason': 'option_stop_loss',
                'priority': 1,
                'message': f'Option {option_pnl_pct:.1f}% loss (stop -40%)'
            })
        
        # Exit 3: Time decay risk (theta burn) - only if unprofitable near expiry
        if position['expiration_date']:
            exp_date = position['expiration_date']
            if isinstance(exp_date, str):
                from datetime import date
                exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()
            
            days_to_expiry = (exp_date - datetime.now().date()).days
            
            # If < 7 days to expiry and not profitable enough, exit to avoid theta decay
            # Increased threshold from 20% to 30% to be more conservative
            if days_to_expiry <= 7 and option_pnl_pct < 30:
                exits.append({
                    'reason': 'theta_decay_risk',
                    'priority': 2,
                    'message': f'{days_to_expiry} days to expiry, only +{option_pnl_pct:.1f}% profit'
                })
        
        return exits
        
    except Exception as e:
        logger.error(f"Error checking option exits for position {position['id']}: {e}")
        return []
```

### Fix 2: Remove Duplicate Exit Checking

```python
def check_exit_conditions(position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check all exit conditions for a position
    Returns list of triggered exits sorted by priority
    """
    exits_to_trigger = []
    
    # NEW: Check trailing stops (Phase 3)
    trailing_exit = check_trailing_stop(position)
    if trailing_exit:
        exits_to_trigger.append(trailing_exit)
    
    # CRITICAL FIX: For options, use ONLY option-specific exit logic
    # to avoid duplicate exit checking (was causing premature exits)
    if position['instrument_type'] in ('CALL', 'PUT'):
        option_exits = check_exit_conditions_options(position)
        exits_to_trigger.extend(option_exits)
        
        # Still check time-based exits (not price-based)
        exits_to_trigger.extend(check_time_based_exits(position))
        
        # Check for partial exits
        partial_exit = check_partial_exit(position)
        if partial_exit:
            exits_to_trigger.append(partial_exit)
        
        # Sort and return - DON'T check price-based stops below
        return sorted(exits_to_trigger, key=lambda x: x['priority'])
    
    # For STOCKS: Use original price-based exit logic
    current_price = float(position['current_price'])
    stop_loss = float(position['stop_loss'])
    take_profit = float(position['take_profit'])
    
    # ... rest of stock exit logic ...
```

### Fix 3: Update sync_from_alpaca_positions() Stop Calculation

```python
# In sync_from_alpaca_positions():
# CRITICAL FIX (2026-02-04): Widened option stops to match exit logic
if is_option:
    stop_loss = entry_price * 0.60  # -40% for options (was 0.75 = -25%)
    take_profit = entry_price * 1.80  # +80% for options (was 1.50 = +50%)
else:
    stop_loss = entry_price * 0.98  # -2% for stock
    take_profit = entry_price * 1.03  # +3% for stock
```

## Why CRM PUT When Stock is Rising?

The signal engine generates BUY_PUT when it detects:
- Bearish RSI divergence
- Downward momentum shift
- Overbought conditions reversing

CRM may be up +0.17% NOW, but the signal was generated earlier when technical indicators showed bearish setup. This is normal - signals are forward-looking, not reactive to current price.

## Impact

**Before Fix:**
- Options exit on ±25% premium noise
- Average hold time: 1-2 minutes
- Capturing bid-ask spread volatility, not real moves

**After Fix:**
- Options need ±40% move to exit
- Minimum 30-minute hold time
- Only exit on real losses or significant profits
- Expected hold time: 30-240 minutes

## Deployment

1. Update `services/position_manager/monitor.py` with fixes
2. Rebuild position manager Docker image
3. Deploy to ECS
4. Monitor next trades for improved hold times

## Testing

After deployment, verify:
- Options held for at least 30 minutes (unless catastrophic loss)
- No exits on small premium swings (±10-20%)
- Exits only on real moves (±40%+) or time-based triggers
