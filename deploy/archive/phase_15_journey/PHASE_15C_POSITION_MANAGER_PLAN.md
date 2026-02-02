# Phase 15C: Position Manager Implementation Plan

**Date:** 2026-01-26  
**Priority:** CRITICAL  
**Timeline:** 1 week  
**Lines of Code:** ~300

---

## 🎯 Objective

Build a service that monitors all open positions and guarantees safe exits, protecting against:
- Failed bracket orders
- Day trades held overnight
- Options expiring worthless
- Partial fills without proper exit orders
- Runaway losses

---

## 🏗️ Architecture

### Service: `services/position_manager/`

**Schedule:** Every 1 minute (EventBridge)  
**Environment:** ECS Fargate (VPC access to RDS)  
**Purpose:** Monitor and enforce exit rules for all open positions

### Components

```
services/position_manager/
├── main.py           # Entry point, orchestrates monitoring
├── config.py         # Configuration, thresholds, schedule
├── db.py            # Database operations
├── monitor.py       # Position monitoring logic
├── exits.py         # Exit enforcement logic
├── Dockerfile       # Container definition
└── requirements.txt # Dependencies
```

---

## 📊 Database Schema (Migration 009)

### Table: `active_positions`

Tracks all currently open positions:

```sql
CREATE TABLE active_positions (
    id SERIAL PRIMARY KEY,
    execution_id INTEGER REFERENCES dispatch_executions(id),
    ticker VARCHAR(10) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL, -- 'STOCK', 'CALL', 'PUT'
    strategy_type VARCHAR(20) NOT NULL,   -- 'day_trade', 'swing_trade'
    
    -- Position details
    side VARCHAR(10) NOT NULL,            -- 'long', 'short'
    quantity DECIMAL(12, 4) NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    
    -- Options specifics
    strike_price DECIMAL(12, 4),
    expiration_date DATE,
    
    -- Exit parameters
    stop_loss DECIMAL(12, 4),
    take_profit DECIMAL(12, 4),
    max_hold_minutes INTEGER,
    
    -- Bracket order tracking
    bracket_order_accepted BOOLEAN DEFAULT FALSE,
    stop_order_id VARCHAR(100),
    target_order_id VARCHAR(100),
    
    -- Monitoring
    current_price DECIMAL(12, 4),
    current_pnl_dollars DECIMAL(12, 4),
    current_pnl_percent DECIMAL(8, 4),
    last_checked_at TIMESTAMP,
    check_count INTEGER DEFAULT 0,
    
    -- Status
    status VARCHAR(20) DEFAULT 'open',    -- 'open', 'closing', 'closed'
    close_reason VARCHAR(50),             -- 'stop_loss', 'take_profit', 'time_exit', 'forced_close', 'expiration'
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE INDEX idx_active_positions_status ON active_positions(status);
CREATE INDEX idx_active_positions_ticker ON active_positions(ticker);
CREATE INDEX idx_active_positions_expiration ON active_positions(expiration_date) WHERE expiration_date IS NOT NULL;
```

### Table: `position_events`

Logs all position monitoring events:

```sql
CREATE TABLE position_events (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES active_positions(id),
    event_type VARCHAR(50) NOT NULL,      -- 'check', 'price_update', 'exit_triggered', 'order_failed', 'closed'
    event_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_position_events_position ON position_events(position_id);
CREATE INDEX idx_position_events_type ON position_events(event_type);
```

### View: `v_open_positions_summary`

Real-time view of all open positions:

```sql
CREATE OR REPLACE VIEW v_open_positions_summary AS
SELECT 
    ap.id,
    ap.ticker,
    ap.instrument_type,
    ap.strategy_type,
    ap.quantity,
    ap.entry_price,
    ap.current_price,
    ap.current_pnl_dollars,
    ap.current_pnl_percent,
    ap.stop_loss,
    ap.take_profit,
    ap.entry_time,
    ap.expiration_date,
    EXTRACT(EPOCH FROM (NOW() - ap.entry_time))/60 AS hold_minutes,
    ap.max_hold_minutes,
    CASE 
        WHEN ap.expiration_date IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (ap.expiration_date - NOW()))/3600 
        ELSE NULL 
    END AS hours_to_expiration,
    ap.bracket_order_accepted,
    ap.last_checked_at,
    ap.check_count
FROM active_positions ap
WHERE ap.status = 'open'
ORDER BY ap.entry_time DESC;
```

