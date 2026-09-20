<!-- Public derivative: operational identifiers and private inventory excluded. Normative behavior unchanged. -->

# Tradvisor V1 - Financial Calculation Contract

**Version:** 1.1
**Date:** 2026-09-20
**Status:** Adopted evaluation baseline under stakeholder delegation; not empirically calibrated
**References:** `tradvisor_brd.md` sections 6.4-6.6; `tradvisor_architecture.md` section 5

## 1. Authority And Boundaries

### Approved V1 Coverage Amendment - 2026-09-20

Only one year of dividend history is currently available, and the stakeholder confirmed that additional years cannot be acquired at present. Full Dividend and Balanced scores, their score-based rankings and recommendations are deferred beyond V1. Dividend research remains a first-class part of Long-Term: display recorded payments with their actual coverage, and historical ordinary yield only when a complete trailing-12-month window, payment semantics and compatible share/price basis are verified. Do not infer consistency, growth or sustainability from one year, substitute a yield-only score, or treat unknown years as zero.

Growth scoring and its guards remain unchanged. Publish supported individual metrics but withhold the full Growth score when required inputs/history are absent; never interpolate a missing fiscal year. Private samples do not establish consecutive full-source fiscal coverage; do not infer market-wide gaps from a sample. Dividend-history limitations alone do not block Growth.

This amendment takes precedence over earlier V1 objective requirements below. Section 4 and Dividend/Balanced formulas, advice and fixtures elsewhere are retained as deferred design references, not V1 implementation or release requirements. Additional dividend-history acquisition is not a V1 blocker. Restoring those scores requires a later scope decision and verified inputs; do not automatically activate them if additional records arrive. Swing and paper-trading rules are unchanged.

The stakeholder authorized applying financial-analysis-expert recommendations to the remaining Long-Term scoring and Swing calculation conventions. This contract resolves those rule choices without another option-selection round. Previously approved indicator periods, Swing contribution curves, liquidity thresholds, exits, growth weights/bands and objective blends remain unchanged except for the explicit current-session trade eligibility guard below. No new service, indicator family, real-portfolio feature or automated execution is introduced.

All new numeric score bands, freshness limits and advisory thresholds below are V1 design settings, not market facts, regulatory minima, return probabilities or demonstrated BRVM predictors. Source acquisition, actual issuer coverage and empirical validation remain delivery dependencies. A missing required input produces explicit unavailability, never invented figures or redistributed weights. An explicit zero-point financial rule is not missing-data imputation.

This contract is authoritative for calculation details and supersedes earlier statements that these financial rule choices are pending. The BRD remains authoritative for product scope and previously approved paper accounting/execution. Version definitions, source snapshots and calculation anchors; never rewrite published historical recommendations.

## 2. Shared Financial Inputs

- Use five consecutive completed fiscal years, ordered oldest to latest, with comparable full-year reporting periods, currency, consolidation scope and accounting basis. Do not annualize an interim period into a scored annual observation. Store fiscal end, publication timestamp, ingestion timestamp and source reference; historical evaluation uses information available at that time, not subsequently published accounts.
- Use net income attributable to ordinary owners and matching attributable equity. Where only another income/equity basis is available, do not silently mix it into the contract. Ordinary shareholder earnings exclude any preferred entitlement when applicable. A reported loss remains a valid observation.
- Use six balance-sheet dates to calculate five annual average-equity denominators: opening equity for the oldest income year plus five year-ends. This adds one opening balance, not a sixth income-history year. Unknown opening balances are unavailable, not approximated by closing equity.
- Use issuer-level ordinary market capitalization `M` on the valuation date, matching the income/equity claim. For a single ordinary class, `M = valid close * ordinary shares outstanding excluding treasury shares` on that date. Distinct classes require verified aggregate capitalization of the matching ordinary claim; otherwise valuation is unavailable. Do not use free-float shares, weighted-average EPS shares or an unmatched price/share count as total capitalization.
- Dividend amounts are gross ordinary cash distributions before investor-specific tax. Keep ordinary and exceptional payments separate. Sum installments once using stable payment identity. Maintain both fiscal-year attribution and actual payment dates. Never infer fiscal year as payment year minus one.
- Fiscal dividend history uses ordinary distributions actually paid and attributed to each fiscal year, with explicit completion/no-payment evidence. A declared but unpaid installment is not a paid distribution and leaves that fiscal year's payment outcome incomplete. Do not shift the entire window backward to hide an unresolved latest fiscal year. This may delay Dividend score availability after annual accounts are published.
- Adjust historical dividend-per-share amounts to a common current share basis for splits/bonus issues using verified factors; rights issues or other complex events require verified comparable-series treatment. Do not treat capital increases as dividend growth. Retain original values and adjustment evidence. Per-share maintenance/growth uses adjusted DPS; earnings coverage uses matching company-wide ordinary distributions and ordinary-owner earnings.

