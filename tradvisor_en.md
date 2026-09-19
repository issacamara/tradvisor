# Tradvisor BRVM - V1 Business Requirements Document

**Version:** 2.0

**Date:** September 18, 2026
**Status:** Review-ready V1 baseline

## 1. Purpose

Tradvisor BRVM is a decision-support product for BRVM-listed equities. V1 gives an individual investor two equally important, clearly separated workflows:

- **Swing Trading:** a daily, explainable technical recommendation for each eligible stock, with manually initiated paper trading.
- **Long-Term Investing:** explainable company scoring and objective-aware investment advice for capital growth, dividend income, or a balanced objective.

Tradvisor provides advisory analysis. It does not place orders, provide execution services, or track a user's real brokerage portfolio in V1.

## 2. Business Outcomes

### 2.1 Short-Term Outcome

After market close, the user can review every BRVM stock and understand whether the current technical evidence supports `Buy`, `Keep`, `Sell`, or `No clear signal`. The user can inspect the indicators and reasoning behind the recommendation, then manually create a simulated order from it.

### 2.2 Long-Term Outcome

The user can rank BRVM companies according to a selected investment objective:

- `Capital growth`
- `Dividend income`
- `Balanced`

For every company with sufficient information, the user can see a Growth score, a Dividend score, an overall rating, and a clear explanation of the factors behind those results.

## 3. Scope and Boundaries

| In V1 | Deferred beyond V1 |
|---|---|
| Daily technical recommendations | Real brokerage portfolio tracking |
| Technical-indicator analysis and explanations | Coris Bourse CSV or Excel imports |
| Manual paper orders and simulated performance | Real order placement or broker integration |
| Long-term rankings, scores, and advisory | Certified real P&L and cash reconciliation |
| Growth, dividend, and balanced objectives | Tax-aware return calculations |
| BigQuery-backed analytical datasets | Corporate-action adjustments and full market microstructure data |

V1 is long-only. A paper `Sell` order may close only shares already held in the paper portfolio. Short selling is outside V1.

## 4. Users and Core Journeys

The primary V1 user is a self-directed BRVM investor who wants repeatable research and a low-risk environment for evaluating a trading approach.

### 4.1 Daily Swing Journey

1. The user opens the daily Swing workspace after market close.
2. The user scans a recommendation and confidence level for each stock.
3. The user opens a stock to inspect prices, volumes, technical indicators, eligibility, and the rule-based explanation.
4. When appropriate, the user manually creates a paper Buy or Sell order from the recommendation.
5. The user follows pending orders, open simulated positions, and position-level exit alerts.

### 4.2 Long-Term Research Journey

1. The user selects `Capital growth`, `Dividend income`, or `Balanced`.
2. The user reviews the resulting company ranking and filters it by sector or analytical status.
3. The user opens a company to inspect its Growth score, Dividend score, overall rating, financial and dividend factors, and alerts.
4. The user uses this explanation to form an investment view; Tradvisor does not initiate a trade.

## 5. Shared Business Rules

- Swing Trading and Long-Term Investing are separate strategy areas. Their outputs must not be combined into a common portfolio or performance figure.
- Every result must show the market date and the relevant data freshness information.
- A stock without sufficient input data remains visible, with `Insufficient data` rather than a manufactured recommendation or score.
- Recommendations and scores are advisory, deterministic, explainable, and reproducible from the underlying data and rule version.
- Data safeguards are implemented through automated tests and calculation guards in V1; data-quality administration is not a user-facing product workflow.

## 6. Functional Requirements: Swing Trading

### 6.1 Daily Recommendation Coverage

For every BRVM stock, the daily Swing workspace must display one of the following states:

| State | Meaning |
|---|---|
| `Buy` | Current technical conditions satisfy the configured entry rule. |
| `Keep` | The evidence supports retaining an existing position, but not opening a new one. |
| `Sell` | The configured exit conditions indicate that an existing position should be closed. |
| `No clear signal` | The stock is eligible but the evidence supports neither a new entry nor an exit. |
| `Insufficient data` | The stock cannot be assessed using the current rules and available history. |

`Sell` is an advisory signal. The paper-trading interface permits a sell only when the virtual portfolio holds the stock.

Each assessable recommendation must include a confidence level and a plain-language rationale. The rationale must explain the applicable indicators, their current values, the decision rule, and why the result is not another state.

### 6.2 Technical Analysis

The user must be able to inspect a stock's technical analysis using the daily price and volume history available in `shares`.

The V1 initial indicator set is:

- closing-price changes over 1, 5, 10, and 20 sessions;
- highest closing price over the prior 20 sessions;
- average and median volume over the prior 20 sessions;
- current volume relative to the 20-session average;
- liquidity eligibility based on recent volume and traded value.

The system must display the analysis inputs, their calculation period, and the rule version. Additional technical indicators may be introduced later only as versioned rules; V1 does not require a user-authored indicator builder.

### 6.3 Initial Recommendation Rules

The initial `Buy` rule is a 20-session breakout with volume confirmation. A stock qualifies only when all of the following are true:

1. It has 20 recent sessions of usable close and volume data.
2. It meets the configured liquidity threshold based on 20-session median volume and estimated traded value.
3. Its close is above the highest close of the previous 20 sessions.
4. Its volume is at least 1.5 times the previous 20-session average volume.

The initial simulated position-management rules are:

| Rule | Initial condition |
|---|---|
| Stop loss | Close at or below 3% below simulated entry price |
| Trailing-stop activation | Close or high reaches 6% above simulated entry price |
| Trailing stop | After activation, close at or below 3% under the highest close since entry |
| Maximum holding duration | Exit on the 20th holding session |

Thresholds and rule weights must be configurable and versioned. A changed rule must not alter the recorded explanation of an earlier recommendation or paper trade.

### 6.4 Paper Trading

Paper trading is a V1 capability, not an automated execution service.

- A user initiates a simulated Buy or Sell order from a recommendation.
- Orders created after a daily recommendation are `Pending` until the next BRVM trading session's closing price is available.
- A pending order executes at that next session's close. The execution record must show that pricing convention.
- The paper portfolio is denominated in XOF and uses user-configurable starting cash.
- Each executed order applies a user-configurable percentage transaction fee.
- The system must prevent paper purchases that exceed available virtual cash and paper sales that exceed the held quantity.
- The user can reset the portfolio at any time. Resetting clears virtual cash, pending orders, simulated positions, and performance history, then restores the selected starting balance.
- The product must show virtual cash, pending orders, held positions, entry price, latest value, gross and fee-adjusted simulated P&L, and applicable exit alerts.

V1 simulated performance is illustrative. It excludes partial fills, actual execution prices, real brokerage fees, settlement behavior, and slippage.

## 7. Functional Requirements: Long-Term Investing

### 7.1 Objective-Aware Ranking

The user can set one active objective: `Capital growth`, `Dividend income`, or `Balanced`. The selected objective changes the ranking and resulting advisory while preserving visibility of all component scores.

Every eligible company must show:

- Growth score from 0 to 100;
- Dividend score from 0 to 100;
- overall rating from 0 to 100;
- an objective-specific advisory classification;
- sector, latest available price, and data freshness.

The overall score and advisory use objective-specific, versioned weighting. `Balanced` must not obscure the underlying Growth and Dividend scores.

### 7.2 Explainable Fundamental Analysis

The score detail must identify:

- the financial and dividend factors used;
- the source period and data freshness;
- each factor's contribution to the relevant score;
- the active objective and its weighting logic;
- alerts or missing information that reduce confidence;
- source financial-document links when available.

V1 uses only calculations supported by the available data:

| Factor family | Available measures |
|---|---|
| Dividend profile | Latest known annual dividend, estimated yield, regularity, and change over time |
| Growth | Revenue and net-income growth |
| Profitability | Net margin and approximate return on equity |
| Financial strength | Net debt, net debt to equity, and total equity |
| Risk context | Latest available rating and rating trend, where interpretable |
| Context | Sector and business activity |

The product must explicitly avoid presenting unavailable measures, including precise EPS, P/E, market capitalization, payout ratio, tax-adjusted yield, and actual portfolio returns, as if they were calculated.

### 7.3 Long-Term Alerts and Advisory

The Long-Term workspace must flag material conditions, including negative net income, declining revenue or net income, high net debt, reduced or absent dividends, irregular dividends, stale financial data, and rating downgrades when interpretable.

The advisory must communicate suitability for the active objective, rather than claiming a guaranteed return or issuing an execution instruction.

## 8. Data and Analytical Foundation

V1 relies on the existing BigQuery source tables:

- `brvm_companies`
- `shares`
- `dividends`
- `financials`
- `ratings`

The implementation may use BigQuery views, materialized views, derived tables, or another BigQuery-native structure. The choice must be driven by query performance, refresh needs, operational simplicity, and FinOps cost.

The logical analytical datasets required by V1 are:

| Logical dataset | Purpose |
|---|---|
| Company reference | Company name, symbol, sector, and activity context |
| Latest market price | Latest close and market-date context per stock |
| Enriched price history | Daily price and volume analysis |
| Swing indicators | Rolling price, volume, liquidity, and recommendation inputs |
| Dividend history | Annual dividends, regularity, and trend |
| Financial trends | Revenue, income, debt, equity, and derived ratios |
| Rating history | Latest rating and interpretable trend |
| Long-term fundamentals | Scoring inputs, alerts, and objective-aware rankings |
| Paper-trading ledger | Virtual portfolio, pending orders, executions, fees, and position state |

Automated tests must protect structural integrity and calculation safety, including uniqueness of stock/date records, valid date joins, non-negative and internally consistent price ranges, valid calculation denominators, and no signal or score when mandatory inputs are absent. These controls are implementation safeguards, not a V1 operational dashboard.

## 9. Non-Functional Requirements

### Explainability

- Every Swing result shows the indicator values, rule conditions, and rule version.
- Every Long-Term result shows score components, factor contributions, objective, source periods, and alerts.
- Every paper execution shows the recommended action, order creation date, execution date, execution-price convention, and applied fee.

### Reliability

- Daily outputs are generated only after the latest available market close is processed.
- Calculations are reproducible from versioned rules and source data.
- Missing or unusable input data causes an explicit unavailable state, never an implicit recommendation.

### Strategic Separation

- Swing and Long-Term areas are visually and analytically separate.
- Paper-trading performance is never combined with Long-Term scores or rankings.
- The product contains no real portfolio, broker-account, or import workflow in V1.

## 10. Acceptance Criteria

### Swing Trading

- Each BRVM stock is visible in the daily Swing workspace with an assessable recommendation or `Insufficient data`.
- Every `Buy`, `Keep`, `Sell`, and `No clear signal` outcome contains a confidence level and indicator explanation.
- The breakout and volume-confirmation calculations use the documented 20-session windows.
- A user can inspect the price and volume inputs behind a recommendation.

### Paper Trading

- A user can manually create a paper order from a recommendation.
- A new paper order remains pending until the next trading session's close and executes using that close.
- Fees, cash constraints, long-only constraints, and position values are calculated correctly.
- The user can reset the virtual portfolio at any time and begin again with the configured starting cash.

### Long-Term Investing

- The user can select Capital growth, Dividend income, or Balanced and receives a corresponding company ranking.
- Every eligible company displays Growth, Dividend, and overall scores from 0 to 100.
- Score details show the underlying factors, contribution, data period, active objective, and applicable alerts.
- Companies without required data remain visible with an explicit unavailable status.

### Scope Protection

- V1 includes no Coris file import, broker integration, real-position valuation, or real portfolio performance calculation.
- The implementation uses a BigQuery-native analytical structure appropriate to validated performance and cost characteristics.
- Automated tests cover calculation safety and data assumptions without creating a user-facing data-quality workflow.

## 11. Delivery Priorities

Both investor workflows are equal first-class MVP capabilities. Their common data foundation is enabling work, not a third user workflow.

| Priority | Deliverable |
|---|---|
| P0 | BigQuery analytical foundation, automated data and calculation tests, and rule versioning |
| P0 | Daily Swing recommendations, technical analysis, and explanations |
| P0 | Manual long-only paper trading with next-session-close execution and reset |
| P0 | Objective-aware Long-Term scores, rankings, explanations, and alerts |
| Later | Real portfolio tracking, Coris imports, broker execution, tax treatment, corporate actions, and richer market data |

## 12. Key Assumptions and Open Design Decisions

- BRVM daily market data is available frequently enough to publish recommendations after the latest close.
- XOF is the only V1 paper-portfolio currency.
- Starting cash, transaction-fee percentage, liquidity threshold, and strategy thresholds have product defaults but are configurable.
- The precise score weightings and confidence calculation are versioned product rules to be calibrated using historical and forward-looking evaluation.
- V1 has one paper portfolio per user. Multiple paper portfolios are a later enhancement.

## 13. Glossary

- **Advisory:** A decision-support output, not an order or investment guarantee.
- **Growth score:** An explainable 0-100 assessment of growth and financial-strength evidence.
- **Dividend score:** An explainable 0-100 assessment of dividend income and sustainability evidence available in V1.
- **No clear signal:** A technically eligible stock for which the rule supports neither entry nor exit.
- **Paper trading:** Simulated, manual trading without real investment or brokerage execution.
- **Pending order:** A paper order awaiting execution at the next trading session's close.
- **Swing trading:** A short-term strategy based on price and volume movements across trading sessions.
