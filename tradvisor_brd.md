# Tradvisor BRVM - V1 Business Requirements Document

**Status:** Draft for Review

**Version:** 1.0

**Date:** September 18, 2026

**Prepared from:** Stakeholder interview and available-data specification
**Priority scale:** Must, Should, Could, Won't for now

## 1. Executive Summary and Business Need

Tradvisor BRVM will help a self-directed BRVM investor make more consistent, explainable investment decisions from available market and fundamental data. The current need is twofold:

- make a daily short-term decision for each listed stock using transparent technical evidence; and
- identify companies suited to capital growth, dividend income, or a balanced long-term objective.

V1 delivers these as two separate, equal workflows. It also provides manual paper trading so the investor can evaluate short-term decisions without placing real orders. V1 is advisory only and does not track real brokerage holdings.

## 2. Objectives and Success Criteria

| ID | Objective | Success criterion | Measurement / acceptance method |
|---|---|---|---|
| OBJ-01 | Support a daily short-term decision for the BRVM universe. | Every listed stock has a daily recommendation or an explicit unavailable state after the latest processed market close. | Daily-output acceptance test and production monitoring. |
| OBJ-02 | Make technical recommendations understandable. | An investor can inspect the values, rules, and confidence behind each assessable recommendation. | Functional acceptance test and stakeholder review. |
| OBJ-03 | Let the investor evaluate a swing approach without capital at risk. | The investor can manually place, execute, value, and reset long-only paper trades using the agreed pricing convention. | Paper-trading scenario tests. |
| OBJ-04 | Support objective-based long-term research. | The investor can rank eligible companies for Capital growth, Dividend income, or Balanced and inspect the rationale. | Functional acceptance test and stakeholder review. |
| OBJ-05 | Preserve trust in advisory outputs. | The product marks insufficient information explicitly and does not present unavailable calculations as facts. | Negative-path and calculation-safety tests. |

No numerical adoption, return, accuracy, or delivery-date target has been confirmed. These are open items rather than implied success measures.

## 3. Stakeholders and User Groups

| Stakeholder / group | Role and interest | Decision or responsibility | Status |
|---|---|---|---|
| Self-directed BRVM investor | Primary V1 user of Swing, paper-trading, and Long-Term workflows. | Validates usability and advisory value. | Confirmed |
| Business sponsor / product owner | Owns business priorities, default rule settings, and final approval. | Approves scoring, confidence, and rollout decisions. | To be confirmed |
| BigQuery data owner | Provides and maintains source-table availability and access. | Confirms refresh timing, data semantics, and access model. | To be confirmed |
| Delivery team | Builds, tests, operates, and supports V1. | Validates implementation feasibility and operational controls. | To be confirmed |

## 4. Current State and Future State

### 4.1 Current State

The available information identifies five BigQuery source tables:

- `brvm_companies`
- `shares`
- `dividends`
- `financials`
- `ratings`

The investor does not yet have a single V1 workflow that turns these data into daily technical advice, objective-aware long-term advice, and a paper-trading record. The original specification mixed future real-portfolio tracking with the MVP and made the relative priority of Swing and Long-Term workflows unclear.

### 4.2 Future State

After the latest available market close, Tradvisor presents a dedicated Swing workspace with an explainable status for every stock. A user may manually translate an advisory into a paper order, which executes at the next trading session's close.

Separately, the Long-Term workspace ranks eligible companies according to the selected objective while exposing Growth, Dividend, and overall ratings, factor contributions, source periods, and alerts. Real holdings remain outside the workflow.

## 5. Scope

### 5.1 In Scope for V1

- Daily Swing recommendations for the BRVM equity universe.
- Technical-indicator analysis, confidence, and plain-language explanation.
- Manually initiated, long-only paper trading in XOF.
- Objective-aware Long-Term company scoring, ranking, alerts, and explanation.
- Use of existing BigQuery market, dividend, financial, rating, and company-reference data.
- Automated calculation and data-assumption tests.

### 5.2 Out of Scope for V1

- Real brokerage portfolio tracking, valuation, performance, or reconciliation.
- Coris Bourse CSV or Excel import.
- Automated order placement, broker integration, or investment execution.
- Short selling.
- Tax-aware returns, certified P&L, or full cash reconciliation.
- Corporate-action adjustment, precise EPS, P/E, market capitalization, payout ratio, and actual portfolio returns.
- A user-facing data-quality administration or monitoring workflow.