---

## 🔍 Monitoring Logic

### 1. Position Discovery

On each run (every 1 minute):

```python
# Find all executions that became open positions since last check
def sync_positions():
    # Get recent executions that are FILLED
    recent_executions = get_filled_executions_since(last_sync_time)
    
    for execution in recent_executions:
        if not position_exists(execution.id):
            create_active_position(execution)
    
    # Get all open positions
    return get_open_positions()
```

### 2. Price Updates

For each open position:

```python
def update_position_price(position):
    # Fetch current price from Alpaca
    if position.instrument_type == 'STOCK':
        current_price = alpaca.get_latest_trade(position.ticker)
    else:  # OPTIONS
        current_price = alpaca.get_option_price(
            position.ticker,
            position.strike_price,
            position.expiration_date,
            position.instrument_type  # CALL or PUT
        )
    
    # Calculate P&L
    pnl_dollars = (current_price - position.entry_price) * position.quantity
    pnl_percent = ((current_price / position.entry_price) - 1) * 100
    
    # Update database
    update_position(
        position.id,
        current_price=current_price,
        current_pnl_dollars=pnl_dollars,
        current_pnl_percent=pnl_percent,
        last_checked_at=now(),
        check_count=position.check_count + 1
    )
    
    log_event(position.id, 'price_update', {
        'price': current_price,
        'pnl': pnl_dollars,
        'pnl_pct': pnl_percent
    })
```

### 3. Exit Condition Checks

```python
def check_exit_conditions(position):
    exits_to_trigger = []
    
    # Check 1: Stop loss hit
    if position.current_price <= position.stop_loss:
        exits_to_trigger.append({
            'reason': 'stop_loss',
            'priority': 1,
            'message': f'Stop loss hit: {position.current_price} <= {position.stop_loss}'
        })
    
    # Check 2: Take profit hit
    if position.current_price >= position.take_profit:
        exits_to_trigger.append({
            'reason': 'take_profit',
            'priority': 1,
            'message': f'Take profit hit: {position.current_price} >= {position.take_profit}'
        })
    
    # Check 3: Day trade time limit (3:55 PM ET = 20:55 UTC)
    if position.strategy_type == 'day_trade':
        now_et = get_eastern_time()
        if now_et.hour == 15 and now_et.minute >= 55:
            exits_to_trigger.append({
                'reason': 'day_trade_close',
                'priority': 2,
                'message': 'Day trade must close by 3:55 PM ET'
            })
    
    # Check 4: Max hold time exceeded
    hold_minutes = (now() - position.entry_time).total_seconds() / 60
    if hold_minutes >= position.max_hold_minutes:
        exits_to_trigger.append({
            'reason': 'max_hold_time',
            'priority': 3,
            'message': f'Max hold time exceeded: {hold_minutes} >= {position.max_hold_minutes}'
        })
    
    # Check 5: Options expiration (close 1 day before)
    if position.expiration_date:
        hours_to_expiry = (position.expiration_date - now()).total_seconds() / 3600
        if hours_to_expiry <= 24:
            exits_to_trigger.append({
                'reason': 'expiration_risk',
                'priority': 2,
                'message': f'Options expiring in {hours_to_expiry:.1f} hours'
            })
    
    # Check 6: Bracket order verification
    if not position.bracket_order_accepted:
        # Verify with Alpaca if bracket orders exist
        has_brackets = verify_bracket_orders(position)
        if not has_brackets:
            exits_to_trigger.append({
                'reason': 'missing_brackets',
                'priority': 1,
                'message': 'Bracket orders not found, forcing manual exit'
            })
    
    return sorted(exits_to_trigger, key=lambda x: x['priority'])
```

---

## 🚪 Exit Enforcement

### Force Close Logic

