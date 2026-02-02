# Phase 11: Ticker-Aware News Processing
## Hybrid Approach: Better Feeds + AI Inference

**Status:** PLANNING  
**Timeline:** 3-5 days implementation  
**Priority:** HIGH - Required for signal generation  
**Dependencies:** Phase 10 complete, Day 6 bugs fixed  

---

## Problem Statement

**Current State:**
- 301 classified news items
- 0 have ticker associations (0.0%)
- RSS feeds provide macro market news
- No ticker symbols in headlines/text
- Signal engine can't generate ticker-specific signals

**Examples of Missed Opportunities:**
```
"Novo Nordisk shares rise 5%" → Should map to NVO
"ASML hits record high on AI" → Should map to ASML, maybe NVDA
"Trump tariffs on Greenland" → Should map to affected sectors
```

---

## Solution: Two-Pronged Approach

### Part A: Ticker-Specific RSS Feeds (Quick Win)
**Add feeds that explicitly mention tickers**

### Part B: AI-Powered Ticker Inference (Handle Edge Cases)
**Use Bedrock/Claude to infer affected stocks from macro news**

---

## Part A: Ticker-Specific RSS Feeds

### Candidate Feed Sources

#### 1. SeekingAlpha RSS
```
https://seekingalpha.com/api/sa/combined/AAPL.xml
https://seekingalpha.com/api/sa/combined/MSFT.xml
...
```
**Pros:** Stock-specific, mentions ticker in every article  
**Cons:** Need individual feed per ticker, may have rate limits

#### 2. Benzinga RSS
```
https://www.benzinga.com/feed
```
**Pros:** Stock-focused news, often includes tickers  
**Cons:** General feed, need to filter

#### 3. Yahoo Finance RSS (Per Ticker)
```
https://finance.yahoo.com/rss/headline?s=AAPL
https://finance.yahoo.com/rss/headline?s=MSFT
...
```
**Pros:** Free, per-ticker, reliable  
**Cons:** Individual feed per ticker

#### 4. Google News RSS (Per Ticker)
```
https://news.google.com/rss/search?q=AAPL+stock
https://news.google.com/rss/search?q=MSFT+stock
...
```
**Pros:** Free, aggregates multiple sources  
**Cons:** Quality varies, need filtering

### Recommended Initial Set

**Per-Ticker Feeds (7 stocks):**
```json
[
  "https://finance.yahoo.com/rss/headline?s=AAPL",
  "https://finance.yahoo.com/rss/headline?s=MSFT",
  "https://finance.yahoo.com/rss/headline?s=GOOGL",
  "https://finance.yahoo.com/rss/headline?s=AMZN",
  "https://finance.yahoo.com/rss/headline?s=META",
  "https://finance.yahoo.com/rss/headline?s=NVDA",
  "https://finance.yahoo.com/rss/headline?s=TSLA"
]
```

**Keep existing macro feeds** for AI inference testing.

### Implementation Steps

