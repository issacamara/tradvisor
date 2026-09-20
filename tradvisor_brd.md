# Tradvisor BRVM - V1 Business Requirements Document

**Status:** Draft for Review

**Version:** 1.23

**Date:** September 20, 2026

**Prepared from:** Stakeholder interview and available-data specification
**Priority scale:** Must, Should, Could, Won't for now

**Confirmed amendment:** The stakeholder approved the missing-close grace period, fee policy, weighted-average cost method, and position-level exit references in section 6.3. This amendment does not constitute approval of the remaining open scoring or operating decisions.

**Indicator-scope amendment:** V1 focuses on EMA, RSI, ATR, and traded value. Scored trend confirmation and the revised scoring baseline in section 6.4 are approved for paper-trading evaluation, not validated investment effectiveness. Initialization, session handling and factual evidence-status semantics are adopted in section 6.6 and the financial calculation contract. Later app versions may replace the strategy; other technical indicator families are deferred.

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
| OBJ-04 | Support objective-based long-term research. | The investor can rank eligible companies for Capital growth and inspect supported Dividend income facts; Dividend and Balanced scoring are deferred beyond V1. | Functional acceptance test and stakeholder review. |
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

After the latest available market close, Tradvisor presents a dedicated Swing workspace with an explainable status for every stock. A user may manually translate an advisory into a paper order, priced at the next trading session's close subject to the missing-price and affordability rules in section 6.3.

Separately, the Long-Term workspace ranks eligible companies for Capital growth, exposing Growth ratings, factor contributions, source periods and alerts. Dividend income research exposes supported payments and conditional historical yield; full Dividend and Balanced scores are deferred beyond V1. Real holdings remain outside the workflow.

## 5. Scope

### 5.1 In Scope for V1

- Daily Swing recommendations for the BRVM equity universe.
- EMA, RSI, ATR, and traded-value analysis, confidence, and plain-language explanation.
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
- Additional technical indicator families such as standalone SMA analysis, Bollinger Bands, and MACD; these may be considered after V1. Raw OHLC/volume inputs and the already approved position-exit references remain in scope.

## 6. Future Business Process

### 6.1 Daily Swing Process

1. The market-data refresh makes the latest available close available for analysis.
2. Tradvisor evaluates each BRVM stock against the active, versioned Swing rules.
3. The system records one recommendation state, confidence, evidence, and market date per stock.
4. The investor reviews the universe or a stock-specific analysis.
5. The investor may manually create a paper Buy or Sell order from that recommendation.
6. The order targets the next trading session's closing price and the fee rate frozen at submission. It executes when that price is available within the agreed grace period and resources remain sufficient; otherwise it expires or is rejected under section 6.3, releasing its reservations.
7. The investor reviews virtual cash, positions, P&L, and exit alerts or resets the paper portfolio.

### 6.2 Long-Term Research Process

1. The investor selects Capital growth or Dividend income research. Balanced scoring is deferred beyond V1.
2. Tradvisor ranks eligible Capital growth results; Dividend income presents supported payment facts and conditional historical yield without a composite score or suitability ranking.
3. The investor reviews the ranking, filters results, and opens company detail.
4. The investor evaluates the component scores, factor contributions, financial and dividend evidence, alerts, and source-document links.
5. The investor makes an independent investment decision outside Tradvisor's execution scope.

### 6.3 Confirmed Paper-Trading Conventions

These are V1 simulation conventions, not claims about real brokerage execution, tax accounting, or actual BRVM fee schedules.

**Manual Sell override (approved 2026-09-20):** Users may manually sell held shares from either Sell or Keep advice. For Keep, display the current advice and require explicit acknowledgment that the sale overrides it; record the advice and override with the accepted order. This does not change the recommendation or authorize an automatic trade. Ownership, available held quantity, reservations, fees and next-session-close execution rules remain unchanged. This approval does not extend to missing or stale advice.

**Recommendation freshness (approved 2026-09-20):** New paper orders require current advice evaluated for the most recently completed authoritative exchange session at acceptance. The latest published batch alone is insufficient if it is outdated. A Buy requires Buy-eligible advice; a Sell requires current personalized Sell advice or Keep advice with explicit override acknowledgment. Reject stale references and require refreshed advice and renewed user confirmation. During a data delay, dated results remain readable but outdated advice cannot authorize new orders. Already accepted orders retain their original execution and expiry rules; later publication or signal changes do not cancel them.

**Starting cash (approved 2026-09-20):** Default to 1,000,000 XOF. At initial setup or reset, the user may select a whole-XOF amount from 100,000 to 100,000,000 inclusive. Reject fractional and out-of-range inputs without changing simulation state. Starting cash is fixed for that simulation generation; changing it requires a confirmed reset. No cash top-ups or direct balance edits are supported during an active simulation. These limits constrain initial funding, not subsequent balances resulting from trading. The default and limits are simulation settings, not recommended investment amounts.

**Missing closing price:** Bind the order to the next trading session after acceptance. If that session's price is delayed, retain the pending order and its reservations for one additional trading session. If the original intended-session close becomes available within that window, use that price and record the processing delay. Otherwise expire the order, release its resources, and display the reason. Never substitute a later session's close or revive an expired order when data arrives afterward.

