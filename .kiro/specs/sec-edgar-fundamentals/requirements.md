# Requirements Document

## Introduction

The algorithmic options trading system currently generates signals based on technical indicators (SMA, trend, volume) and news sentiment, but lacks any fundamental financial data. This feature adds a fundamentals data pipeline that ingests structured financial data from the SEC's free EDGAR XBRL API, normalizes it, stores it in the existing PostgreSQL database, computes fundamental features (revenue growth, profit margins, leverage, cash flow strength), and integrates those features into the existing signal engine to improve signal quality and risk management. Additionally, the pipeline monitors SEC filings (10-K, 10-Q, 8-K) to detect material events and earnings releases, feeding that information into the signal engine for confidence adjustments and the EOD strategy's earnings calendar.

## Glossary

- **SEC_EDGAR_Client**: A Python module that calls the SEC EDGAR API endpoints (Submissions, Company Facts, Company Concept, Frames) with proper User-Agent headers, rate limiting, caching, and error handling.
- **CIK**: Central Index Key — the SEC's unique numeric identifier for each company filing entity. Always zero-padded to 10 digits when used in API URLs.
- **XBRL**: eXtensible Business Reporting Language — the structured data format used by the SEC for financial filings. Each financial fact is tagged with a taxonomy (e.g., `us-gaap`) and a concept tag (e.g., `Revenues`, `NetIncomeLoss`).
- **Taxonomy**: The classification system for XBRL concepts. The primary taxonomy is `us-gaap`; some companies use `ifrs-full` or custom extensions.
- **Company_Facts**: The complete set of structured financial facts for a single company, returned by the SEC Company Facts API endpoint.
- **Fundamentals_Ingestion_Task**: An ECS scheduled task that pulls Company Facts for all monitored tickers, normalizes the XBRL data, and stores it in the `financial_fundamentals` table.
- **Feature_Computer**: The component that computes derived fundamental features (revenue growth, profit margin, leverage ratio, cash flow strength, asset turnover) from raw financial data in `financial_fundamentals`.
- **Signal_Engine_Integration**: The component within the signal engine that reads fundamental features and applies confidence adjustment rules based on fundamental health indicators.
- **Filing_Monitor_Task**: An ECS scheduled task that checks the SEC Submissions API for new filings (10-K, 10-Q, 8-K) across all monitored tickers and records them in the `sec_filings` table.
- **SSM_Config**: JSON configuration stored in AWS SSM Parameter Store at `/ops-pipeline/sec_edgar_config`, containing refresh intervals, monitored metrics, confidence boost rules, and the required User-Agent string.
- **Monitored_Tickers**: The set of 39 tickers stored in SSM at `/ops-pipeline/tickers` that the system actively tracks for trading signals.
- **Period_Type**: The reporting period classification for a financial metric — one of `quarterly` (10-Q, 3-month period), `annual` (10-K, 12-month period), or `ytd` (year-to-date cumulative).

## Requirements

### Requirement 1: Ticker-to-CIK Mapping

**User Story:** As a system operator, I want the system to map the 39 monitored tickers to their SEC CIK numbers, so that the pipeline can query the correct EDGAR API endpoints for each company.

#### Acceptance Criteria

1. WHEN the Fundamentals_Ingestion_Task starts, THE SEC_EDGAR_Client SHALL load the SEC's published ticker-to-CIK reference file and resolve CIK numbers for all Monitored_Tickers.
2. THE SEC_EDGAR_Client SHALL store resolved mappings in the `sec_cik_mapping` table with fields: ticker, cik (zero-padded 10-digit string), company_name, and last_updated timestamp.
3. WHEN a ticker cannot be resolved to a CIK, THE SEC_EDGAR_Client SHALL log a warning with the unresolved ticker and skip that ticker for the current ingestion cycle.
4. WHEN the `sec_cik_mapping` table already contains a mapping for a ticker, THE SEC_EDGAR_Client SHALL update the `last_updated` timestamp and `company_name` if changed, preserving the existing CIK.
5. THE SEC_EDGAR_Client SHALL refresh the ticker-to-CIK mapping at most once per day.

### Requirement 2: SEC EDGAR API Client

**User Story:** As a developer, I want a reusable Python client for the SEC EDGAR API, so that all pipeline components can query SEC data with proper rate limiting, caching, and error handling.