1. Update `/ops-pipeline/rss_feeds` SSM parameter
2. Add new feeds to existing list (don't replace)
3. RSS ingest will automatically pick them up
4. Verify ticker mentions in new news items
5. No code changes needed (regex extraction will work)

**Time:** 1 hour  
**Cost:** $0

---

## Part B: AI-Powered Ticker Inference

### Architecture

```
News Text
    ↓
FinBERT Sentiment Classification (existing)
    ↓
Regex Ticker Extraction (existing)
    ↓
IF tickers found:
    → Use them
ELSE:
    → Call Bedrock for AI inference
    ↓
    Bedrock/Claude analyzes text
    ↓
    Returns: [affected tickers with confidence scores]
    ↓
Store: Direct tickers + AI-inferred tickers
```

### Bedrock Integration

**Model:** Claude 3 Haiku (fast, cheap) or Sonnet (better quality)

**Prompt Template:**
```
You are a financial analyst identifying which stocks are affected by news.

News: {title} {summary}

Available stocks: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA

For each affected stock, provide:
1. Ticker symbol
2. Impact type: direct, sector, indirect
3. Confidence: 0.0-1.0

Return JSON: [{"ticker": "NVDA", "impact": "sector", "confidence": 0.8}, ...]

Only include if confidence > 0.5. Return [] if no clear connection.
```

**Example Outputs:**
```
News: "Novo Nordisk shares rise 5% after Wegovy launch"
AI: [] (not in our universe)

News: "ASML hits record high on AI boost"
AI: [{"ticker": "NVDA", "impact": "sector", "confidence": 0.7}]

News: "Trump tariffs on imports"  
AI: [{"ticker": "AAPL", "impact": "indirect", "confidence": 0.6},
     {"ticker": "MSFT", "impact": "indirect", "confidence": 0.5}]
```

### Implementation

#### 1. Add Bedrock Client
```python
# services/classifier_worker/nlp/ai_ticker_inference.py
import boto3
import json

class TickerInferenceClient:
    def __init__(self, model_id="anthropic.claude-3-haiku-20240307-v1:0"):
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
        self.model_id = model_id
    
    def infer_tickers(self, title, summary, ticker_universe):
        """Use Claude to infer affected tickers from news text"""
        
        prompt = f"""You are a financial analyst identifying which stocks are affected by news.

News: {title} {summary or ''}

Available stocks: {', '.join(ticker_universe)}

For each affected stock, provide:
1. Ticker symbol (must be from available list)
2. Impact type: direct, sector, indirect  
3. Confidence: 0.0-1.0

Return JSON array: [{{"ticker": "NVDA", "impact": "sector", "confidence": 0.8}}]

Only include if confidence > 0.5. Return [] if no clear connection.
"""
        
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            })
        )
        
        result = json.loads(response['body'].read())
        content = result['content'][0]['text']
        
        # Parse JSON response
        try:
            inferences = json.loads(content)
            # Filter for confidence and valid tickers
            return [
                inf['ticker'] 
                for inf in inferences 
                if inf['confidence'] > 0.5 and inf['ticker'] in ticker_universe
            ]
        except:
            return []
```

#### 2. Update Classifier Main
```python
# In services/classifier_worker/main.py

from nlp.ai_ticker_inference import TickerInferenceClient

# Initialize in main()
ai_inference = TickerInferenceClient()

# In process_event()
tickers = extract_tickers(text, ticker_whitelist)

# If no tickers found via regex, try AI inference
if not tickers:
    tickers = ai_inference.infer_tickers(
        event['title'],
        event.get('summary', ''),
        ticker_whitelist
    )
```

#### 3. IAM Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel"
  ],
  "Resource": "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-haiku-*"
}
```

#### 4. Cost Estimation
**Bedrock Claude Haiku:**
- Input: ~200 tokens per news item
- Output: ~50 tokens
- Cost: ~$0.00025 per classification
- 300 news/day × $0.00025 = **$0.075/day = $2.25/month**

**Bedrock Claude Sonnet (better quality):**
- Same tokens
- Cost: ~$0.003 per classification  
- 300 news/day × $0.003 = **$0.90/day = $27/month**

**Recommendation:** Start with Haiku ($2/month), upgrade to Sonnet if quality issues.

---

## Implementation Plan

### Day 1: Research & Setup (2-3 hours)
- [ ] Research ticker-specific RSS feeds
- [ ] Test Yahoo Finance RSS for each ticker
- [ ] Verify they mention tickers explicitly
- [ ] Test Bedrock access and permissions
- [ ] Create ticker inference prompt template
- [ ] Test on sample news items

### Day 2: Add RSS Feeds (2 hours)
- [ ] Update `/ops-pipeline/rss_feeds` SSM parameter
- [ ] Add 7 Yahoo Finance ticker feeds
- [ ] Keep existing macro feeds for AI testing
- [ ] Verify RSS ingest picks up new feeds
- [ ] Monitor for ticker-mentioned news

### Day 3: Implement AI Inference (4-6 hours)
- [ ] Create `ai_ticker_inference.py` module
- [ ] Implement Bedrock client with error handling
- [ ] Add fallback logic (if Bedrock fails, continue without)
- [ ] Update IAM role with Bedrock permissions
- [ ] Add cost tracking/logging

### Day 4: Integrate & Test (4-6 hours)
- [ ] Update classifier main.py
- [ ] Rebuild classifier Docker image
- [ ] Deploy with digest-pinned image
- [ ] Test on existing 301 news items (backfill)
- [ ] Monitor ticker association rates
- [ ] Verify signal engine receives sentiment

### Day 5: Validation (2-3 hours)
- [ ] Verify recommendations start appearing
- [ ] Check dispatcher executes recommendations
- [ ] Validate end-to-end pipeline
- [ ] Monitor Bedrock costs
- [ ] Tune confidence thresholds if needed
- [ ] Document new baseline

---

## Success Criteria

✅ At least 50% of news items have ticker associations  
✅ Signal engine receives ticker-specific sentiment  
✅ BUY/SELL recommendations generated during market hours  
✅ Dispatcher executes at least one simulated trade  
✅ Bedrock costs stay under $5/month  
✅ No degradation in classification latency  

---

## Risks & Mitigation

### Risk: Bedrock API Failures
**Mitigation:** Fallback to regex-only extraction, log failures

### Risk: Incorrect Ticker Inference
**Mitigation:** Store confidence scores, filter low-confidence inferences

### Risk: Cost Overrun
**Mitigation:** Start with Haiku, monitor daily costs, circuit breaker if >$10/day

### Risk: Latency Increase
**Mitigation:** Async/batch processing, timeout after 3 seconds

---

## Cost Impact

**New Monthly Costs:**
- Bedrock Haiku: +$2.25/month
- No infrastructure changes: $0

**Updated Total:** ~$42/month (was $40)

**If upgrade to Sonnet:** ~$67/month

---

## Migration Strategy

### Phase 11.1: RSS Feeds Only (Day 2)
- Add ticker feeds
- Deploy
- Test for 1 day
- Measure improvement

**Expected:** 20-30% of news with tickers

### Phase 11.2: Add AI Inference (Day 4)
- Implement Bedrock integration
- Deploy
- Test for 1 day
- Measure combined improvement

**Expected:** 50-70% of news with tickers

### Phase 11.3: Tune & Validate (Day 5)
- Adjust confidence thresholds
- Verify signal quality
- Validate end-to-end
- Document baseline

---

## Alternative: Phase 11 Lite (RSS Only)

If you want to avoid Bedrock complexity initially:

**Just add ticker feeds, skip AI inference:**
- Faster (1-2 days)
- Cheaper ($0 additional)
- Simpler (no AI integration)
- Gets 20-30% coverage immediately

**Try this first**, then add AI if still insufficient.

---

## Files To Create

```
services/classifier_worker/nlp/ai_ticker_inference.py
  - Bedrock client wrapper
  - Ticker inference logic
  - Error handling