**Fees and affordability:** Require explicit selection of a nonnegative percentage simulation fee at setup; zero is permitted but not silently assumed. Apply it to executed trade value on both buys and sells. Freeze the rate at submission, so preference changes affect only later orders. Use exact decimal arithmetic and round the final fee once to the nearest whole XOF, with halves rounded upward. Reserve resources at submission and recheck affordability at the actual close, including fees and other orders' reservations. Reject the entire order if insufficient resources remain; do not partially fill it. Rejected or expired orders incur no execution fee.

**Position accounting:** Use weighted-average purchase cost per stock, retaining gross purchase cost and purchase fees separately. Additional buys update the average. Partial sells remove proportional gross purchase cost and associated purchase fees from the remaining position. Gross realized P&L excludes fees; net realized P&L subtracts allocated purchase fees and the sell fee. Unrealized net P&L includes purchase fees already incurred, but does not deduct a hypothetical future sell fee. This is simulation accounting, not a tax-lot election.

**Holding period and exit references:** A holding period begins when a position is opened and ends only when it is fully sold. Adding shares or partially selling does not restart the holding timer. Stop-loss advice uses current weighted-average entry price excluding fees. Trailing-stop advice uses the highest valid daily close since the position opened. Fully selling clears these references; a later purchase starts a new holding period. Exit alerts never place orders automatically.

**Approved V1 exit baseline: Option 2, balanced exit.** These are versioned paper-trading evaluation settings, not validated BRVM parameters or guaranteed loss limits. Evaluate at daily closes. Let `P` be the current close, `E` the current gross weighted-average entry, and `H` the highest valid close since opening.

| Exit rule | Approved condition |
|-----------|--------------------|
| Loss alert | `P <= 0.95 * E` (5% below entry) |
| Trailing activation | A close reaches `P >= 1.08 * E` (+8% relative to current entry) |
| Activated trailing exit | `P <= 0.96 * H` (4% decline from the highest close) |
| Technical deterioration | Two consecutive exchange-session closes are each below their own session's EMA20, with latest RSI14 <45; OR current EMA20 <= EMA50 |
| Maximum duration | Opening execution session = 0; following exchange session = 1. Duration Sell advice starts at the close of session 30 and remains applicable while the position stays open |

Any one exit trigger produces Sell advice; the two-session technical confirmation does not delay loss, activated trailing, EMA crossover, or duration advice. Show all triggered reasons. Keep applies to an existing paper holding only when all applicable checks are assessable and none triggers. If no exit is established but a required check is unavailable, do not silently report Keep. A verifiable exit can still be reported while explicitly marking another check unavailable. Missing sessions cannot be skipped to manufacture consecutive-session confirmation.

Falling below the 70% Buy threshold, overextension, and failure of the Buy liquidity gate are not standalone Sell triggers. Do not calculate Sell strength as `100 - Buy strength`; shared entry evidence and personalized holding advice remain distinct. Alerts require manual order submission and the agreed next-session-close execution convention, so execution prices may differ materially from alert levels and fees reduce returns.

Example with unchanged `E = 1,000 XOF`: the loss alert level is 950, trailing activation is 1,080, and a subsequent high close of 1,150 gives a trailing exit level of 1,104. Additional buys and partial sells retain the established timer and high-water reference.

**Confirmed exit-state conventions:** Once trailing protection activates, it remains active until the position is fully closed or the portfolio is reset. Additional buys that change average entry and partial sells do not deactivate it. Before activation, evaluate each new valid close against `1.08 * E` using the entry applicable to that session; never compare an old high with a newly reduced entry to activate retroactively. For example, an already active position with high 1,150 retains its 1,104 trailing level even if an additional buy raises average entry to 1,100. This is not a guaranteed net profit.

Count elapsed exchange sessions from the intended execution session of the opening buy, which is session 0, regardless of later processing delay. Exclude exchange holidays and weekends; a session counts even when the stock does not trade or its price is missing. Neither missing prices nor additional buys/partial sells pause or restart the timer. A manual order submitted after the session-30 alert targets session 31's close under the existing convention; 30 sessions is an advice deadline, not guaranteed liquidation.

Each open position retains the exit-rule version and immutable configuration assigned when it opens until fully closed. Additional buys inherit that policy; a newly opened position uses the then-active policy. Future rule changes do not silently migrate open positions. Retain the old evaluator/configuration for active positions and historical reproducibility. Fully closing and reopening creates fresh activation, timing, high-water and policy references; portfolio reset clears the simulation as already specified.

Evaluate turnover, drawdowns, subsequent returns and fee-adjusted paper outcomes. Compare fixed-percentage distances in ATR units to understand volatility sensitivity; this does not authorize ATR-based exits. Fast-exit and patient-exit alternatives were not selected for V1.

### 6.4 Confirmed V1 Indicator Scope

| Core indicator | User-facing analytical purpose | Contract boundary |
|----------------|---------------------------------|-------------------|
| EMA | Explain price trend and price position relative to the exponential moving averages | Confirmed fast EMA 20 and slow EMA 50 sessions; EMA 20 is the price-extension reference. Entry comparisons are specified below; initialization is defined in section 6.6 |
| RSI | Explain momentum and its current strength or stretched condition | Confirmed 14 sessions with Wilder smoothing; overbought/oversold labels alone do not mandate a trade |
| ATR | Explain recent price variability, including gaps | Confirmed 14 sessions with Wilder smoothing; requires high, low, and previous close; measures volatility rather than direction; ATR-based exits have not been approved |
| Traded value | Explain trading activity in XOF and support liquidity assessment | Confirmed median >= 5,000,000 XOF over 20 exchange sessions and trading in at least 18 of those sessions; distinguish actual source turnover from a labeled price-times-volume estimate |