### Sector Mapping

| Category | Activity growth input | Resilience inputs |
|----------|-----------------------|-------------------|
| Non-financial operating company | Reported consolidated sales/revenue | Interest-bearing debt, unrestricted cash/cash equivalents, attributable equity, current assets and current liabilities on a coherent reporting scope |
| Deposit-taking bank/banking group | Reported net banking income (PNB) | Disclosed regulatory capital adequacy and applicable required level, matched by date, jurisdiction and consolidation scope |
| Insurer/insurance group | Reported gross written premiums on a consistent basis; expose the label, not generic industrial sales | Eligible solvency capital/margin and required solvency capital/margin on the same regulatory basis |
| Unsupported, mixed or unidentified entity | Unavailable until a verified category mapping exists | No industrial fallback for financial holdings, funds or unsupported conglomerates |

Use issuer reports and verified company-reference metadata to assign categories, not the name alone. Do not splice insurance revenue under different accounting standards into a premium series. The approved 15% activity-growth ceiling is a common provisional starting band for these distinct activity measures, not a claim of economic equivalence. Regulators' required capital levels are sourced inputs, never the scoring constants below. Bank coverage uses the minimum disclosed coverage across applicable required capital constraints; missing a required constraint is unavailable. Insurance coverage uses the matched eligible/required solvency amounts. Applicable requirements must be verified during source integration; no jurisdiction's law is assumed here.

## 3. Long-Term Growth Score

Let `C(x) = min(1, max(0, x))`; rates in formulas use decimals, not percentage-point integers. Each dimension is bounded and retains its own evidence. An unavailable required term makes its dimension and dependent overall score unavailable; other assessable dimensions remain visible.

### 3.1 Activity And Earnings Growth: 30 Points

Retain the approved three-year endpoint CAGR, activity allocation 12 and earnings allocation 18, with full credit at 15% and 20% respectively. Retain the approved earnings loss/recovery rules, intervening-loss explanation and strict small-base warning in BRD section 6.5.

Complete the activity endpoint policy: a confirmed latest activity value <=0 earns zero activity-growth points; a starting value <=0 followed by a positive latest value earns zero with a recovery/new-base explanation. Neither displays ordinary CAGR. Negative bank PNB is an observed result, not missing data; anomalous negative industrial revenue requires verified reporting semantics before this rule applies. Unknown or incomparable values are unavailable, not classified as observed zero.

### 3.2 Profitability And Consistency: 25 Points

For each of five years, `ROE = ordinary_owner_net_income / ((opening_equity + closing_equity) / 2)`. Both equity endpoints must be positive to interpret ROE. If either is observed nonpositive, assign that year's normalized ROE factor zero with an invalid-equity explanation, without displaying a misleading ratio. Missing endpoints remain unavailable. With positive equity, `roe_factor = C(ROE / 0.15)`.

| Term | Points |
|------|--------|
| Latest-year ROE | `10 * latest_roe_factor` |
| Five-year typical ROE | `5 * median(five annual roe_factors)` |
| Profitable-year consistency | `10 * count(net_income > 0 in five years) / 5` |

The 15% ROE full-credit level is a provisional common band, not a cost-of-equity estimate. High leverage or very small equity can inflate ROE; the separate resilience dimension and guards below must remain visible. Five positive years earn consistency credit, but do not prove recurring earnings quality. No second revenue/earnings growth bonus is added here.

### 3.3 Financial Resilience: 20 Points

Non-financial companies:

- With positive equity, `ND_E = (interest_bearing_debt - unrestricted_cash) / equity`; debt factor is `C(1 - max(ND_E, 0))`, worth 12 points. Net cash and zero net debt both receive full credit; net debt/equity >=1 receives zero. Observed nonpositive equity earns zero debt-factor points without displaying the ratio.
- Current ratio `CR = current_assets / current_liabilities`; liquidity factor is `C((CR - 1) / 1)`, worth 8 points. CR <=1 earns zero; CR >=2 earns full credit. Confirmed zero current liabilities with positive current assets earns full credit without displaying infinity; zero assets and liabilities earns zero with an explanation. Negative balance-sheet inputs are unsupported, not good liquidity.
- Latest balance-sheet values determine points. Show prior-year net-debt/equity and current-ratio trends as context, without an additional adjustment. Assets and liabilities must be from a matching scope; a group with material unmatched noncontrolling claims requires a verified compatible dataset rather than a mixed-scope ratio.

