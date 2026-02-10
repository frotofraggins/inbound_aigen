# Risk State Machine - Complete Implementation Plan
**Date:** 2026-02-10  
**Priority:** P0 - Improve 28.6% win rate to 50-60%  
**Approach:** Professional risk management without touching prediction logic

---

## Executive Summary

**Goal:** Transform from basic trading to professional risk-managed system

**Method:** Add lifecycle states that protect winners, reduce losers, take early profits

**Expected Impact:**
- Win rate: 28.6% → 45-55%
- Avg loss: -15.8% → -8% to -10%
- Profit factor: <1.0 → 1.5-2.0
- Max drawdown: -52% → -30%

---

## Architecture Overview

### Current Flow
```
Signal → Dispatcher → Position Manager → Exit (simple stops)
```

### New Flow
```
Signal → Dispatcher → Position Manager with State Machine → Smart Exits
                              ↓
                    Track profit evolution
                              ↓
                    Adjust behavior per state
                              ↓
                    Execute state-specific actions
```

---

## State Definitions

### State Lifecycle
```
NEW (just opened)
  ↓
OPEN (baseline risk)
  ↓ profit >= 10%
PROFIT_PROTECTED (stop at breakeven)
  ↓ profit >= 20%
PARTIAL_TAKEN (took 40%, riding 60%)
  ↓ profit >= 30%
TRAILING (lock in gains progressively)
  ↓ exit triggered
EXIT_PENDING (order submitted)
  ↓
CLOSED (in position_history)
```

### State Behaviors

| State | Stop Loss | Take Profit | Special Actions |
|-------|-----------|-------------|-----------------|
| NEW | -40% | +80% | None |
| OPEN | -40% | +80% | Watch for breakeven |
| PROFIT_PROTECTED | 0% (breakeven) | +80% | Protected from loss |
| PARTIAL_TAKEN | 0% (breakeven) | +80% on remaining | 40% locked in |
| TRAILING | Progressive trail | None | Lock 70-85% of peak |
| EXIT_PENDING | N/A | N/A | Awaiting fill |
| CLOSED | N/A | N/A | In history |

---

## Implementation Phases

### Phase 1: Database Schema (30 min)
- Add lifecycle fields to active_positions
- Create position_state_history audit table
- Create config table for tunables
- Migration script + deployment

### Phase 2: State Machine Core (60 min)
- Create state_machine.py module
- Implement state transition logic
- Add state-specific exit checks
- Unit tests for state transitions

### Phase 3: Position Manager Integration (45 min)
- Update monitor.py to use state machine
- Add peak tracking
- Add partial profit execution
- Add progressive trailing stops

### Phase 4: Configuration (15 min)
- Create config/trade_management.json
- Add loader in position manager
- Feature flag for enable/disable

### Phase 5: Testing & Validation (90 min)
- Backtest on 28 historical trades
- Calculate expected improvement
- Dry run with paper trading
- Verify state transitions work

### Phase 6: Deployment (30 min)
- Deploy DB migration
- Deploy updated services
- Enable feature flag
- Monitor first 10 trades

**Total Time:** ~4.5 hours

---

## Detailed Implementation

### 1. Database Migration

**File:** `db/migrations/1034_risk_state_machine.sql`