Each indicator must be inspectable with its dated value, configured period where applicable, plain-language definition, interpretation, and limitations. The confirmed V1 strategy remains trend confirmation, using a percentage signal-strength score with partial credit: EMA up to 40 points, RSI up to 30, and ATR-based extension up to 30. Display signal strength, not a probability of profit. Failure to qualify for Buy does not automatically imply Sell. Previous all-technical-conditions-pass proposals are superseded.

**Approved evaluation baseline:** The stakeholder accepted the financial review's corrections. These reference points are provisional strategy settings for versioned paper-trading evaluation, not empirically validated BRVM thresholds. Let `A = ATR14(t)`, `g = (EMA20(t) - EMA50(t)) / A`, `s = (EMA20(t) - EMA20(t-5)) / A`, and `e = (close(t) - EMA20(t)) / A`; `t-5` means five exchange sessions earlier. Required inputs must be available and valid, with `A > 0`; otherwise mark the score unavailable without reweighting.

| Contribution | Approved reference points and interpolation |
|--------------|--------------------------------------------|
| EMA alignment, 0-20 | `20 * min(1, max(0, g))`: zero at/below 0 ATR separation, 10 at 0.5 ATR, 20 at/above 1 ATR |
| EMA direction, 0-20 | `20 * min(1, max(0, s / 0.5))`: zero for flat/falling EMA20, 10 at a 0.25 ATR rise, 20 at/above a 0.5 ATR rise over five sessions |
| RSI momentum, 0-30 | RSI <=40: 0; RSI 50: 15; RSI 55-65: 30; RSI 70: 15; RSI >=80: 0. Linear interpolation between consecutive reference points |
| ATR extension, 0-30 | `e < 0`: 0; `0 <= e <= 1`: 30; `1 < e < 3`: `15 * (3 - e)`; `e >= 3`: 0 |

Buy requires the unrounded total >=70, median traded value >=5,000,000 XOF, trading in at least 18 of the last 20 exchange sessions, and all four structural guards: `EMA20(t) > EMA50(t)`, `close(t) >= EMA20(t)`, `EMA20(t) > EMA20(t-5)`, and `e < 3`. Section 6.6 additionally requires mature indicator chains and a confirmed current-session trade/close with no active suspension. Publish failed-guard reasons alongside any available score; a high score never overrides a failed guard. Display one decimal place, but rounding must not promote a below-threshold result.

Review fixtures must include a flat/falling EMA20 with theoretical contributions 20+0+30+30=80 that is not Buy-eligible, and an extension >=3 ATR with contributions 20+20+30+0=70 that is not Buy-eligible. Also cover exactly 70 with passing guards, failed liquidity, and the strict guard boundaries. These are calculation fixtures, not evidence of realizable market performance.

The RSI curve remains the active evaluation candidate; compare a gentler high-RSI penalty offline because RSI and extension may penalize the same move. This does not introduce a second live V1 strategy. ATR also normalizes both EMA contributions, so it influences up to 70 points; components are coupled, not independent evidence. Historical evaluation must examine subsequent returns, drawdowns, turnover, and results after fees under the agreed paper-execution rules, including denominator sensitivity. Initialization/warm-up and evidence-status labels are defined in section 6.6 and the financial calculation contract; no separate probability-like confidence score is introduced.

Periods refer to exchange trading sessions, not calendar days or only sessions on which the stock traded. The 20-session liquidity median includes confirmed zero-turnover sessions, never substitutes zero for missing observations, and is accompanied by the count of sessions with trading. The adopted financial calculation contract specifies verified no-trade versus unknown observations, separate analytical inputs, exact recursive seeds and 250-session warm-up; windows never silently compress time. Low ATR does not override the liquidity gate. Historical holdout evaluation with fees and execution limitations is separate from calculation unit tests.

Later app versions may replace this strategy, including with pullback or weighted-score approaches, without rewriting historical recommendations. Preserve the strategy identity, rule/configuration version, input reference, and original evidence for each result. V1 requires one active strategy, not user-selectable strategies or simultaneous evaluation of multiple strategies.

The paper-accounting and position-reference rules in section 6.3 remain confirmed. Adding ATR does not silently replace those rules with an ATR-multiple stop or change the manual-order requirement.

### 6.5 Confirmed Long-Term Scoring Approach

The stakeholder selected Option 2: a sector-aware scorecard using fixed, versioned scoring rules and financially appropriate measures for banks, insurers, and non-financial companies. A universal cross-sector scorecard and peer-percentile ranking were not selected as the V1 scoring method. This does not require a separate model for every industry. Category and metric definitions are adopted in section 6.6 and the financial calculation contract; verified issuer mapping and source acquisition remain implementation dependencies.

| Score | Approved analytical dimensions |
|-------|--------------------------------|
| Growth, 0-100 | Multi-year revenue and earnings growth; profitability and consistency; sector-appropriate financial resilience; valuation at the current share price |
| Dividend, 0-100 | Regularity of ordinary payments; dividend maintenance and growth; earnings coverage and payout sustainability; ordinary dividend yield at the current price |

