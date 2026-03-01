# Implementation Plan: SEC EDGAR Fundamentals Pipeline

## Overview

Build a fundamentals data pipeline that ingests SEC EDGAR XBRL data, normalizes it, computes fundamental features, and integrates them into the signal engine. Implementation follows the existing ECS task patterns (config loading from SSM, structured JSON logging, PostgreSQL via direct connection).

## Tasks

- [ ] 1. Database migration for SEC EDGAR tables
  - [ ] 1.1 Create migration file `db/migrations/1038_sec_edgar_tables.sql`
    - Create `sec_cik_mapping` table (ticker PK, cik, company_name, last_updated)
    - Create `financial_fundamentals` table with unique constraint on (ticker, metric_name, report_date, period_type)
    - Create `fundamental_features` table (ticker, computed_at, feature_name, feature_value)
    - Create `sec_filings` table with unique constraint on accession_number
    - Create all indexes per design: (ticker, metric_name), (ticker, report_date), (ticker, feature_name), (ticker, form_type), (filing_date)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [ ] 2. SEC EDGAR shared module
  - [ ] 2.1 Create `services/sec_edgar/` package with `__init__.py`, `client.py`, `gaap_mapping.py`, `config.py`, `features.py`
    - Implement `RateLimiter` class (token bucket, 10 req/sec)
    - Implement `SECEdgarClient` with `get_submissions`, `get_company_facts`, `get_company_concept`, `get_frames`, `load_ticker_cik_map`
    - Implement in-memory cache with configurable TTL (1h for facts, 5m for submissions)
    - Implement retry logic: 429 with Retry-After, 5xx with exponential backoff (3 retries)
    - Return None on 404, log warning
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 2.2 Write property tests for SEC EDGAR client
    - **Property 2: Cache hit returns data without HTTP request**
    - **Property 3: Rate limiter enforces 10 requests per second**
    - **Validates: Requirements 2.2, 2.5, 2.6**

  - [ ] 2.3 Implement GAAP concept mapping in `gaap_mapping.py`
    - Define `GAAP_CONCEPT_MAP` dict with all 9 canonical metrics and their XBRL tag variants
    - Build reverse lookup `TAG_TO_CANONICAL`
    - Implement `normalize_metric_name(xbrl_tag, taxonomy)` — returns canonical name or `raw:` prefixed tag
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 2.4 Write property tests for GAAP concept normalization
    - **Property 4: GAAP concept normalization maps known tags and prefixes unknown tags**
    - **Validates: Requirements 4.1, 4.3, 4.5**

  - [ ] 2.5 Implement SSM config loader in `config.py`
    - Implement `load_sec_edgar_config(base_config)` — loads from `/ops-pipeline/sec_edgar_config`
    - Implement `serialize_sec_edgar_config(config)` and `deserialize_sec_edgar_config(raw)`
    - Default values for all fields except `user_agent_string`
    - Handle missing SSM param, invalid JSON gracefully
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 2.6 Write property test for SSM config round-trip
    - **Property 11: SSM config round-trip**
    - **Validates: Requirements 9.5**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Fundamentals ingestion task
  - [ ] 4.1 Create `services/sec_edgar_ingest/` with `main.py`, `Dockerfile`, `requirements.txt`
    - Implement ticker-to-CIK resolution using `client.load_ticker_cik_map()` and upsert into `sec_cik_mapping`
    - Implement XBRL fact extraction from Company Facts response, filtering by monitored_metrics
    - Implement normalization using `gaap_mapping.normalize_metric_name`
    - Implement upsert into `financial_fundamentals` (update only when filing_date is newer)
    - Follow existing ECS task pattern: `load_config()`, structured JSON logging, `sys.exit(1)` on critical error
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 4.2 Write property tests for ticker-to-CIK resolution and upsert
    - **Property 1: Ticker-to-CIK resolution produces valid zero-padded CIKs**
    - **Property 12: CIK mapping upsert preserves existing CIK**
    - **Validates: Requirements 1.1, 1.2, 1.4**

  - [ ]* 4.3 Write property tests for XBRL fact extraction and upsert
    - **Property 5: XBRL fact extraction filters by monitored metrics**
    - **Property 6: Financial fundamentals upsert only updates when filing date is newer**
    - **Validates: Requirements 3.2, 3.3, 3.4**