```python
def force_close_position(position, reason, priority):
    """
    Force close a position immediately
    """
    try:
        # Log the exit trigger
        log_event(position.id, 'exit_triggered', {
            'reason': reason,
            'priority': priority,
            'current_price': position.current_price,
            'pnl': position.current_pnl_dollars
        })
        
        # Update status to closing
        update_position_status(position.id, 'closing')
        
        # Submit market order to close
        if position.instrument_type == 'STOCK':
            order = alpaca.submit_order(
                symbol=position.ticker,
                qty=position.quantity,
                side='sell',  # Always sell to close long positions
                type='market',
                time_in_force='day'
            )
        else:  # OPTIONS
            order = alpaca.close_option_position(
                symbol=position.ticker,
                strike=position.strike_price,
                expiration=position.expiration_date,
                option_type=position.instrument_type,
                qty=position.quantity
            )
        
        # Update with close details
        update_position(
            position.id,
            status='closed',
            close_reason=reason,
            closed_at=now()
        )
        
        log_event(position.id, 'closed', {
            'order_id': order.id,
            'reason': reason,
            'final_price': position.current_price,
            'final_pnl': position.current_pnl_dollars
        })
        
        return True
        
    except Exception as e:
        log_event(position.id, 'order_failed', {
            'reason': reason,
            'error': str(e)
        })
        return False
```

### Partial Fill Handling

```python
def handle_partial_fills(position):
    """
    Check if original order was partially filled
    and ensure exit orders match filled quantity
    """
    # Get original execution
    execution = get_execution(position.execution_id)
    
    # Query Alpaca for actual filled quantity
    alpaca_position = alpaca.get_position(position.ticker)
    
    if alpaca_position:
        actual_qty = alpaca_position.qty
        
        if actual_qty != position.quantity:
            # Partial fill detected
            log_event(position.id, 'partial_fill_detected', {
                'expected': position.quantity,
                'actual': actual_qty
            })
            
            # Update position quantity
            update_position(position.id, quantity=actual_qty)
            
            # Cancel and resubmit bracket orders with correct quantity
            if position.stop_order_id:
                alpaca.cancel_order(position.stop_order_id)
            if position.target_order_id:
                alpaca.cancel_order(position.target_order_id)
            
            # Resubmit with correct quantity
            resubmit_bracket_orders(position, actual_qty)
```

---

## 📈 Monitoring Flow

### Main Loop (Every 1 Minute)

```python
def main():
    """
    Position manager main loop
    Runs every 1 minute via EventBridge
    """
    logger.info("Position manager starting")
    
    # Step 1: Sync positions from executions
    sync_positions()
    
    # Step 2: Get all open positions
    open_positions = get_open_positions()
    logger.info(f"Found {len(open_positions)} open positions")
    
    # Step 3: Monitor each position
    for position in open_positions:
        try:
            # Update price
            update_position_price(position)
            
            # Check for partial fills
            handle_partial_fills(position)
            
            # Check exit conditions
            exit_triggers = check_exit_conditions(position)
            
            # If any exits triggered, close position
            if exit_triggers:
                top_trigger = exit_triggers[0]
                logger.warning(
                    f"Exit triggered for {position.ticker}: {top_trigger['message']}"
                )
                force_close_position(
                    position,
                    top_trigger['reason'],
                    top_trigger['priority']
                )
            
        except Exception as e:
            logger.error(f"Error monitoring position {position.id}: {e}")
            log_event(position.id, 'monitor_error', {'error': str(e)})
    
    logger.info("Position manager completed")
```

---

## 🔔 Alerts & Notifications

### Critical Alerts (Email)

Send email for:
1. **Exit triggered** - Position closed by position manager
2. **Bracket order missing** - Manual intervention needed
3. **Order failure** - Couldn't close position
4. **Expiration warning** - Options expiring in <24 hours

### Log Alerts

Log to CloudWatch for:
- Every position check (INFO)
- Price updates (DEBUG)
- Exit triggers (WARNING)
- Order failures (ERROR)

---

## 🧪 Testing Plan

### Unit Tests

```python
def test_stop_loss_trigger():
    position = create_test_position(
        entry_price=100,
        stop_loss=95,
        current_price=94
    )
    exits = check_exit_conditions(position)
    assert len(exits) > 0
    assert exits[0]['reason'] == 'stop_loss'

def test_day_trade_time_limit():
    position = create_test_position(
        strategy_type='day_trade',
        entry_time=datetime(2026, 1, 26, 14, 0)  # 2 PM ET
    )
    # Mock time to 3:56 PM ET
    exits = check_exit_conditions(position)
    assert any(e['reason'] == 'day_trade_close' for e in exits)

def test_options_expiration():
    position = create_test_position(
        instrument_type='CALL',
        expiration_date=datetime(2026, 1, 27)  # Tomorrow
    )
    exits = check_exit_conditions(position)
    assert any(e['reason'] == 'expiration_risk' for e in exits)
```