Growth means capital-growth attractiveness, not merely historical business growth. Keep both component scores visible and unchanged when the investor changes objective; objective-specific weights change the overall rating and advice. Balanced-quality dimension weights, mixed-horizon history (B/B), distinct-objective blends, the 12/18 revenue/net-income growth allocation and its balanced scoring baseline/earnings exceptions are approved below. The remaining dimension formulas, bands and advisory guards are adopted under stakeholder delegation in section 6.6. Scores are not return forecasts or probabilities.

**Confirmed objective blends: Option 1, distinct objectives.** Let `G` and `D` be the assessable Growth and Dividend scores for the same company, input snapshot and rule version.

| Objective | Growth weight | Dividend weight | Overall rating |
|-----------|---------------|-----------------|----------------|
| Capital growth | 100% | 0% | `G` |
| Dividend income | 0% | 100% | `D` |
| Balanced | 50% | 50% | `(G + D) / 2` |

These are score weights, not portfolio allocations. A low dividend score does not reduce the capital-growth rating; Growth already includes profitability, resilience and valuation, while Dividend includes coverage and sustainability. Both component scores remain visible with explicit unavailability where applicable. An unavailable required score is never zero or silently replaced by the other score. Keep serious-risk/advisory eligibility checks separate from the numerical rating; a high score or balanced average does not alone establish suitability. The adopted guards are defined in the financial calculation contract section 5. The 80/20 and 65/35 alternatives were not selected for V1.

Acceptance example with assessable `G=85` and `D=25`: capital-growth overall is 85, dividend-income overall is 25, and balanced overall is 55. Objective selection changes neither component score nor its evidence.

| Growth dimension | Maximum points | Dividend dimension | Maximum points |
|------------------|----------------|--------------------|----------------|
| Revenue and earnings growth | 30 | Ordinary-payment regularity | 25 |
| Profitability and consistency | 25 | Dividend maintenance and growth | 15 |
| Financial resilience | 20 | Earnings coverage and payout sustainability | 40 |
| Valuation at current price | 25 | Ordinary dividend yield | 20 |

Each score totals 100 possible points. These are provisional evaluation weights, not empirically optimized BRVM weights. Keep dimension weights common across sectors while defining financially appropriate underlying metrics and scoring bands; no unapproved sector-specific weight changes are implied.

**Confirmed growth allocation: Option 2, moderate earnings emphasis.** Within the 30-point revenue and earnings growth dimension, allocate 12 points to three-year revenue CAGR and 18 points to three-year company net-income CAGR. The contribution is `12 * revenue_growth_factor + 18 * earnings_growth_factor`, with each factor normalized to 0-1 using the approved baseline below. Equal 15/15 weighting and separately scored latest-year momentum were not selected for V1.

Latest annual revenue and net-income changes remain visible as context and deterioration alerts, without a separate numerical bonus or penalty in this dimension. Sustained profitability remains in the existing 25-point profitability/consistency dimension. Company net-income growth is not EPS growth and does not account for shareholder dilution. Use sector-appropriate revenue definitions; bank and insurance metric mappings follow the financial calculation contract, with source coverage still to verify. Known losses and recoveries are evidence, not missing records; use the approved earnings exceptions below, never ordinary percentage growth from a negative base. Tiny positive bases and exceptional earnings require explanatory qualification, not unsupported normalization adjustments. The 12/18 split is an evaluation baseline, not an empirically validated BRVM calibration.

**Confirmed growth bands: Option 2, balanced evaluation baseline.** For comparable positive starting and ending values, `CAGR = (value_latest / value_three_fiscal_years_earlier)^(1/3) - 1`. Let `clamp(x, 0, 1) = min(1, max(0, x))`. Revenue points are `12 * clamp(revenue_CAGR / 0.15, 0, 1)`; earnings points are `18 * clamp(net_income_CAGR / 0.20, 0, 1)`, subject to the earnings exceptions below. Nonpositive CAGR earns zero growth points; full credit starts at 15% revenue CAGR and 20% earnings CAGR, with continuous linear credit between zero and those thresholds and no extra credit above them. The 10%/15% and 20%/30% alternatives were not selected. These are provisional evaluation thresholds, not established BRVM benchmarks; validate them against sector-appropriate measures before freezing category contracts. They do not establish interchangeable revenue semantics across sectors.

| Earnings/history condition | Approved V1 treatment |
|----------------------------|-----------------------|
| Latest net income is zero or negative | Award 0/18 earnings-growth points with a break-even/loss explanation; do not display ordinary earnings CAGR |
| Starting net income is zero or negative and latest is positive | Label recovery, award 0/18 earnings-growth points under this conservative rubric, and do not fabricate ordinary CAGR |
| Positive endpoints with an intervening loss | Calculate endpoint CAGR and flag interrupted profit history; assess consistency in its existing dimension |
| Positive starting net income below 10% of median absolute annual net income over the five-year history | Show a small-base warning; retain the capped formula without an extra points adjustment |
| Required observations missing | Mark the dependent score unavailable, with no zero substitution or weight redistribution |

Zero earnings points for known loss/recovery cases are an explicit scoring policy, not missing-data imputation or a claim that a turnaround has no investment value. The small-base comparison is strict (equality does not trigger); use all five annual absolute net-income observations, including confirmed zeros. A zero median cannot satisfy the warning condition for a positive starting value. Warning and contribution caps do not eliminate denominator distortion. Qualify exceptional earnings without inventing adjusted earnings. No new latest-year scoring adjustment is introduced. The financial calculation contract section 3.1 explicitly defines nonpositive activity endpoint treatment; do not infer missing observations to be observed zeros.