Banks and insurers:

- Define `K` as regulatory capital/solvency coverage of the applicable required level, using the sector input contract. For banks, each disclosed capital ratio is divided by its corresponding required ratio and the minimum coverage is used. For insurers, `K = eligible_solvency_capital / required_solvency_capital`.
- Resilience points are `20 * C((K - 1) / 0.5)`: zero at/below the requirement, full credit at 1.5 times the requirement. This scoring buffer is not a legal requirement. Missing/zero required denominators are unavailable, not infinite coverage.
- Show latest and historical available coverage with dates. Do not use deposits, technical reserves or total liabilities as industrial debt. This narrow capitalization score does not establish comprehensive bank/insurer safety; credit quality, liquidity and underwriting risks remain limitations and available explanatory evidence, not invented inputs or extra weights.

### 3.4 Valuation: 25 Points

Require a positive matching ordinary market capitalization `M` and latest annual accounts. Use earnings/book yields to avoid misleading negative P/E values:

- Earnings-value contribution: `15 * C((net_income / M) / 0.10)` for positive net income; observed nonpositive net income earns zero. A 10% historical earnings yield receives full credit, not a promised investment yield.
- Book-value contribution: for positive equity AND positive latest net income, calculate `PB = M / equity` and award `10 * C((3 - PB) / 2)`. PB <=1 gets full credit, PB >=3 gets zero. Nonpositive equity or income earns zero book-value points, preventing automatic cheapness credit to a loss-making/negative-equity issuer.
- These are historical value screens, not intrinsic values or price targets. Book value is particularly limited for asset-light companies, and shared bands remain an evaluation baseline. Profitability, ROE and P/B are algebraically related; do not describe them as independent confirmation.

## 4. Long-Term Dividend Score

Let `D[y]` be ordinary paid cash dividend per share attributed to fiscal year y, adjusted to a common share basis, for five complete fiscal years. Let `T[y]` be matched total ordinary paid distributions to ordinary owners and `NI[y]` matching earnings. Confirmed no-payment years are zero; unresolved payments/missing records are unavailable. No ordinary dividend history is not the same as missing history.

| Dimension | Formula and boundary behavior |
|-----------|-------------------------------|
| Regularity: 25 | `25 * count(D[y] > 0) / 5` |
| Maintenance: 10 | Across four adjacent year pairs, award `10 / 4` for each pair with previous DPS >0 AND current DPS >= previous DPS. Zero-to-zero and a first payment after zero do not earn maintenance points. Use comparable unrounded DPS. |
| Growth: 5 | With positive three-year endpoints, `5 * C(dividend_CAGR / 0.10)`. Latest zero or a nonpositive starting base earns zero with cessation/restart explanation, not fabricated CAGR. An intervening cut remains visible and affects maintenance. |
| Coverage/sustainability: 40 | Apply the annual payout factor below with weights 20 latest, 10 previous, 10 two years earlier. |
| Historical ordinary yield: 20 | `20 * C(trailing_12_month_ordinary_paid_DPS / current_valid_close / 0.08)`. Zero payments earn zero; full credit at 8%, with no extra credit beyond it. |

Annual payout factor: if `T <= 0` or `NI <= 0`, assign zero; otherwise `p = T / NI` and factor `C((1.20 - p) / 0.40)`. A positive payout up to 80% of positive earnings earns full annual credit; credit declines linearly to zero at 120%. Do not divide DPS by company net income. Negative distributions are invalid source values. This plateau avoids claiming that a lower positive payout is always better; payout, regularity and yield must be read together.

The trailing window is `(valuation_date minus 12 calendar months, valuation_date]`, using actual payment dates and verified share adjustments. Include multiple ordinary installments once; exclude exceptional distributions. A yield above 12% triggers an advisory review guard even though numerical yield points remain capped. Cash-flow coverage is not claimed by an earnings-payout score.

## 5. Objective Ratings And Advice