## 6. Future Business Process

### 6.1 Daily Swing Process

1. The market-data refresh makes the latest available close available for analysis.
2. Tradvisor evaluates each BRVM stock against the active, versioned Swing rules.
3. The system records one recommendation state, confidence, evidence, and market date per stock.
4. The investor reviews the universe or a stock-specific analysis.
5. The investor may manually create a paper Buy or Sell order from that recommendation.
6. The order remains pending until the next trading session's closing price is available, then executes at that close with the configured fee.
7. The investor reviews virtual cash, positions, P&L, and exit alerts or resets the paper portfolio.

### 6.2 Long-Term Research Process

1. The investor selects Capital growth, Dividend income, or Balanced.
2. Tradvisor calculates and ranks eligible company results using the active objective-specific rules.
3. The investor reviews the ranking, filters results, and opens company detail.
4. The investor evaluates the component scores, factor contributions, financial and dividend evidence, alerts, and source-document links.
5. The investor makes an independent investment decision outside Tradvisor's execution scope.

## 7. Functional Requirements

### 7.1 Swing Trading

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-SW-01 | The system shall show every BRVM stock in the daily Swing workspace with `Buy`, `Keep`, `Sell`, `No clear signal`, or `Insufficient data`. | Must | Stakeholder interview | Given the latest market data has been processed, when the user opens the Swing workspace, then each listed stock has exactly one displayed state. |
| FR-SW-02 | The system shall assign `Insufficient data` when mandatory inputs or history are unavailable. | Must | Stakeholder interview | Given a stock lacks mandatory input data, when daily evaluation runs, then no Buy, Keep, Sell, or No clear signal outcome is produced and the missing basis is shown. |
| FR-SW-03 | The system shall provide a confidence level and plain-language explanation for each assessable Swing result. | Must | Stakeholder interview | Given a stock has an assessable result, when the user opens its detail, then the result, confidence, indicators, values, conditions met or unmet, and rule version are visible. |
| FR-SW-04 | The system shall make the initial V1 technical inputs available for inspection: 1-, 5-, 10-, and 20-session price changes; 20-session high close; 20-session average and median volume; volume relative to average; and liquidity eligibility. | Must | Stakeholder interview and source specification | Given a stock has enough price and volume history, when the user opens technical analysis, then each listed input and its calculation period is displayed. |
| FR-SW-05 | The system shall apply the initial Buy rule only when the stock has 20 usable sessions, meets the configured liquidity threshold, closes above the prior 20-session high close, and has volume at least 1.5 times the prior 20-session average. | Must | Source specification, retained as V1 rule | Given all four conditions are true, when daily evaluation runs, then the result is Buy; given any condition is false, then Buy is not issued. |
| FR-SW-06 | The system shall generate exit-oriented Swing advice using configurable, versioned stop loss, trailing-stop, and maximum-duration rules. | Must | Source specification and stakeholder approval of paper-trading scope | Given an open paper position meets an active exit rule, when evaluation runs, then the position shows the relevant exit alert and advisory. |
| FR-SW-07 | The system shall retain the rule version and evidence that produced each historical Swing result. | Should | Business analyst interpretation of explainability requirement | Given a rule is changed after a result is recorded, when the historical result is viewed, then its original rule version and explanation remain available. |