Acceptance fixtures: 7.5% revenue CAGR and 10% earnings CAGR contribute 6+9=15/30; 15% and 20% contribute 12+18=30/30; higher rates cannot exceed these maxima. Test zero/negative CAGR with positive endpoints, loss/recovery exceptions, intervening losses, missing history and the small-base warning boundary separately. These are calculation fixtures, not evidence of investment effectiveness.

**Approved mixed-horizon history:** Require five completed fiscal years of relevant records for score eligibility. Use three-year revenue and earnings CAGR where mathematically meaningful and show the latest annual change. A three-year CAGR requires four annual observations; the fifth year supports consistency assessment. Assess profitability across five years and in the latest year; assess resilience from the latest reported balance sheet with historical trend context. Review five fiscal years of ordinary-dividend history, three-year dividend growth where meaningful, and payout coverage for the latest matched fiscal year plus the preceding two years. Within-dimension aggregation is specified in the adopted financial calculation contract.

Historical yield is ordinary dividends actually paid during the trailing 12 months divided by the latest valid close, explicitly labeled historical rather than forecast. Match dividend amounts to the relevant earnings fiscal year for payout analysis; use actual payment dates for trailing yield, not an assumed fiscal-year offset. Price/share-basis compatibility and required input contracts must be verified before these measures are calculated.

Five years of records does not require five profitable years or five dividend payments. Confirmed zero dividends are observations; missing records are not zeros. Companies lacking required history remain visible with explicit score unavailability, without silent shorter-window fallback or weight redistribution. Preserve observed losses and dividend cuts as evidence, not missing data. Verify source coverage before implementation; approved windows do not establish that the existing pipelines contain the required history. Historical consistency is not a promise of future performance.

Apply sector-appropriate interpretation: do not penalize bank deposits or insurance liabilities using industrial-company net-debt rules. A loss-to-profit transition is a recovery, not ordinary percentage growth from a negative base. Exceptional dividends must not inflate recurring-income assessment. High yield alone must not establish dividend attractiveness; payment history and coverage matter. Keep serious-risk/advisory eligibility checks separate from the numerical total, with the adopted rules in the financial calculation contract.

Calculate only supported measures. Missing required inputs produce explicit unavailability, never silently redistributed points. Verify compatible share counts, EPS or total dividend amounts before including P/E, price-to-book or payout ratios; do not divide dividend per share by company-wide net income. Cash-flow coverage and regulatory-capital measures require additional source inputs and are not established by the existing five-field financial extraction. Revenue, income, debt, cash, equity and dividend extraction code does not establish complete historical coverage. The adopted calculation contract defines required metrics, formulas and failure states; verify and acquire those inputs before producing dependent scores. This is calculation validity, not a separate data-quality feature.

### 6.6 Delegated Financial Baseline

**Superseding V1 scope amendment, approved 2026-09-20:** Only one year of dividend history is available and additional years cannot currently be acquired. Keep dividend research first-class, but defer full Dividend and Balanced scores, score-based rankings and recommendations beyond V1. Show recorded payments and their coverage; show trailing-12-month ordinary yield only with verified complete window and compatible payment/share/price semantics. Do not infer consistency, growth or sustainability from one year or replace the deferred score with yield-only scoring. Earlier Dividend/Balanced formulas and acceptance examples are retained solely as later-version design references. This amendment overrides earlier three-score/objective requirements throughout this document. Growth scoring retains its full input/history requirements: show supported metrics, mark incomplete scores unavailable, and never interpolate missing fiscal years. SHEC 2024 is unconfirmed in the full source. Additional dividend-history acquisition is not a V1 release prerequisite. See financial contract v1.1, section 1.

On 2026-09-19 the stakeholder authorized applying financial-analysis-expert recommendations to remaining Long-Term scoring and Swing conventions. [Financial Calculation Contract v1.1](tradvisor_financial_contract.md), including the 2026-09-20 scope amendment, is the normative calculation specification. This is an adopted, versioned evaluation baseline, not an assertion of empirical financial effectiveness.

| Area | Adopted rule |
|------|--------------|
| Profitability/consistency, 25 points | Latest ROE 10, median five-year normalized ROE 5, profitable-year frequency 10; full ROE credit at 15%, with explicit nonpositive-equity treatment |
| Resilience, 20 points | Non-financial net debt/equity 12 plus current ratio 8; banks/insurers use matched regulatory capital/solvency coverage 20, not industrial liabilities |
| Valuation, 25 points | Historical earnings yield 15 plus guarded price/book 10; no cheap-book credit for observed nonpositive earnings/equity |
| Dividend, 100 points | Paid ordinary regularity 25; maintenance 10 and growth 5; annual payout coverage 20/10/10; trailing ordinary yield 20, capped at 8% yield |
| Long-Term advice | Unrounded >=70 candidate, 50 to <70 watchlist, <50 low score; independent financial, freshness and dividend-sustainability guards. Not personalized Sell advice |
| Sector and input validity | Explicit bank PNB, insurer gross written premium and industrial revenue mappings; source-required share basis, ordinary-owner claims, capital coverage and paid-dividend attribution; no missing-input reweighting |
| Swing initialization | SMA-seeded EMA20/50; Wilder RSI14/ATR14 from 14 changes/TR values; explicit flat RSI=50; 250 uninterrupted session closes before actionable calculation |
| Non-trading sessions | Confirmed no-trade sessions carry analytical close and explicitly model zero TR without inventing OHLC candles; unknown observations interrupt dependent recursion. Show the modeled basis and its volatility limitation |
| Liquidity basis | Complete actual 20-session turnover window preferred; complete, consistently labeled close-times-volume window permitted as fallback. Original 5m XOF and 18/20 thresholds retained |
| Additional Swing guard | A confirmed current-session trade/close and no active suspension are also required for Buy; no-current-trade is not automatic Sell |
| Confidence semantics | Numerical Swing signal strength and Long-Term scores are not profit probabilities. Publish factual calculation availability, freshness and actual/estimated/modeled basis instead of an additional confidence percentage |