Retain overall `G`, `D`, or `(G + D) / 2` for growth, dividend and balanced objectives respectively. Do not require an unused component merely to calculate a single-objective rating. Guards may need independent financial inputs even when that component is unused; display the distinction.

Use unrounded overall scores: >=70 is a research candidate, >=50 and <70 is watchlist, and <50 is low score for this objective. Display one decimal place; rounding never changes eligibility. Sort eligible candidates by unrounded overall then symbol for stable ties; keep guarded/unavailable names visible in separate states, not silently dropped. These are Long-Term research labels, not Swing Buy/Keep/Sell or real-portfolio liquidation instructions. State an indicative 3-5 year capital-growth horizon and annual-income monitoring horizon; neither guarantees outcomes.

### Advisory Guards

Evaluate each guard as pass, fail or unknown. Any fail yields `review_required` with all established reasons; if no fail but a required guard or the required objective score is unavailable, yield `insufficient_evidence`. Only an assessable score with all applicable guards passing can receive candidate/watchlist/low-score advice. A high numerical score cannot override a guard. Retain assessable scores and evidence even when advice is blocked.

Common guards for all objectives:

- Latest ordinary-owner net income and equity must both be positive. Confirmed loss/break-even or nonpositive equity is review-required, not hidden by averaging.
- Latest required financial report/solvency input must be no more than 18 calendar months old measured from its period-end, and known to the platform as of the analysis time. Exactly 18 months passes. An interim update does not silently replace required annual history.
- Valuation price must be a positive actual traded close no more than five exchange sessions old (age 0 through 5 passes); a carried reference close is not a fresh trade. Show last-trade age, trading frequency and turnover basis. The Swing 5m/18-of-20 filter is not automatically a Long-Term suitability threshold.
- Financial institutions must have assessable capital coverage `K >= 1`; below 1 is review-required. Non-financial companies must have assessable ND/E <=1 and CR >=1 under the above denominator policies; nonpositive equity fails independently. These are conservative product guards, not legal distress definitions.
- Confirmed suspension, default, going-concern warning or regulatory capital breach requires review. Absence of such a flag is not certified absence of risk; disclose that V1 does not offer comprehensive event surveillance. Unresolved comparable share basis/category/input conflicts block dependent advice.

Additional guards for dividend and balanced objectives:

- Latest complete fiscal-year ordinary distribution and trailing-12-month ordinary distribution must both be positive.
- Latest total ordinary payout must not exceed latest positive matching earnings, and three-year aggregate ordinary payouts must not exceed aggregate earnings; nonpositive aggregate earnings fails. Equality passes. These use the same three matched fiscal years as coverage points.
- Historical ordinary yield must be <=12%; above this level requires yield-trap review, not an assertion that a cut is certain.

All outputs include objective, horizon, score/contributions or unavailable reasons, dated evidence, major observed risks, triggered guards and monitoring conditions. Re-evaluate on a new published financial/dividend input and daily price batch. Do not create an extra confidence percentage: use factual calculation status (`assessable`, `warming_up`, `missing_inputs`, `unsupported_basis`) and dated freshness/basis fields. Swing signal strength is not confidence in profit; Long-Term rating is not a probability. Stale inputs can have assessable historical metrics while failing current-advice freshness guards.

## 6. Swing Calculation Conventions

### 6.1 Session Grid And Non-Trading Observations

- Use the authoritative exchange-session grid, no weekend/holiday rows. Distinguish confirmed trade, confirmed no trade/suspension, and unknown observation. Never infer no trading solely from a missing row or a carried price. Keep source OHLC separate from calculation inputs.
- For a confirmed trade, require a valid dated close; ATR also requires genuine same-session high/low and preceding analytical close on a comparable price basis. Verify `low <= close <= high` and positive prices. Missing high/low on a traded session is unavailable ATR, never replaced with close.
- For a confirmed no-trade session with a valid prior analytical close, carry that close for EMA/RSI and use zero close change. For session-grid ATR only, explicitly assign `TR = 0` as a no-observed-trading-range convention. This is a modeled analytical input, not observed OHLC: never manufacture a candle or call it exchange-reported high/low. Record `confirmed_no_trade` and `modeled_zero_range`; expose counts and the convention in ATR explanations. The next traded session's range includes the gap from the carried close.
- This session-based convention keeps periods in exchange sessions and can lower ATR during inactivity; it does not measure latent volatility or execution risk. If no-trade status or prior close is unknown, do not apply it. The liquidity filter, positive ATR requirement and new current-session trade guard below prevent treating inactivity as an actionable low-risk signal. Compare this convention's effects in historical evaluation.
- Unknown close or an unresolved price-basis event breaks the EMA/RSI chain; unknown true range breaks ATR independently. Do not compress time, freeze the recursive state through an unknown observation or silently forward-fill it. Backfill/recompute from a preceding valid checkpoint, or start a new segment and complete warm-up before dependent scoring. Known no-trade sessions do not break the chain under the explicit model above.