### 7.2 Paper Trading

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-PT-01 | The system shall let the user manually create a paper Buy or Sell order from a Swing recommendation. | Must | Stakeholder interview | Given a visible Swing recommendation, when the user selects the paper-trade action and submits valid order details, then a corresponding pending paper order is created. |
| FR-PT-02 | The system shall execute a paper order at the next BRVM trading session's closing price. | Must | Stakeholder interview | Given a paper order is created after a daily recommendation, when the next trading-session close becomes available, then the order executes at that close and records the pricing convention. |
| FR-PT-03 | The system shall support only long-only paper trading. | Must | Stakeholder interview | Given the virtual portfolio holds no shares of a symbol, when the user attempts a paper Sell, then the system prevents the order. |
| FR-PT-04 | The system shall maintain a single XOF paper portfolio with user-configurable starting cash and a user-configurable percentage transaction fee. | Must | Stakeholder interview | Given the user updates starting cash or the fee percentage, when a new simulation is started or an order executes, then the selected values are used and shown. |
| FR-PT-05 | The system shall prevent a paper Buy that exceeds available virtual cash and a paper Sell that exceeds held quantity. | Must | Stakeholder interview | Given an order would exceed available cash or holdings, when the user submits it, then the system rejects it with a clear reason and does not change the ledger. |
| FR-PT-06 | The system shall show virtual cash, pending orders, holdings, entry price, latest value, gross P&L, fee-adjusted simulated P&L, and exit alerts. | Must | Stakeholder interview | Given the user has pending or executed paper orders, when the user opens the paper portfolio, then each listed value is available and mathematically consistent with the ledger. |
| FR-PT-07 | The system shall let the user reset the paper portfolio at any time. | Must | Stakeholder interview | Given the user confirms a reset, when reset completes, then pending orders, holdings, and performance history are cleared and virtual cash equals the selected starting balance. |

### 7.3 Long-Term Investing

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-LT-01 | The system shall let the user select Capital growth, Dividend income, or Balanced as the active Long-Term objective. | Must | Stakeholder interview | Given the Long-Term workspace is open, when the user selects an objective, then the active objective is visible and the ranking updates to that objective. |
| FR-LT-02 | The system shall display a 0-100 Growth score, a 0-100 Dividend score, and a 0-100 overall rating for each eligible company. | Must | Stakeholder interview | Given a company has sufficient required data, when it is displayed in the Long-Term workspace, then all three scores are present and within the 0-100 range. |
| FR-LT-03 | The system shall use objective-specific, versioned weighting to calculate the overall rating and advisory classification while preserving both component scores. | Must | Stakeholder interview | Given the same eligible company is evaluated under different objectives, when the objective changes, then the ranking or advisory may change while Growth and Dividend scores remain visible. |
| FR-LT-04 | The system shall explain each Long-Term result through financial and dividend factors, factor contributions, source periods, freshness, selected objective, alerts, and available financial-document links. | Must | Stakeholder interview | Given the user opens a company detail, when score information is displayed, then each stated explanation element is visible or explicitly unavailable. |
| FR-LT-05 | The system shall calculate only measures supported by the provided data, including dividend profile, revenue and net-income growth, net margin, approximate return on equity, net debt, net debt to equity, ratings, sector, and activity context. | Must | Source specification | Given required source fields are present, when Long-Term processing runs, then supported measures are calculated; unsupported measures are not shown as calculated values. |
| FR-LT-06 | The system shall flag negative income, declining revenue or income, high net debt, reduced or absent dividends, irregular dividends, stale financial data, and interpretable rating downgrades. | Should | Source specification | Given an alert condition is present, when the company is displayed, then the relevant alert is visible in the ranking and detail view. |
| FR-LT-07 | The system shall keep a company visible with an explicit unavailable status when it lacks data required for a reliable score. | Must | Stakeholder interview | Given required financial, dividend, or price inputs are missing, when the ranking is displayed, then the company is marked unavailable rather than assigned a misleading score. |

## 8. Nonfunctional Requirements

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| NFR-01 | Daily advisory output shall identify the latest market date processed and shall not claim to represent a later close. | Must | Stakeholder interview | Given the daily output is displayed, when the user inspects it, then the market date is visible and matches the data used. |
| NFR-02 | Recommendations, scores, and paper executions shall be reproducible from source data, configuration, and versioned rules. | Must | Stakeholder interview | Given the same input snapshot and rule version, when a calculation is rerun, then it returns the same outcome and evidence. |
| NFR-03 | Missing, invalid, or unsafe calculation inputs shall produce an explicit unavailable state instead of an inferred recommendation or score. | Must | Stakeholder interview | Given a mandatory input is missing or a calculation denominator is invalid, when processing runs, then the affected output is unavailable and no invalid value is presented. |
| NFR-04 | Swing and Long-Term outputs shall remain distinct in the user experience and analytical reporting. | Must | Stakeholder interview | Given the user views either workflow, when results are displayed, then paper-trading performance is not combined with Long-Term scores or rankings. |
| NFR-05 | The BigQuery analytical layer shall use a structure selected for validated query performance, refresh needs, operational simplicity, and FinOps cost. | Must | Stakeholder interview | Given the implementation design is reviewed, when the analytical structure is selected, then its performance and cost rationale is documented and approved by the appropriate owner. |
| NFR-06 | V1 shall make core decision information understandable without requiring the user to infer calculation logic. | Should | Stakeholder interview | Given a user inspects a result, when its explanation is displayed, then the values and rules necessary to understand the outcome are available in plain language. |