The contract also defines loss/recovery cases, denominator boundaries, comparison inclusivity, missing-data behavior, corporate-action compatibility, point-in-time evidence, advisory explanations and acceptance fixtures. Financial report freshness is 18 calendar months from period-end; current Long-Term price advice requires an actual traded close at most five exchange sessions old. These are product settings, not legal or financial guarantees.

Several required inputs are not established by the reused five-field extractor. Extend existing adapters and verify coverage; show unavailable dependent scores until supported. This is tested calculation logic, not a separate data-quality feature. Source integration, market-calendar integration and historical effectiveness evaluation remain implementation/validation work.

## 7. Functional Requirements

### 7.1 Swing Trading

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-SW-01 | The system shall show every BRVM stock in the daily Swing workspace with `Buy`, `Keep`, `Sell`, `No clear signal`, or `Insufficient data`. | Must | Stakeholder interview | Given the latest market data has been processed, when the user opens the Swing workspace, then each listed stock has exactly one displayed state. |
| FR-SW-02 | The system shall assign `Insufficient data` when mandatory inputs or history are unavailable. | Must | Stakeholder interview | Given a stock lacks mandatory input data, when daily evaluation runs, then no Buy, Keep, Sell, or No clear signal outcome is produced and the missing basis is shown. |
| FR-SW-03 | The system shall provide signal strength, factual evidence status and a plain-language explanation for each Swing result, without implying a probability of profit. | Must | Stakeholder interview and delegated section 6.6 financial review | Detail exposes assessable signal strength or unavailability, freshness, actual/estimated/modeled input basis, indicator values, conditions met or unmet and rule version. No separate probability-like confidence percentage is shown. |
| FR-SW-04 | The system shall make EMA, RSI, ATR, and traded value available for inspection, with dated values, periods, explanations, and calculation limitations. | Must | Stakeholder-confirmed V1 indicator selection | Given sufficient valid history, when technical analysis opens, then all four core indicators are inspectable; unavailable indicators show a reason, and estimated traded value is distinguishable from actual turnover. |
| FR-SW-05 | The system shall apply the versioned section 6.4 scoring baseline, with 40/30/30 allocations, minimum Buy score 70%, mandatory liquidity and structural guards, while allowing strategy replacement in later app versions. | Must | Stakeholder-approved financial review and scoring baseline | Given section 6.4 fixtures, Buy requires the unrounded score >=70 and all eligibility guards. Contributions and rejection reasons are reproducible; rounding cannot promote eligibility. Missing mandatory inputs or nonpositive ATR prevent an actionable score. Historical results remain unchanged after strategy changes. |
| FR-SW-06 | The system shall generate personalized Keep/Sell advice using the versioned balanced exit baseline in section 6.3: 5% loss alert, +8% trailing activation, 4% trailing decline, technical deterioration and 30-session maximum duration. | Must | Stakeholder-approved balanced exit policy | Any established exit trigger produces Sell advice with reasons and no automatic order. Keep requires assessable checks with no trigger; missing inputs do not silently imply Keep. Additional buys/partial sells retain the timer and high-water reference; fully closing then reopening starts new references. Buy ineligibility alone does not imply Sell. |
| FR-SW-07 | The system shall retain the rule version and evidence that produced each historical Swing result. | Should | Business analyst interpretation of explainability requirement | Given a rule is changed after a result is recorded, when the historical result is viewed, then its original rule version and explanation remain available. |