#### Acceptance Criteria

1. THE SEC_EDGAR_Client SHALL include a configurable User-Agent header on every HTTP request, loaded from SSM_Config field `user_agent_string`.
2. THE SEC_EDGAR_Client SHALL enforce a maximum request rate of 10 requests per second across all concurrent calls to SEC EDGAR endpoints.
3. WHEN the SEC EDGAR API returns an HTTP 429 (Too Many Requests) response, THE SEC_EDGAR_Client SHALL wait for the duration specified in the Retry-After header (or 10 seconds if absent) before retrying the request.
4. WHEN the SEC EDGAR API returns an HTTP 5xx server error, THE SEC_EDGAR_Client SHALL retry the request up to 3 times with exponential backoff (1s, 2s, 4s base delays).
5. THE SEC_EDGAR_Client SHALL cache API responses in memory with a configurable TTL (default 1 hour for Company Facts, 5 minutes for Submissions).
6. WHEN a cached response exists and has not expired, THE SEC_EDGAR_Client SHALL return the cached response without making an HTTP request.
7. THE SEC_EDGAR_Client SHALL support four endpoint methods: `get_submissions(cik)`, `get_company_facts(cik)`, `get_company_concept(cik, taxonomy, tag)`, and `get_frames(taxonomy, tag, unit, period)`.
8. WHEN the SEC EDGAR API returns an HTTP 404 response, THE SEC_EDGAR_Client SHALL return None and log a warning rather than raising an exception.

### Requirement 3: Financial Data Ingestion

**User Story:** As a system operator, I want the system to periodically pull structured financial data from SEC EDGAR for all monitored tickers, so that fundamental data is available for feature computation.

#### Acceptance Criteria

1. THE Fundamentals_Ingestion_Task SHALL run as a scheduled ECS task triggered by EventBridge at a configurable interval (default: every 6 hours).
2. WHEN the Fundamentals_Ingestion_Task runs, THE task SHALL call `get_company_facts(cik)` for each ticker in the `sec_cik_mapping` table and extract financial facts for the configured `monitored_metrics` list from SSM_Config.
3. THE Fundamentals_Ingestion_Task SHALL normalize each XBRL fact into a row in the `financial_fundamentals` table with fields: ticker, cik, report_date, metric_name, metric_value, period_type, filing_date, taxonomy, and created_at.
4. WHEN a financial fact already exists in `financial_fundamentals` with the same (ticker, metric_name, report_date, period_type) combination, THE Fundamentals_Ingestion_Task SHALL update the metric_value and filing_date if the new filing_date is more recent, and skip the record otherwise.
5. THE Fundamentals_Ingestion_Task SHALL log a summary at completion containing: total tickers processed, total facts inserted, total facts updated, total facts skipped, and total errors.
6. IF the SEC EDGAR API is unreachable for a ticker, THEN THE Fundamentals_Ingestion_Task SHALL log the error, skip that ticker, and continue processing remaining tickers.

### Requirement 4: Data Normalization and GAAP Concept Mapping

**User Story:** As a developer, I want XBRL financial data normalized into consistent metric names, so that feature computation can rely on a stable schema regardless of how individual companies tag their filings.

#### Acceptance Criteria