deploy/PHASE_11_PLAN.md (this file)
deploy/PHASE_11_RSS_FEEDS.md
  - Researched feed sources
  - Feed quality assessment

scripts/test_ticker_inference.py
  - Test Bedrock inference on sample news
  - Validate output format
```

---

## Next Steps

**Immediate:**
1. Research ticker-specific RSS feeds (Yahoo Finance, SeekingAlpha, Benzinga)
2. Test feed quality and ticker mention rates
3. Create list of 7-14 good feeds (1-2 per ticker)

**Then:**
4. Update SSM parameter with new feeds
5. Wait 24 hours to collect ticker-mentioned news
6. Verify signal engine starts receiving sentiment
7. If still insufficient, add Bedrock integration

---

## Decision Points

**After RSS Feeds Added (Day 2):**
- If ticker association rate > 30%: Proceed with observation
- If < 30%: Implement Bedrock integration

**After Bedrock Added (Day 4):**
- If ticker association rate > 50%: Success
- If 30-50%: Acceptable, tune thresholds
- If < 30%: Investigate prompt engineering

---

## Approval Required

**Proceed with Phase 11?**
- ✅ YES - Implement hybrid approach (RSS + AI)
- ⏸️ HOLD - Complete observation first, then enhance
- 📋 RSS ONLY - Skip AI, just add ticker feeds

**My Recommendation:** Start with RSS feeds NOW (breaks observation freeze but necessary), add AI inference on Day 3-4 if needed.