### 7.2 Paper Trading

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-PT-01 | The system shall let the user manually create a paper Buy or Sell order from a current Swing recommendation, including a Sell overriding Keep advice. | Must | Stakeholder interview and 2026-09-20 override/freshness approvals | Valid manual commands create pending orders. Advice must be evaluated for the latest completed authoritative exchange session; stale advice requires refresh and renewed confirmation. Selling from Keep requires visible advice and explicit override acknowledgment; preserve that advice and override on the order without changing the recommendation. Ownership, available shares, fees and execution checks still apply. Dated results remain readable during delays; accepted orders retain their original execution/expiry rules. |
| FR-PT-02 | The system shall price a paper order at the next BRVM trading session's close, with a one-additional-trading-session grace period for delayed closing data. | Must | Stakeholder-approved section 6.3 | Given the original intended-session close arrives within the grace period and resources are sufficient, then execute at that price with session and processing timestamps; if the price misses the deadline, expire with a reason and released reservations, without substituting another session's price. Insufficient resources follow FR-PT-05 instead. |
| FR-PT-03 | The system shall support only long-only paper trading. | Must | Stakeholder interview | Given the virtual portfolio holds no shares of a symbol, when the user attempts a paper Sell, then the system prevents the order. |
| FR-PT-04 | The system shall maintain a single XOF paper portfolio with starting cash defaulting to 1,000,000 XOF, configurable in whole XOF from 100,000 to 100,000,000 inclusive at setup or reset only, and an explicitly selected percentage fee frozen per order and applied to buys and sells. | Must | Stakeholder-approved section 6.3 | Accept both starting-cash boundaries; reject fractions/out-of-range amounts without state changes. No active-simulation top-ups or starting-cash edits. Fee changes affect new orders only; executed fees use whole-XOF half-up rounding. |
| FR-PT-05 | The system shall reserve resources at submission and prevent orders exceeding available cash or held shares, including an affordability recheck at execution. | Must | Stakeholder-approved section 6.3 | Given insufficient resources at submission, then reject without a ledger change; given an accepted order becomes unaffordable at execution, then reject the entire order and release its reservation without a partial fill or execution fee. |
| FR-PT-06 | The system shall show cash, pending orders, holdings, weighted-average entry price, latest value, gross and fee-adjusted realized/unrealized simulated P&L, and exit alerts. | Must | Stakeholder-approved section 6.3 | Given additional buys and partial sells, then remaining purchase cost and purchase fees are allocated proportionally and reconcile with executions; net realized P&L includes allocated purchase and actual sell fees, while unrealized net P&L excludes a hypothetical sell fee. |
| FR-PT-07 | The system shall let the user reset the paper portfolio at any time. | Must | Stakeholder interview | Given the user confirms a reset, when reset completes, then pending orders, holdings, and performance history are cleared and virtual cash equals the selected starting balance. |

### 7.3 Long-Term Investing

| ID | Requirement | Priority | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-LT-01 | The system shall support Capital growth and Dividend income research as Long-Term objectives; Balanced scoring is deferred beyond V1. | Must | Stakeholder-approved 2026-09-20 amendment | Capital growth exposes eligible score-based rankings; Dividend income exposes supported payment facts and conditional historical yield, without a composite score or suitability ranking. |
| FR-LT-02 | The system shall display a 0-100 Growth score and equal Capital growth overall rating for companies with complete required inputs/history, keeping other catalog companies visible with supported metrics and explicit missing-input explanations. Dividend and Balanced scores are deferred beyond V1. | Must | Stakeholder-approved 2026-09-20 scope and coverage amendments | Complete required inputs produce scores in 0-100; incomplete inputs produce unavailable totals, not low or reweighted partial scores. Separate insufficient-evidence companies from complete-score rankings; advisory guards still apply independently. Review actual company/sector coverage with the product owner before launch and explicitly revisit scope if coverage is insufficient for a useful Long-Term workflow. No numeric coverage threshold has been agreed. No Dividend/Balanced numeric score is published. |
| FR-LT-03 | The system shall use the approved sector-aware Growth scorecard, weights, history and guards without shortening windows or redistributing weights. | Must | Stakeholder-approved scorecard and 2026-09-20 amendment | Growth dimension maxima total 100; overall equals G. Missing fiscal years are not interpolated. Dividend-history gaps alone do not block Growth. Dividend/Balanced formulas remain deferred references, not V1 acceptance requirements. Apply section 6.6 and financial contract v1.1. |
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

| NFR-07 | The pilot shall support 25 invited users and 5 concurrent sessions, with 95th-percentile normal API reads within 2 seconds excluding cold starts/network transit, and publish daily results within 15 minutes after required market inputs are ready. | Must | Stakeholder-approved operating baseline, 2026-09-20 | Representative load and batch tests meet these targets; delayed sources preserve the last published dated results without implying freshness. |
| NFR-08 | Pilot availability shall be best-effort with no overnight support or contractual uptime guarantee; recovery shall target 24 hours from incident acknowledgement, using the latest successful usable daily backup without a strict 24-hour maximum application-change loss. | Must | Stakeholder-approved operating baseline and data-loss relaxation, 2026-09-20 | Daily application-state backups retained for 7 days; monitor backup age and failures, and report the actual restored recovery point and potential lost-change interval. Backup cost validation and a successful restore test are release prerequisites. Restoration must not resurrect reset simulations or removed access. |
| NFR-09 | Retention shall preserve calculation evidence and active simulation history while applying the approved lifecycle limits below. | Must | Stakeholder-approved operating baseline, 2026-09-20 | Verify lifecycle boundaries, reset cleanup, idempotency protection and restore behavior against the retention table. |
| NFR-10 | The complete V1 application shall target WCAG 2.2 Level AA, including authentication and complete paper-trading workflows. | Must | Stakeholder approval, 2026-09-20 | Automated checks plus manual keyboard and screen-reader testing cover both workflows; advisory actions are not color-only, chart data has accessible tabular equivalents, and tables/drawers/resizable panels are keyboard-operable. |

### 8.1 Approved Retention And Recovery Baseline

| Data | V1 retention |
|------|--------------|
| Market/financial source evidence and rule versions | Retain history and versions needed for calculations and retained recommendations; no simple annual deletion of scarce financial history. |
| Published recommendations | 12 months with supporting evidence. Retain evidence longer where still required by an active simulation. |
| Paper history | Throughout the active simulation. Reset hides the previous generation immediately; remove old operational records within 7 days. |
| Idempotency receipts | 30 days, retaining only the information needed to prevent duplicate commands, not cleared financial history. |
| Operational logs | 30 days; exclude passwords, tokens and unnecessary personal data. |
| Application-state backups | Daily, retained for 7 days. Old records may remain in inaccessible backups until expiry; restore must reapply reset exclusions before serving users. |