1. THE Fundamentals_Ingestion_Task SHALL maintain a GAAP concept mapping that translates common XBRL tag variants to canonical metric names (e.g., `us-gaap:Revenues`, `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, and `us-gaap:SalesRevenueNet` all map to `revenue`).
2. THE GAAP concept mapping SHALL cover at minimum these canonical metrics: `revenue`, `net_income`, `total_assets`, `total_liabilities`, `stockholders_equity`, `operating_cash_flow`, `total_debt`, `earnings_per_share`, `operating_income`.
3. WHEN an XBRL tag is not found in the GAAP concept mapping, THE Fundamentals_Ingestion_Task SHALL store the fact using the original XBRL tag as the metric_name prefixed with `raw:` (e.g., `raw:us-gaap:SomeObscureTag`).
4. THE GAAP concept mapping SHALL be defined as a Python dictionary in the codebase, not in SSM, to ensure version control and code review for mapping changes.
5. WHEN multiple XBRL tags for the same canonical metric exist in a single filing period, THE Fundamentals_Ingestion_Task SHALL prefer the tag with the highest priority in the mapping (first match wins).

### Requirement 5: Fundamental Feature Computation

**User Story:** As a trader, I want the system to compute derived fundamental features from raw financial data, so that the signal engine can use fundamental health indicators for confidence adjustments.

#### Acceptance Criteria

1. THE Feature_Computer SHALL compute the following features for each ticker with sufficient data: `revenue_growth_yoy` (year-over-year revenue change percentage), `revenue_growth_qoq` (quarter-over-quarter revenue change percentage), `profit_margin` (net_income / revenue as percentage), `leverage_ratio` (total_debt / stockholders_equity), `operating_cash_flow_trend` (sign of change in operating_cash_flow over last 2 quarters), `asset_turnover` (revenue / total_assets).
2. WHEN a required input metric is missing for a feature computation, THE Feature_Computer SHALL skip that feature for the ticker and log a warning.
3. THE Feature_Computer SHALL store computed features in the `fundamental_features` table with fields: ticker, computed_at, feature_name, feature_value.
4. THE Feature_Computer SHALL run after each Fundamentals_Ingestion_Task completes, computing features from the latest available data.
5. WHEN computing growth rates (YoY, QoQ), THE Feature_Computer SHALL use the two most recent periods of the appropriate type from `financial_fundamentals` and compute the percentage change as `(current - prior) / abs(prior) * 100`.
6. WHEN the prior period value for a growth rate computation is zero, THE Feature_Computer SHALL set the feature value to null and log a warning.

### Requirement 6: Signal Engine Integration

**User Story:** As a trader, I want fundamental features to influence signal confidence, so that signals aligned with strong fundamentals get boosted and signals conflicting with weak fundamentals get reduced.

#### Acceptance Criteria

1. WHEN the Signal_Engine generates a signal for a ticker, THE Signal_Engine_Integration SHALL query the latest fundamental features for that ticker from the `fundamental_features` table.
2. THE Signal_Engine_Integration SHALL apply configurable confidence adjustment rules from SSM_Config field `confidence_boost_rules`, where each rule specifies a condition on fundamental features and a confidence multiplier.
3. WHEN a ticker has `revenue_growth_yoy` greater than 10% AND the signal direction is bullish (BUY_CALL or BUY_STOCK), THE Signal_Engine_Integration SHALL multiply the signal confidence by a configurable `revenue_growth_boost` multiplier (default 1.10).
4. WHEN a ticker has negative `operating_cash_flow_trend` for 2 consecutive quarters, THE Signal_Engine_Integration SHALL multiply the signal confidence by a configurable `negative_cashflow_penalty` multiplier (default 0.85).
5. WHEN a ticker has both declining `revenue_growth_yoy` (negative) AND declining `profit_margin` (quarter-over-quarter decrease), THE Signal_Engine_Integration SHALL add a `risk_off` flag to the signal metadata.
6. WHEN fundamental features are unavailable for a ticker (no data in `fundamental_features`), THE Signal_Engine_Integration SHALL apply no adjustment and log an info message.
7. THE Signal_Engine_Integration SHALL log each confidence adjustment applied, including the rule name, the observed feature values, and the resulting confidence multiplier.

### Requirement 7: SEC Filing Monitor and Event Detection

**User Story:** As a trader, I want the system to detect new SEC filings (10-K, 10-Q, 8-K) for monitored tickers, so that the system can trigger fundamentals refreshes and flag material events for the signal engine.

#### Acceptance Criteria

1. THE Filing_Monitor_Task SHALL run as a scheduled ECS task triggered by EventBridge at a configurable interval (default: every 1 hour during market hours, every 6 hours outside market hours).
2. WHEN the Filing_Monitor_Task runs, THE task SHALL call `get_submissions(cik)` for each ticker in the `sec_cik_mapping` table and check for filings newer than the most recent `filing_date` in the `sec_filings` table for that ticker.
3. WHEN a new filing is detected, THE Filing_Monitor_Task SHALL insert a record into the `sec_filings` table with fields: ticker, cik, form_type, accession_number, filing_date, primary_doc_url, and processed (default false).
4. WHEN a new 10-K or 10-Q filing is detected, THE Filing_Monitor_Task SHALL set a flag to trigger an immediate fundamentals refresh for that ticker on the next Fundamentals_Ingestion_Task run.
5. WHEN a new 8-K filing is detected, THE Filing_Monitor_Task SHALL insert a record with `form_type` equal to `8-K` and set the `processed` field to false, flagging it for the signal engine to consume as a material event.
6. THE Filing_Monitor_Task SHALL log a summary at completion containing: total tickers checked, new filings found (by form type), and any errors encountered.
7. IF the SEC EDGAR API is unreachable for a ticker during filing monitoring, THEN THE Filing_Monitor_Task SHALL log the error, skip that ticker, and continue processing remaining tickers.

### Requirement 8: Database Schema

**User Story:** As a developer, I want well-defined database tables for SEC data, so that all pipeline components have a consistent storage layer.

#### Acceptance Criteria

1. THE database migration SHALL create a `sec_cik_mapping` table with columns: `ticker` (VARCHAR, primary key), `cik` (VARCHAR(10), not null), `company_name` (VARCHAR), `last_updated` (TIMESTAMP WITH TIME ZONE, not null).
2. THE database migration SHALL create a `financial_fundamentals` table with columns: `id` (SERIAL, primary key), `ticker` (VARCHAR, not null), `cik` (VARCHAR(10), not null), `report_date` (DATE, not null), `metric_name` (VARCHAR, not null), `metric_value` (NUMERIC), `period_type` (VARCHAR, not null), `filing_date` (DATE), `taxonomy` (VARCHAR, default 'us-gaap'), `created_at` (TIMESTAMP WITH TIME ZONE, default now()).
3. THE database migration SHALL create a unique constraint on `financial_fundamentals` for the combination (ticker, metric_name, report_date, period_type) to enforce upsert semantics.
4. THE database migration SHALL create a `fundamental_features` table with columns: `id` (SERIAL, primary key), `ticker` (VARCHAR, not null), `computed_at` (TIMESTAMP WITH TIME ZONE, not null), `feature_name` (VARCHAR, not null), `feature_value` (NUMERIC).
5. THE database migration SHALL create a `sec_filings` table with columns: `id` (SERIAL, primary key), `ticker` (VARCHAR, not null), `cik` (VARCHAR(10), not null), `form_type` (VARCHAR, not null), `accession_number` (VARCHAR, not null, unique), `filing_date` (DATE, not null), `primary_doc_url` (VARCHAR), `processed` (BOOLEAN, default false), `created_at` (TIMESTAMP WITH TIME ZONE, default now()).
6. THE database migration SHALL create indexes on: `financial_fundamentals(ticker, metric_name)`, `financial_fundamentals(ticker, report_date)`, `fundamental_features(ticker, feature_name)`, `sec_filings(ticker, form_type)`, and `sec_filings(filing_date)`.

### Requirement 9: SSM Configuration

**User Story:** As a system operator, I want all SEC EDGAR pipeline configuration stored in SSM Parameter Store as JSON, so that I can tune refresh intervals, monitored metrics, and confidence rules without code deploys.

#### Acceptance Criteria

1. THE Fundamentals_Ingestion_Task SHALL load configuration from SSM parameter `/ops-pipeline/sec_edgar_config` as a JSON object.
2. THE SSM_Config SHALL contain at minimum: `user_agent_string` (string, required), `refresh_interval_hours` (integer, default 6), `monitored_metrics` (list of canonical metric names, default: ["revenue", "net_income", "total_assets", "total_liabilities", "stockholders_equity", "operating_cash_flow", "total_debt", "earnings_per_share", "operating_income"]), `confidence_boost_rules` (object with rule definitions), `filing_check_interval_hours_market` (integer, default 1), `filing_check_interval_hours_off` (integer, default 6).
3. WHEN the SSM parameter is missing or contains invalid JSON, THE Fundamentals_Ingestion_Task SHALL log an error and use default values for all configuration fields except `user_agent_string`.
4. IF the `user_agent_string` is missing from SSM_Config, THEN THE SEC_EDGAR_Client SHALL refuse to make any API requests and log a critical error, because the SEC requires a User-Agent header.
5. FOR ALL valid SSM_Config JSON objects, parsing then serializing back to JSON SHALL produce an equivalent configuration (round-trip property).