```sql
-- Add lifecycle management columns to active_positions
ALTER TABLE active_positions 
ADD COLUMN IF NOT EXISTS lifecycle_state TEXT DEFAULT 'OPEN',
ADD COLUMN IF NOT EXISTS peak_price FLOAT,
ADD COLUMN IF NOT EXISTS partial_taken BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS partial_qty_sold FLOAT DEFAULT 0,
ADD COLUMN IF NOT EXISTS breakeven_armed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS trail_price FLOAT,
ADD COLUMN IF NOT EXISTS trail_level INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_state_change TIMESTAMP,
ADD COLUMN IF NOT EXISTS state_change_count INT DEFAULT 0;

-- Create state transition audit table
CREATE TABLE IF NOT EXISTS position_state_history (
    id SERIAL PRIMARY KEY,
    position_id INT REFERENCES active_positions(id),
    old_state TEXT,
    new_state TEXT,
    reason TEXT,
    profit_pct FLOAT,
    peak_price FLOAT,
    current_price FLOAT,
    changed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_state_history_position 
ON position_state_history(position_id, changed_at DESC);

-- Create trade management config table
CREATE TABLE IF NOT EXISTS trade_management_config (
    id SERIAL PRIMARY KEY,
    config_version INT NOT NULL,
    breakeven_trigger FLOAT NOT NULL,
    partial_profit_trigger FLOAT NOT NULL,
    partial_size FLOAT NOT NULL,
    time_stop_minutes INT NOT NULL,
    min_progress_pct FLOAT NOT NULL,
    trail_levels JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert default config
INSERT INTO trade_management_config (
    config_version,
    breakeven_trigger,
    partial_profit_trigger,
    partial_size,
    time_stop_minutes,
    min_progress_pct,
    trail_levels,
    enabled
) VALUES (
    1,
    0.10,  -- Move to breakeven at +10%
    0.20,  -- Take partial at +20%
    0.40,  -- Take 40% partial
    240,   -- 4 hour time stop
    0.05,  -- Need 5% progress per hour
    '[
        {"profit": 0.20, "keep": 0.70, "name": "tier1"},
        {"profit": 0.40, "keep": 0.80, "name": "tier2"},
        {"profit": 0.60, "keep": 0.85, "name": "tier3"}
    ]'::jsonb,
    true
) ON CONFLICT DO NOTHING;
```

---

### 2. State Machine Module

**File:** `services/position_manager/state_machine.py`