**Data-loss amendment (approved 2026-09-20):** Recover application state from the latest successful usable daily backup; changes after that recovery point may be lost. The strict 24-hour maximum loss is removed, not replaced with another guaranteed maximum. Daily backups and 7-day retention remain required; monitor backup age and failures and report the recovery point and potential lost-change interval during recovery. If no usable backup exists, report that recovery is unavailable rather than imply a guarantee. This relaxation never authorizes resurrection of deliberately reset simulations or removed access. The recovery-time target remains 24 hours from incident acknowledgement, not occurrence; no overnight acknowledgement commitment is implied. Backup mechanism, cost and reset-safe restoration must be validated before claiming the recovery targets are met. These operational periods do not establish legal retention obligations. WCAG 2.2 AA is approved in NFR-10. The product owner accepts launch/coverage/costs; one technical operator owns exceptions and recovery. Name the operator and support contact before launch. The V1 access model is confirmed in section 9.4.

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

V1 does not process real brokerage positions or imports. The stakeholder approved email/password sign-in with verified email, password reset, and an administrator-managed email allowlist on 2026-09-20. Any email provider is supported; Google sign-in is not required or committed for V1. Only verified, currently allowlisted accounts may read application data or use paper trading. Removing access denies subsequent protected requests even with an otherwise valid sign-in session. Allowlist management is manual through trusted administrative tooling, with no invitation-management UI or public application admission in V1. Authentication account creation alone never grants access. Paper records remain owned by the authenticated user, not a caller-supplied identity.

Acceptance: unverified, non-allowlisted and removed users cannot read protected data or submit paper commands; admitted users cannot access another user's private records; password reset and email verification flows are available. Personal-data handling, disclaimer wording, applicable investment-advice regulation, and audit-retention obligations remain material open questions for appropriate owners before release.

## 10. Assumptions, Constraints, Dependencies, Risks, and Mitigations

### 10.1 Assumptions

| ID | Assumption | Validation owner | Impact if false |
|---|---|---|---|
| ASM-01 | Latest BRVM daily market data is available frequently enough to publish an after-close recommendation. | BigQuery data owner | Daily Swing outcome cannot be delivered as stated. |
| ASM-02 | XOF is the sole V1 paper-portfolio currency. | Product owner | Portfolio model and UX require expansion. |
| ASM-03 | One paper portfolio per user is sufficient for V1. | Primary user / product owner | Multiple simulations require scope expansion. |
| ASM-04 | Adopted score weights, evidence-status logic and thresholds are configurable and versioned under the financial calculation contract without expanding V1 scope. | Product owner / delivery team | Source coverage, calculation verification and historical evaluation remain prerequisites to actionable pilot publication; financial rule choices are adopted. |

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
| DEP-03 | Implement and verify the in-scope financial input/calculation contracts, source coverage and historical evaluation. | Product owner | Source acquisition and empirical validation remain pending; starting cash is confirmed in section 6.3. Dividend/Balanced scoring is deferred under section 6.6. |
| DEP-04 | Security, privacy, and investment-advice compliance review. | Product owner with legal/security support | To be confirmed |

### 10.4 Risks and Mitigations

| ID | Risk | Mitigation |
|---|---|---|
| RISK-01 | Thin or incomplete market data could produce false confidence. | Display factual availability, freshness and input basis; apply calculation guards and automated tests, with separate historical effectiveness evaluation. |
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
| OQ-02 | Have the in-scope financial input requirements and empirical evaluation been verified? | Sector-aware Long-Term scoring, B/B dimension weights, mixed-horizon history and distinct-objective blends are confirmed in section 6.5. Scored trend confirmation is confirmed in section 6.4. Balanced exits and state conventions are confirmed in section 6.3. Section 6.6 and the financial calculation contract resolve remaining financial rule choices and confidence semantics; input coverage and empirical evaluation remain outstanding, distinct from rule adoption. Starting cash, fee and accounting rules are settled; Dividend/Balanced scoring is deferred under the section 6.6 amendment. | Product owner |
| OQ-03 | What is the data-refresh schedule, data-delay expectation, and authoritative market-close definition? | Daily recommendation timing and status depend on it. | BigQuery data owner |
| OQ-04 (resolved) | Small invited group; email/password with verified email, password reset and manually administered email allowlist. | Backend admission and ownership enforcement; no invitation-management UI in V1. | Stakeholder confirmed 2026-09-20 |
| OQ-05 | What legal, regulatory, disclaimer, and record-retention requirements apply to BRVM investment-advisory content? | Determines release readiness and user communication. | Product owner / legal owner |
| OQ-06 (roles and target resolved) | Who is the named technical operator and support contact? | WCAG 2.2 AA and operational roles are approved; nominate the operator/contact before launch and verify NFR-07 through NFR-10. | Product owner |

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
| Security / legal owner | Verify the approved access controls and confirm privacy, disclaimer, and investment-advice obligations. |
| Delivery team | Produce architecture and implementation backlog only after the above decisions are recorded or accepted as explicit assumptions. |

This document is a Draft for Review until the approval section is completed.