### 6.2 Seeds And Recursion

Number each uninterrupted input segment's closes from 1. Retain anchor date and input/config version.

| Indicator | Initialization | Subsequent recurrence |
|-----------|----------------|-----------------------|
| EMA N, N=20 or 50 | Arithmetic mean of first N analytical closes, published at close N | `EMA[t] = (2/(N+1))*close[t] + (1-2/(N+1))*EMA[t-1]` |
| Wilder RSI14 | First 14 close changes require 15 closes. Seed mean positive gains and mean absolute negative losses at close 15 | Each average becomes `(13*previous_average + current_gain_or_loss)/14`; RSI=`100 - 100/(1 + avg_gain/avg_loss)` |
| Wilder ATR14 | First 14 valid session TR inputs each need a previous analytical close, so normally close 15 | `ATR[t] = (13*ATR[t-1] + TR[t])/14` |

RSI boundaries: positive average gain and zero loss ->100; zero gain and positive loss ->0; both zero ->50. This neutral flat-series convention is explicit, not a missing-input fallback. ATR zero is a valid flat-range indicator value but makes the approved normalized Swing score unavailable. Internal SMA seeding is not an added user-facing indicator.

### 6.3 Warm-Up, Price Basis And Publication

- Allow indicator chart values after their defined seeds, tagged warming-up until each required chain has 250 uninterrupted exchange-session closes including the current session (249 usable changes/TR inputs for RSI/ATR). Actionable scoring requires all required chains mature, current and five-session-old EMA values present, and the complete liquidity window. 250 is a conservative numerical initialization policy, not 250 traded sessions or a guarantee of predictive reliability. A stock with shorter history remains visible without actionable scoring.
- Once initialized, continue from the versioned checkpoint/anchor. Do not reseed on a moving 250-row window each day. Corrections rebuild affected series from an earlier valid checkpoint into a new batch; prior published results and accepted paper-order references remain immutable.
- Normalize verified splits/bonus share events consistently across historical indicator OHLC and volume, retaining original exchange observations and point-in-time adjustment provenance. Do not dividend-adjust the V1 technical series into total-return prices. Raw cash-dividend price gaps may affect indicators and must be explained. Unknown/complex rights or other price-basis events block affected advice until a supported comparable basis is available. Indicator adjustments never silently rewrite paper positions or their entry references; unresolved paper corporate actions require separate handling under the accounting contract before advice resumes.
- Use unrounded indicator values through scoring and guard evaluation. Round only display values. Calculations use float64 or more accurate deterministic arithmetic; cross-engine fixture tolerance is `abs(a-b) <= 1e-8 * max(1, abs(a), abs(b))`, with exact agreement on action/guard labels required separately. Boundary comparisons use canonical unrounded engine output; tolerance never promotes eligibility.

### 6.4 Traded Value And Current-Session Eligibility

- Primary liquidity basis is source-reported actual XOF turnover. For the full 20-session window, require 20 known values, including confirmed zero-trade zeros. If actual turnover is incomplete but each traded session has valid raw close and share volume, use `raw_close * raw_volume` for ALL traded rows in that window and zero for confirmed no-trade rows. Label the entire window estimated, never mix actual and estimated rows into an unlabeled median.
- Use original same-session close/volume units for turnover, not adjusted historical price times unadjusted volume. Reject negative turnover/volume and inconsistent actual-positive turnover with zero trading evidence. Price-times-volume is an approximation, not a lower bound on turnover; show that limitation with estimated-basis recommendations.
- For 20 sorted values, median is the average of positions 10 and 11. Count confirmed sessions with trades, not sessions whose estimate merely rounds above zero. If neither complete basis is available, liquidity eligibility is unknown and Buy is unavailable.
- Preserve median >=5,000,000 XOF and >=18 traded sessions out of 20, plus existing score >=70 and structural guards. Add a current-session guard: Buy also requires a confirmed trade with a genuine current-session close and no active suspension. This is an explicit additional eligibility guard, not a change to score weights or the 18/20 rule. Publish any assessable score with no-current-trade rejection reason; it is not automatically Sell.
- Paper exits remain independent: missing/unknown prices do not imply Keep; established duration or other assessable exit triggers still generate Sell advice under the existing partial-availability contract. Do not use a synthetic carried close to claim a fresh price-trigger crossing or a new high-water price. A paper execution still requires the genuine intended-session execution close under its existing grace/expiry rules, not an analytical carried close.