```python
"""
Trade Lifecycle State Machine
Professional risk management through state-based behavior
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

# State definitions
STATE_NEW = 'NEW'
STATE_OPEN = 'OPEN'
STATE_PROFIT_PROTECTED = 'PROFIT_PROTECTED'
STATE_PARTIAL_TAKEN = 'PARTIAL_TAKEN'
STATE_TRAILING = 'TRAILING'
STATE_EXIT_PENDING = 'EXIT_PENDING'
STATE_CLOSED = 'CLOSED'


class TradeStateMachine:
    """
    Manages trade lifecycle states and transitions
    
    Principles:
    1. States are mutually exclusive
    2. Transitions are one-way (mostly)
    3. Each state has specific allowed actions
    4. All transitions are logged
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize with configuration
        
        Args:
            config: Dict with breakeven_trigger, partial_profit_trigger, 
                    partial_size, trail_levels, etc.
        """
        self.config = config
        self.breakeven_trigger = config['breakeven_trigger']  # 0.10 = +10%
        self.partial_trigger = config['partial_profit_trigger']  # 0.20 = +20%
        self.partial_size = config['partial_size']  # 0.40 = 40%
        self.trail_levels = config['trail_levels']  # List of {profit, keep}
        self.time_stop_minutes = config.get('time_stop_minutes', 240)
        self.min_progress_pct = config.get('min_progress_pct', 0.05)
    
    def evaluate_transitions(
        self,
        position: Dict[str, Any],
        current_price: float,
        peak_price: float
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all possible state transitions for a position
        
        Returns:
            List of possible transitions with reasons and actions
        """
        transitions = []
        
        current_state = position.get('lifecycle_state', STATE_OPEN)
        entry_price = float(position['entry_price'])
        entry_time = position['entry_time']
        
        # Calculate metrics
        profit_pct = (current_price - entry_price) / entry_price
        time_in_trade = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
        
        # Check OPEN → PROFIT_PROTECTED
        if current_state == STATE_OPEN:
            if profit_pct >= self.breakeven_trigger:
                transitions.append({
                    'from_state': STATE_OPEN,
                    'to_state': STATE_PROFIT_PROTECTED,
                    'reason': f'Profit {profit_pct*100:.1f}% >= {self.breakeven_trigger*100:.0f}% trigger',
                    'actions': ['move_stop_to_breakeven'],
                    'priority': 1
                })
        
        # Check PROFIT_PROTECTED → PARTIAL_TAKEN
        if current_state == STATE_PROFIT_PROTECTED:
            if profit_pct >= self.partial_trigger and not position.get('partial_taken'):
                transitions.append({
                    'from_state': STATE_PROFIT_PROTECTED,
                    'to_state': STATE_PARTIAL_TAKEN,
                    'reason': f'Profit {profit_pct*100:.1f}% >= {self.partial_trigger*100:.0f}% trigger',
                    'actions': ['execute_partial_exit'],
                    'priority': 1
                })
        
        # Check for TRAILING (from PARTIAL_TAKEN or PROFIT_PROTECTED)
        if current_state in (STATE_PROFIT_PROTECTED, STATE_PARTIAL_TAKEN):
            # Check if we've hit any trail level
            for i, level in enumerate(self.trail_levels):
                if profit_pct >= level['profit']:
                    current_level = position.get('trail_level', 0)
                    if i >= current_level:  # New level reached
                        transitions.append({
                            'from_state': current_state,
                            'to_state': STATE_TRAILING,
                            'reason': f'Hit trail level {i+1}: {profit_pct*100:.1f}% >= {level["profit"]*100:.0f}%',
                            'actions': ['update_trail_stop'],
                            'priority': 2,
                            'trail_level': i,
                            'keep_pct': level['keep']
                        })
                        break
        
        # Check time pressure (any state)
        if time_in_trade > self.time_stop_minutes:
            progress_required = (time_in_trade / 60) * self.min_progress_pct
            if profit_pct < progress_required:
                transitions.append({
                    'from_state': current_state,
                    'to_state': STATE_EXIT_PENDING,
                    'reason': f'Time stop: {time_in_trade:.0f}min, profit {profit_pct*100:.1f}% < required {progress_required*100:.1f}%',
                    'actions': ['force_exit'],
                    'priority': 3
                })
        
        return sorted(transitions, key=lambda x: x['priority'])
    
    def check_trail_hit(
        self,
        position: Dict[str, Any],
        current_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Check if trailing stop was hit
        
        Returns:
            Exit dict if trail hit, None otherwise
        """
        trail_price = position.get('trail_price')
        
        if trail_price and current_price <= trail_price:
            entry_price = float(position['entry_price'])
            locked_pct = (trail_price - entry_price) / entry_price
            
            return {
                'reason': 'trailing_stop',
                'priority': 1,
                'message': f'Trail stop hit: ${current_price:.2f} <= ${trail_price:.2f}, locking {locked_pct*100:.1f}% gain'
            }
        
        return None
    
    def calculate_trail_price(
        self,
        entry_price: float,
        peak_price: float,
        keep_pct: float
    ) -> float:
        """
        Calculate trailing stop price
        
        Args:
            entry_price: Original entry
            peak_price: Highest price seen
            keep_pct: Percentage of gains to keep (0.70 = 70%)
        
        Returns:
            Trail stop price
        """
        peak_gain = peak_price - entry_price
        trail_price = entry_price + (peak_gain * keep_pct)
        return trail_price
```

---

### 3. Configuration File

**File:** `config/trade_management.json`

```json
{
  "version": 1,
  "enabled": true,
  "description": "Professional trade management with lifecycle states",
  
  "breakeven_protection": {
    "trigger_profit_pct": 0.10,
    "description": "Move stop to breakeven at +10% profit"
  },
  
  "partial_profits": {
    "trigger_profit_pct": 0.20,
    "partial_size_pct": 0.40,
    "description": "Take 40% off at +20% profit"
  },
  
  "trailing_stops": {
    "levels": [
      {
        "name": "tier1",
        "profit_trigger": 0.20,
        "keep_pct": 0.70,
        "description": "At +20% profit, trail at 70% (lock +14%)"
      },
      {
        "name": "tier2",
        "profit_trigger": 0.40,
        "keep_pct": 0.80,
        "description": "At +40% profit, trail at 80% (lock +32%)"
      },
      {
        "name": "tier3",
        "profit_trigger": 0.60,
        "keep_pct": 0.85,
        "description": "At +60% profit, trail at 85% (lock +51%)"
      }
    ]
  },
  
  "time_management": {
    "time_stop_minutes": 240,
    "min_progress_per_hour_pct": 0.05,
    "description": "If holding > 4h with < 5%/hour progress, consider exit"
  },
  
  "options_specific": {
    "day_trade_aggressive_trail": true,
    "swing_trade_conservative_trail": true,
    "market_close_exit_time": "15:55",
    "description": "Different trails for day vs swing trades"
  }
}
```