### Integration Tests

1. **Test with paper trading:**
   - Execute a trade
   - Verify position created in active_positions
   - Wait for position manager to detect
   - Verify price updates every minute
   - Trigger stop loss, verify close

2. **Test day trade close:**
   - Execute day trade at 3:50 PM ET
   - Wait until 3:55 PM ET
   - Verify forced close

3. **Test options expiration:**
   - Execute options trade expiring tomorrow
   - Verify forced close within 24 hours

---

## 📦 Deployment

### Build & Push Docker Image

```bash
# Build from repo root
cd /home/nflos/workplace/inbound_aigen
docker build -f services/position_manager/Dockerfile -t position-manager:latest .

# Tag for ECR
docker tag position-manager:latest \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest

# Push to ECR
docker push \
  160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest
```

### ECS Task Definition

```json
{
  "family": "position-manager",
  "containerDefinitions": [{
    "name": "position-manager",
    "image": "160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/position-manager:latest",
    "memory": 512,
    "cpu": 256,
    "essential": true,
    "environment": [
      {"name": "DB_HOST", "value": "ops-pipeline-db.cluster-xxx.us-west-2.rds.amazonaws.com"},
      {"name": "DB_NAME", "value": "ops_pipeline"},
      {"name": "ALPACA_API_KEY", "value": "..."},
      {"name": "ALPACA_API_SECRET", "value": "..."},
      {"name": "ALPACA_BASE_URL", "value": "https://paper-api.alpaca.markets"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/ops-pipeline/position-manager",
        "awslogs-region": "us-west-2",
        "awslogs-stream-prefix": "ecs"
      }
    }
  }],
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "256",
  "memory": "512",
  "taskRoleArn": "arn:aws:iam::160027201036:role/ecsTaskRole",
  "executionRoleArn": "arn:aws:iam::160027201036:role/ecsTaskExecutionRole"
}
```

### EventBridge Schedule

```json
{
  "ScheduleExpression": "rate(1 minute)",
  "Target": {
    "Arn": "arn:aws:ecs:us-west-2:160027201036:cluster/ops-pipeline-cluster",
    "RoleArn": "arn:aws:iam::160027201036:role/EventBridgeECSRole",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:us-west-2:160027201036:task-definition/position-manager:1",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["subnet-xxx", "subnet-yyy"],
          "SecurityGroups": ["sg-xxx"],
          "AssignPublicIp": "DISABLED"
        }
      }
    }
  }
}
```

---

## ✅ Success Criteria

Position Manager is complete when:

1. **Positions tracked:**
   - [ ] All filled executions create active_positions records
   - [ ] Prices updated every 1 minute
   - [ ] P&L calculated accurately

2. **Exits enforced:**
   - [ ] Stop loss hits trigger immediate close
   - [ ] Take profit hits trigger immediate close
   - [ ] Day trades closed by 3:55 PM ET
   - [ ] Options closed 1 day before expiration

3. **Safety guaranteed:**
   - [ ] No position can run without monitoring
   - [ ] Failed bracket orders detected
   - [ ] Partial fills handled correctly
   - [ ] Manual close works when automated fails

4. **Monitoring working:**
   - [ ] All events logged to CloudWatch
   - [ ] Critical alerts sent to email
   - [ ] Position summary view accurate
   - [ ] Can query historical position events

---

## 📊 Metrics to Track

### Daily Metrics

- Total positions opened
- Total positions closed
- Positions closed by reason:
  - stop_loss
  - take_profit
  - day_trade_close
  - expiration_risk
  - max_hold_time
- Average hold time
- Win rate (take_profit / total)

### Health Metrics

- Position manager execution count
- Average execution duration
- Failed position close attempts
- Bracket order verification rate
- Price update success rate

---

## 🔄 Next Steps After Completion

1. **Monitor for 1 week** - Verify all exits working
2. **Add trailing stops** - Let winners run
3. **Implement profit protection** - Scale out on targets
4. **Add daily P&L reporting** - Email summary
5. **Build Phase 14** - AI learning from position data

---

**This is the safety net. Without this, all other features are built on sand.**