## 7. Delivery Dependencies And Verification

No new data-quality feature is added. Implement these input contracts and failure states as tested financial logic within the existing ingestion and Analysis Engine boundaries. The current five-field financial extractor does NOT establish support for matched ordinary-owner figures, opening equity, current assets/liabilities, unrestricted cash, outstanding shares, complete fiscal dividend installments, premium histories or regulatory coverage/requirements. Extend existing adapters with source evidence; unsupported company scores remain unavailable. This is a material coverage dependency, especially for financial institutions, not a reason to invent proxy capital ratios.

Required calculation fixtures:

- Growth maxima sum to 100 (30+25+20+25); Dividend maxima sum to 100 (25+15+40+20). Objective changes never change G or D. Missing unused D does not block a G rating, but missing a required common guard can block advice.
- At 15% latest/five-year ROE and five profitable years, profitability earns 25; latest/five-year ROE of 7.5% and four profitable years earns 7.5+8=15.5. Nonpositive versus unknown equity yields explicit zero-factor policy versus unavailability.
- Non-financial ND/E=0.5, CR=1.5 ->6+4=10; financial K=1.25 ->10. Verify exact boundaries, zero current liabilities and missing/invalid regulatory requirements.
- Net income/M=5%, PB=2 with positive income/equity ->7.5+5=12.5 valuation points. Negative income cannot earn cheap-book points.
- Five positive equal ordinary DPS values ->regularity25, maintenance10, growth0. All five confirmed zeros and zero trailing ordinary payments ->D=0 when all required financial, price and share inputs are known; missing histories remain unavailable.
- Annual payout factors at positive payouts/earnings of 0.8, 1.0 and 1.2 ->1, 0.5 and 0; no distribution or nonpositive earnings ->0. Yield4% ->10 points; >12% retains capped numerical contribution but triggers review.
- Score 69.96 displays70.0 but stays watchlist; exact70 can be a candidate only if every guard passes. Test equality at all age, payout, liquidity and capital boundaries; unknown guards, confirmed breaches and score unavailability have distinct outcomes.
- EMA seeds, RSI 100/0/50 limits, ATR gaps, close250 versus249, known no-trade zero-range modeling versus missing OHLC on a traded day, interruption/recovery, checkpoint replay, actual/estimated window selection, median ties and fresh-trade guard.
- Test price/share corporate-action compatibility, fiscal-year versus payment-date matching, incomplete dividends, point-in-time publication and immutable historical versions.

Unit/contract tests establish calculation behavior only. Before actionable pilot publication, evaluate sector score distributions and coverage, denominator extremes, historical holdout behavior with publication lags, corporate actions, fees, liquidity and manual execution constraints. Report unavailable-company counts and concentration alongside results; do not quietly tune weights to the same holdout. Until evaluation is reviewed, outputs remain explicitly experimental research/paper-trading signals, not validated investment advice.

## 8. Financial References

- [Fidelity: EMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema): recursive weighting and arithmetic-mean initialization. The 250-session warm-up is our design convention.
- [Fidelity: RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI): relative average gains/losses and momentum interpretation. Flat-series and missing-session behaviors are explicit product conventions.
- [Fidelity: ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr): true range, gap handling and Wilder recurrence. Modeled zero range for a verified no-trade session is a disclosed extension, not reported OHLC or a claim sourced to Fidelity.
- [CFA Institute: Financial Analysis Techniques](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques): contextual use of profitability, liquidity, solvency and valuation ratios, not endorsement of these score bands.
- [CFA Institute: Analysis of Financial Institutions](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/analysis-of-financial-institutions): distinct bank/insurer capital, liquidity and risk analysis; capital coverage alone is incomplete.
- [CFA Institute: Analyzing Income Statements](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/analyzing-income-statements): revenue/earnings interpretation, per-share claims and non-recurring items.

References support financial concepts. They do not validate our 15% ROE, yield/payout bands, score thresholds, regulatory scoring buffer, freshness limits or strategy performance.
