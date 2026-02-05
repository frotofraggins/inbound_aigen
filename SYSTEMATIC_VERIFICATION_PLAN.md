# Systematic System Verification - No Assumptions

## 📋 Verification Checklist

### Phase 1: Infrastructure
- [ ] List all ECS services
- [ ] List all EventBridge schedulers
- [ ] List all Lambda functions
- [ ] Verify each is actually running (not just exists)

### Phase 2: Data Ingestion
- [ ] RSS: Check service code for what it actually does
- [ ] RSS: Verify it's running and when it last ran
- [ ] RSS: Check database for recent events
- [ ] Sentiment: Check classifier code
- [ ] Sentiment: Verify it processes RSS events
- [ ] Sentiment: Check classified events exist

### Phase 3: Telemetry
- [ ] Check telemetry service code
- [ ] Verify what ticker list it loads
- [ ] Check when it last ran
- [ ] Verify bars are being inserted
- [ ] Check data freshness

### Phase 4: Features
- [ ] Check feature computer code
- [ ] Verify what it computes
- [ ] Check when it last ran
- [ ] Verify features exist in database
- [ ] Check data quality

### Phase 5: Signals
- [ ] Check signal engine code
- [ ] Verify how it loads watchlist
- [ ] Check how it generates signals
- [ ] Verify signals are being created
- [ ] Check signal quality/confidence

### Phase 6: Trading
- [ ] Check dispatcher code flow
- [ ] Verify how it claims recommendations
- [ ] Check broker execution logic
- [ ] Verify database insert happens
- [ ] Check if executions are saved

### Phase 7: Position Management
- [ ] Check position manager code
- [ ] Verify sync logic
- [ ] Check exit conditions code
- [ ] Verify tracking logic
- [ ] Check if positions are monitored

### Phase 8: Learning
- [ ] Check what triggers data collection
- [ ] Verify bar fetcher code
- [ ] Check position history insert
- [ ] Verify learning table schemas
- [ ] Check if data flows correctly

---

## 🔍 Starting Systematic Check

I will go through each phase methodically, reading actual code and checking real data.
No assumptions. Only verified facts.