---

### 4. Position Manager Updates

**File:** `services/position_manager/risk_manager.py` (NEW)

```python
"""
Risk Management - State-based trade management
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
import json

import db
from state_machine import TradeStateMachine
from config import load_trade_management_config

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Professional risk management using lifecycle states
    
    Responsibilities:
    1. Track peak prices
    2. Evaluate state transitions
    3. Execute state-specific actions
    4. Maintain audit trail
    """
    
    def __init__(self):
        """Initialize with config"""
        self.config = load_trade_management_config()
        self.state_machine = TradeStateMachine(self.config)
        self.enabled = self.config.get('enabled', True)
        
        if self.enabled:
            logger.info("✓ Risk State Machine ENABLED")
        else:
            logger.warning("⚠ Risk State Machine DISABLED (legacy mode)")
    
    def process_position(
        self,
        position: Dict[str, Any],
        current_price: float
    ) -> List[Dict[str, Any]]:
        """
        Process a position through risk state machine
        
        Returns:
            List of actions to execute (exits, updates, etc.)
        """
        if not self.enabled:
            return []  # Skip if disabled
        
        actions = []
        
        try:
            entry_price = float(position['entry_price'])
            peak_price = position.get('peak_price') or current_price
            
            # 1. Update peak if new high
            if current_price > peak_price:
                peak_price = current_price
                db.update_position_peak(position['id'], peak_price)
                logger.info(f"Position {position['id']}: New peak ${peak_price:.2f}")
            
            # 2. Check if trail stop hit (priority check)
            trail_exit = self.state_machine.check_trail_hit(position, current_price)
            if trail_exit:
                actions.append(trail_exit)
                return actions  # Exit immediately
            
            # 3. Evaluate state transitions
            transitions = self.state_machine.evaluate_transitions(
                position, current_price, peak_price
            )
            
            # 4. Execute first (highest priority) transition
            if transitions:
                transition = transitions[0]
                
                # Execute transition actions
                for action_type in transition['actions']:
                    action = self._execute_action(
                        position,
                        action_type,
                        transition,
                        current_price,
                        entry_price,
                        peak_price
                    )
                    if action:
                        actions.append(action)
                
                # Update position state
                self._record_state_change(
                    position['id'],
                    transition['from_state'],
                    transition['to_state'],
                    transition['reason'],
                    (current_price - entry_price) / entry_price,
                    peak_price,
                    current_price
                )
                
                db.update_position_state(
                    position['id'],
                    transition['to_state']
                )
            
            return actions
            
        except Exception as e:
            logger.error(f"Error in risk manager for position {position['id']}: {e}")
            return []
    
    def _execute_action(
        self,
        position: Dict[str, Any],
        action_type: str,
        transition: Dict[str, Any],
        current_price: float,
        entry_price: float,
        peak_price: float
    ) -> Optional[Dict[str, Any]]:
        """Execute a state-specific action"""
        
        if action_type == 'move_stop_to_breakeven':
            # Update stop loss to entry price (protect profits)
            db.update_position_stop(position['id'], entry_price)
            db.update_position_breakeven_armed(position['id'], True)
            
            logger.info(
                f"Position {position['id']}: BREAKEVEN ARMED at ${entry_price:.2f} "
                f"(profit {((current_price-entry_price)/entry_price)*100:.1f}%)"
            )
            return None  # No exit, just update
        
        elif action_type == 'execute_partial_exit':
            # Calculate quantity to sell
            total_qty = float(position['quantity'])
            qty_to_sell = int(total_qty * self.config['partial_size'])
            qty_remaining = total_qty - qty_to_sell
            
            logger.info(
                f"Position {position['id']}: PARTIAL EXIT triggered "
                f"(selling {qty_to_sell} of {total_qty}, keeping {qty_remaining})"
            )
            
            return {
                'type': 'partial',
                'quantity': qty_to_sell,
                'reason': 'partial_profit_target',
                'priority': 1,
                'message': f'Taking {self.config["partial_size"]*100:.0f}% off at {((current_price-entry_price)/entry_price)*100:.1f}% profit'
            }
        
        elif action_type == 'update_trail_stop':
            # Calculate new trail price
            trail_level = transition['trail_level']
            keep_pct = transition['keep_pct']
            
            trail_price = self.state_machine.calculate_trail_price(
                entry_price, peak_price, keep_pct
            )
            
            db.update_position_trail(
                position['id'],
                trail_price,
                trail_level
            )
            
            locked_pct = (trail_price - entry_price) / entry_price
            
            logger.info(
                f"Position {position['id']}: TRAIL UPDATED level {trail_level+1} "
                f"at ${trail_price:.2f} (locking {locked_pct*100:.1f}% gain)"
            )
            return None  # No exit yet
        
        elif action_type == 'force_exit':
            # Time stop triggered
            return {
                'type': 'full',
                'reason': 'time_stop_insufficient_progress',
                'priority': 3,
                'message': transition['reason']
            }
        
        return None
    
    def _record_state_change(
        self,
        position_id: int,
        old_state: str,
        new_state: str,
        reason: str,
        profit_pct: float,
        peak_price: float,
        current_price: float
    ) -> None:
        """Record state transition in audit table"""
        try:
            db.insert_state_history(
                position_id=position_id,
                old_state=old_state,
                new_state=new_state,
                reason=reason,
                profit_pct=profit_pct,
                peak_price=peak_price,
                current_price=current_price
            )
            logger.info(f"State change: {old_state} → {new_state} ({reason})")
        except Exception as e:
            logger.error(f"Failed to record state change: {e}")
```