Performance targets, availability targets, recovery objectives, accessibility standard, authentication model, and retention periods are not yet confirmed.

## 9. Data, Reporting, Integration, Security, Privacy, and Compliance

### 9.1 Data Requirements

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| DR-01 | V1 shall use `brvm_companies`, `shares`, `dividends`, `financials`, and `ratings` as the stated analytical data sources. | Must | Source specification | Given the V1 data catalog is reviewed, when a displayed measure is traced, then its source table or documented derived dataset is identifiable. |
| DR-02 | V1 shall use a BigQuery-native analytical structure, which may be views, materialized views, derived tables, or another appropriate structure. | Must | Stakeholder interview | Given the data design is implemented, when it is reviewed, then it documents the selected structure and its performance and FinOps rationale. |
| DR-03 | Automated tests and calculation guards shall validate critical data and calculation assumptions. | Must | Stakeholder interview | Given invalid structural, price-range, date-join, or denominator inputs, when tests and processing run, then unsafe outputs are prevented. |

### 9.2 Reporting Requirements

The V1 user-facing reports are the daily Swing workspace, stock technical-analysis detail, paper-portfolio view, objective-aware Long-Term ranking, and company score detail. No separate executive report or export requirement has been confirmed.

### 9.3 Integration Requirements

No broker integration, real-order submission, Coris import, or external portfolio integration is in scope for V1. BigQuery is the confirmed data platform. Source refresh method and schedule are dependencies to be confirmed by the data owner.

### 9.4 Security, Privacy, and Compliance

V1 does not process real brokerage positions or imports. Authentication, authorization roles, personal-data handling, disclaimer wording, applicable investment-advice regulation, and audit-retention obligations are material open questions. They must be validated by the product owner and appropriate legal, security, and data owners before release.

## 10. Assumptions, Constraints, Dependencies, Risks, and Mitigations

### 10.1 Assumptions

| ID | Assumption | Validation owner | Impact if false |
|---|---|---|---|
| ASM-01 | Latest BRVM daily market data is available frequently enough to publish an after-close recommendation. | BigQuery data owner | Daily Swing outcome cannot be delivered as stated. |
| ASM-02 | XOF is the sole V1 paper-portfolio currency. | Product owner | Portfolio model and UX require expansion. |
| ASM-03 | One paper portfolio per user is sufficient for V1. | Primary user / product owner | Multiple simulations require scope expansion. |
| ASM-04 | Score weights, confidence logic, and default thresholds can be configured and versioned without changing the V1 business scope. | Product owner | Scoring and recommendation acceptance remain blocked. |

### 10.2 Constraints

- V1 is limited to the fields and history available in the confirmed BigQuery sources.
- The product is advisory only; it cannot represent a guaranteed return or execution service.
- Real portfolio and broker workflows are deliberately excluded.
- The BigQuery design must account for FinOps as well as performance.

### 10.3 Dependencies

| ID | Dependency | Owner | Status |
|---|---|---|---|
| DEP-01 | Reliable BigQuery access and documented source-table semantics. | BigQuery data owner | To be confirmed |
| DEP-02 | Timely availability of market-close data. | BigQuery data owner | To be confirmed |
| DEP-03 | Approval of default score weights, confidence logic, liquidity threshold, and paper-trading defaults. | Product owner | To be confirmed |
| DEP-04 | Security, privacy, and investment-advice compliance review. | Product owner with legal/security support | To be confirmed |

### 10.4 Risks and Mitigations