- [ ] 5. Fundamental feature computation
  - [ ] 5.1 Implement feature computation in `services/sec_edgar/features.py`
    - Implement `compute_growth_rate(conn, ticker, metric, period_type, periods_back)` — returns percentage change or None
    - Implement `compute_ratio(conn, ticker, numerator, denominator, period_type)` — returns ratio or None
    - Implement `compute_trend_sign(conn, ticker, metric, period_type, periods_back)` — returns +1, -1, 0, or None
    - Implement `compute_fundamental_features(conn, ticker)` — orchestrates all 6 features
    - Implement `compute_all_features(conn, tickers)` — batch computation with DB writes to `fundamental_features`
    - Handle division by zero (return None), missing data (skip feature, log warning)
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6_

  - [ ]* 5.2 Write property tests for feature computation
    - **Property 7: Growth rate formula correctness**
    - **Property 8: Feature computation produces all features when data is complete**
    - **Validates: Requirements 5.1, 5.5, 5.6**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Signal engine integration
  - [ ] 7.1 Create `services/signal_engine_1m/fundamentals.py`
    - Implement `get_fundamental_adjustments(conn, ticker, signal_direction, config)` — returns multiplier, risk_off flag, adjustments list, features_snapshot
    - Revenue growth boost: revenue_growth_yoy > 10% + bullish → multiply by revenue_growth_boost (default 1.10)
    - Negative cash flow penalty: operating_cash_flow_trend < 0 → multiply by negative_cashflow_penalty (default 0.85)
    - Risk-off flag: declining revenue_growth_yoy + declining revenue_growth_qoq → set risk_off=True
    - No data → multiplier=1.0, risk_off=False
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ] 7.2 Integrate fundamentals into `services/signal_engine_1m/main.py`
    - After `compute_signal()`, call `get_fundamental_adjustments()` for the ticker
    - Multiply signal confidence by the returned multiplier
    - Add risk_off flag to signal metadata/reason dict
    - Include fundamentals_snapshot in the features_snapshot_json for the learning pipeline
    - _Requirements: 6.1, 6.2_

  - [ ]* 7.3 Write property tests for confidence adjustment rules
    - **Property 9: Confidence adjustment rules apply correct multipliers**
    - **Validates: Requirements 6.3, 6.4, 6.5, 6.6**

- [ ] 8. Filing monitor task
  - [ ] 8.1 Create `services/sec_edgar_filing_monitor/` with `main.py`, `Dockerfile`, `requirements.txt`
    - Implement `extract_new_filings(submissions, ticker, cik, latest_filing_date)` — returns list of new filing dicts
    - Implement filing insertion into `sec_filings` table
    - Detect 10-K/10-Q → flag for fundamentals refresh
    - Detect 8-K → store with processed=false for signal engine consumption
    - Follow existing ECS task pattern with structured JSON logging
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 8.2 Write property tests for filing detection
    - **Property 10: New filing detection finds only filings newer than the latest stored**
    - **Validates: Requirements 7.2, 7.3**

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. ECS task definitions and deployment config
  - [ ] 10.1 Create ECS task definition for fundamentals ingestion task
    - Create `deploy/sec-edgar-ingest-task-definition.json` following existing pattern (e.g., `deploy/vix-monitor-task-definition.json`)
    - Configure ECR image: `160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/sec-edgar-ingest:latest`
    - Set environment variables: AWS_REGION, RUN_MODE=ONCE
    - _Requirements: 3.1_

  - [ ] 10.2 Create ECS task definition for filing monitor task
    - Create `deploy/sec-edgar-filing-monitor-task-definition.json`
    - Configure ECR image: `160027201036.dkr.ecr.us-west-2.amazonaws.com/ops-pipeline/sec-edgar-filing-monitor:latest`
    - Set environment variables: AWS_REGION, RUN_MODE=ONCE
    - _Requirements: 7.1_

- [ ] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The shared `services/sec_edgar/` module is used by both the ingestion task and filing monitor task
- Database writes use direct PostgreSQL connection from ECS tasks (same pattern as existing services)
- All config is loaded from SSM `/ops-pipeline/sec_edgar_config` as JSON