---

### 5. Database Functions

**Add to:** `services/position_manager/db.py`

```python
def update_position_state(position_id: int, new_state: str) -> None:
    """Update position lifecycle state"""
    query = """
    UPDATE active_positions
    SET lifecycle_state = %s,
        last_state_change = NOW(),
        state_change_count = state_change_count + 1
    WHERE id = %s
    """
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (new_state, position_id))
            db.conn.commit()


def update_position_stop(position_id: int, new_stop: float) -> None:
    """Update stop loss price"""
    query = """
    UPDATE active_positions
    SET stop_loss = %s
    WHERE id = %s
    """
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (new_stop, position_id))
            db.conn.commit()


def update_position_breakeven_armed(position_id: int, armed: bool) -> None:
    """Mark breakeven protection as armed"""
    query = """
    UPDATE active_positions
    SET breakeven_armed = %s
    WHERE id = %s
    """
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (armed, position_id))
            db.conn.commit()


def update_position_trail(position_id: int, trail_price: float, trail_level: int) -> None:
    """Update trailing stop price and level"""
    query = """
    UPDATE active_positions
    SET trail_price = %s,
        trail_level = %s
    WHERE id = %s
    """
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (trail_price, trail_level, position_id))
            db.conn.commit()


def mark_partial_taken(position_id: int, qty_sold: float) -> None:
    """Mark that partial profit was taken"""
    query = """
    UPDATE active_positions
    SET partial_taken = TRUE,
        partial_qty_sold = %s,
        quantity = quantity - %s
    WHERE id = %s
    """
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (qty_sold, qty_sold, position_id))
            db.conn.commit()


def insert_state_history(
    position_id: int,
    old_state: str,
    new_state: str,
    reason: str,
    profit_pct: float,
    peak_price: float,
    current_price: float
) -> None:
    """Insert state change into audit table"""
    query = """
    INSERT INTO position_state_history (
        position_id, old_state, new_state, reason,
        profit_pct, peak_price, current_price
    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (
                position_id, old_state, new_state, reason,
                profit_pct, peak_price, current_price
            ))
            db.conn.commit()
```

---

### 6. Integration into Position Manager

**Update:** `services/position_manager/main.py`