| ID | Risk | Mitigation |
|---|---|---|
| RISK-01 | Thin or incomplete market data could produce false confidence. | Display Insufficient data and confidence; apply calculation guards and automated tests. |
| RISK-02 | Users may mistake advice or paper results for investment guarantees. | Use clear advisory language and disclose simulation assumptions. |
| RISK-03 | Uncalibrated score weights or thresholds could reduce trust. | Version configurations, retain explanations, and calibrate before or during pilot evaluation. |
| RISK-04 | BigQuery query patterns could create avoidable cost or latency. | Select and validate the analytical structure against performance and FinOps criteria. |
| RISK-05 | Missing legal or privacy decisions could delay release. | Assign and complete the compliance review before rollout. |

## 11. Delivery, Rollout, Training, and Support Considerations

### 11.1 Delivery Sequence

1. Validate source semantics, refresh timing, and the BigQuery analytical design.
2. Implement automated calculation safeguards and versioned rule configuration.
3. Deliver daily Swing recommendations and technical explanation.
4. Deliver manual paper trading and scenario validation.
5. Deliver objective-aware Long-Term scores, explanations, and alerts.
6. Validate daily outputs, simulation behavior, and stakeholder usability before broader rollout.

The two investor workflows are equal first-class V1 outcomes; this sequence describes dependencies, not a reduction in priority.

### 11.2 Rollout and Training

The investor needs concise in-product explanations of the advisory nature of recommendations, the next-session-close paper-execution convention, fees, reset behavior, and score inputs. Formal training, support channels, release date, pilot group, and change-management approach are to be confirmed by the product owner.

## 12. Open Questions

| ID | Question | Why it matters | Owner |
|---|---|---|---|
| OQ-01 | What numerical targets define successful V1 adoption, usage, advisory quality, and delivery timing? | Success cannot be measured beyond functional acceptance without targets. | Product owner |
| OQ-02 | What are the approved default values for starting cash, transaction fee, liquidity threshold, stop/trailing rules, score weights, and confidence logic? | Defaults affect user outcomes and test cases. | Product owner |
| OQ-03 | What is the data-refresh schedule, data-delay expectation, and authoritative market-close definition? | Daily recommendation timing and status depend on it. | BigQuery data owner |
| OQ-04 | Who may access the product, and what authentication and authorization model is required? | Determines security and privacy design. | Product owner / security owner |
| OQ-05 | What legal, regulatory, disclaimer, and record-retention requirements apply to BRVM investment-advisory content? | Determines release readiness and user communication. | Product owner / legal owner |
| OQ-06 | What accessibility, availability, performance, support, and retention thresholds are required? | Needed for measurable nonfunctional acceptance. | Product owner |

## 13. Traceability

| Objective | Primary requirements | Success measure / acceptance method |
|---|---|---|
| OBJ-01 | FR-SW-01, FR-SW-02, FR-SW-05, NFR-01 | Daily-output acceptance test |
| OBJ-02 | FR-SW-03, FR-SW-04, FR-SW-07, NFR-06 | Functional acceptance and stakeholder review |
| OBJ-03 | FR-PT-01 through FR-PT-07, NFR-02 | Paper-trading scenario tests |
| OBJ-04 | FR-LT-01 through FR-LT-07 | Functional acceptance and stakeholder review |
| OBJ-05 | FR-SW-02, FR-LT-07, DR-03, NFR-03 | Negative-path and calculation-safety tests |

## 14. Approval

| Approval role | Name | Decision | Date | Notes |
|---|---|---|---|---|
| Business sponsor / product owner | To be confirmed | Pending | To be confirmed | Approves scope, requirements, and defaults. |
| Primary user representative | To be confirmed | Pending | To be confirmed | Validates workflow usefulness and language. |
| Data owner | To be confirmed | Pending | To be confirmed | Confirms source-data access, semantics, and refresh dependency. |
| Security / legal reviewer | To be confirmed | Pending | To be confirmed | Confirms applicable release requirements. |

## 15. Next Steps

| Owner | Action |
|---|---|
| Product owner | Review this draft, approve scope, choose measurable success targets, and set V1 rule defaults. |
| BigQuery data owner | Confirm source-table semantics, refresh timing, access, and data-platform constraints. |
| Security / legal owner | Confirm applicable authentication, privacy, disclaimer, and investment-advice obligations. |
| Delivery team | Produce architecture and implementation backlog only after the above decisions are recorded or accepted as explicit assumptions. |

This document is a Draft for Review until the approval section is completed.