```python
# Add at top
from risk_manager import RiskManager

# In main() function, after initializing bar_fetcher:
# Initialize risk manager
risk_manager = RiskManager()
logger.info(f"✓ Risk manager initialized (enabled: {risk_manager.enabled})")

# In position processing loop, after update_position_price():

# NEW: Process through risk state machine
risk_actions = risk_manager.process_position(position, position['current_price'])

# Execute risk actions BEFORE regular exit checks
for action in risk_actions:
    if action.get('type') == 'partial':
        # Partial exit
        success = exits.execute_partial_exit(
            position,
            action['quantity'],
            action['reason']
        )
        if success:
            positions_updated += 1
            continue  # Don't check other exits
    elif action.get('type') == 'full':
        # Full exit from risk manager
        success = exits.force_close_position(
            position,
            action['reason'],
            action['priority']
        )
        if success:
            positions_closed += 1
            continue  # Position closed, skip rest
```

---

## Backtest Expected Results

### Replay on 28 Historical Trades

**Current outcomes:**
- 8 winners (28.6%)
- 20 losers (71.4%)
- Avg: -15.8%

**With risk state machine (estimated):**

**Breakeven protection (+10% → 0%):**
- Saves: ~5 trades that went +10% then reversed to loss
- Impact: 5 losers → scratches
- New: 8 winners, 15 losers, 5 scratches (35% win rate)

**Partial profits (+20% → take 40%):**
- Saves: ~3 trades that hit +20% then reversed
- Locks in: +8% avg on those 3 (instead of -15%)
- Impact: +$600-800 profit

**Trailing stops (+20/40/60%):**
- Saves: ~4 peak reversals
- Converts: 4 losers → small winners
- Impact: +$400-600 profit

**Expected new results:**
- Winners: 12-13 (43-46% win rate)
- Losers: 10-12 (smaller losses)
- Scratches: 3-5
- Avg P&L: -5% to +2%

**Improvement:** Win rate 28.6% → 45%, Avg loss -15.8% → -5%

---

## Deployment Sequence

### Step 1: Deploy Database Migration (10 min)

```bash
# Create migration
cd db/migrations
# (migration already shown above)

# Deploy via db-migrator
docker build -f services/db_migrator/Dockerfile -t ops-pipeline/db-migrator:latest .
docker push ...
aws ecs run-task ...
```

### Step 2: Add Config File (5 min)

```bash
# Upload config
aws ssm put-parameter \
  --name /ops-pipeline/trade-management-config \
  --value file://config/trade_management.json \
  --type String \
  --region us-west-2
```

### Step 3: Deploy Position Manager (20 min)

```bash
# Already have script
cd services/position_manager
# Add state_machine.py, risk_manager.py
# Update main.py
docker build ...
docker push ...
aws ecs update-service --force-new-deployment ...
```

### Step 4: Verify (30 min)

```bash
# Watch logs
aws logs tail /ecs/ops-pipeline/position-manager --follow

# Look for:
# "Risk manager initialized (enabled: True)"
# "State change: OPEN → PROFIT_PROTECTED"
# "BREAKEVEN ARMED at $X.XX"
```

### Step 5: Monitor First 10 Trades

- Check state transitions happen
- Verify partials execute
- Confirm trails update
- Compare vs legacy exits

---

## Rollback Plan

### Feature Flag

**If issues occur:**

```json
{
  "enabled": false  // Disable risk state machine
}
```

Update SSM parameter, services will reload on next run.

**Fallback:** System reverts to original exit logic

### Full Rollback

```bash
# Revert to previous Docker image
aws ecs update-service \
  --cluster ops-pipeline-cluster \
  --service position-manager-service \
  --task-definition position-manager-service:8 \  # Previous version
  --force-new-deployment
```

---

## Success Metrics

### Week 1 (Initial Validation)
- ✓ State transitions working
- ✓ No system errors
- ✓ Partials executing correctly
- Target: No regressions

### Week 2-3 (Early Results)
- Win rate: 35-40% (from 28.6%)
- Avg loss: -10% to -12% (from -15.8%)
- Max loss: -35% (from -52%)
- Target: Visible improvement

### Week 4-6 (Mature Results)
- Win rate: 40-50%
- Avg P&L: 0% to +5%
- Profit factor: 1.2-1.5
- Target: Consistent profitability

---

## Why This Works

### Mathematics

**Current:** 28.6% win rate, avg winner +30%, avg loser -25%
- Expected value: (0.286 * 30%) + (0.714 * -25%) = -9.
