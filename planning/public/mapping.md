<!-- Public derivative: operational identifiers and private inventory excluded. Normative behavior unchanged. -->

# Tradvisor V1 - Source-To-Calculation Mapping

**Version:** 0.5
**Date:** 2026-09-20
**Status:** PROPOSAL - evidence-based implementation mapping; not production coverage certification
**References:** BRD v1.23 (companion baseline document), Architecture v1.0 (companion baseline document), API/data contract v0.13 (companion baseline document), Financial contract v1.1 (companion baseline document)

## 1. Scope And Findings

Map the five user-supplied tables to the approved Swing, paper-trading, Growth and dividend-research requirements. This document identifies fields to reuse, transformations to implement, meanings to confirm and unavailable inputs. It does not change calculation rules, lower history requirements, authorize production queries or introduce a data-quality service. Swing and Long-Term remain equal first-class V1 workflows; ordering the mapping by dependencies does not change their priority.

- The supplied `shares` schema contains the basic OHLC and volume inputs. The stakeholder confirms that `date` is intended as the trading date and `volume` counts individual shares traded. Targeted inspection shows the scraper assigns the runtime's current date rather than extracting/verifying the source session. Historical date correctness, zero-volume/trade-status semantics and sufficient uninterrupted history remain unconfirmed. The low-volume sample cannot certify actionable Swing coverage.
- The supplied `financials` schema contains useful reported figures, but does not establish all required Growth inputs or five consecutive comparable years. Publish supported metrics separately; never reweight a partial score into a full score.
- One year of dividend records supports dated research facts once their meaning is established. It does not establish complete trailing-12-month ordinary yield, multiyear consistency or sustainability. Full Dividend/Balanced scoring remains deferred beyond V1; acquiring older dividend years is not a release prerequisite.
- Paper holdings, cash, fees, orders and exit state are new application-owned data, not missing columns to add to the market-price table. Reset/recovery state stays under the approved application contracts.

## 2. Evidence And Status Convention

Private source samples and schema metadata informed this mapping but are not reproduced
or linked publicly. They do not certify full history, source semantics or usable coverage.
The intended price date is the trading date and volume counts individual shares. Source
session attribution and zero-volume price meaning still require adapter verification.
Financial scope, units, owner attribution and required additional fields remain unverified.
A missing fiscal year must remain missing; only one dividend year is currently available.

Available means a field is present, not semantically verified. Confirm means evidence is
needed. Derive means deterministic computation after prerequisites. Add means normalized
metadata/state is needed. Unavailable means not evidenced. Deferred means outside V1.

Preserve supported facts and metrics. Publish complete Growth scores only with all
required inputs; never reweight partial totals or invent missing history. Report company
and sector coverage and blocking inputs for product-owner acceptance before launch.
Insufficient coverage requires explicit scope review, not a silent formula change.


## 3. Source Fields And Meaning

### 3.1 Company Reference

| Source field | Target/use | Status and required treatment |
|--------------|------------|-------------------------------|
| `brvm_companies.symbol` (STRING) | Catalog symbol, joins to observations | Available / Confirm: stable issuer/share-class identity and symbol validity dates. Do not join by company name or assume symbol never changes. |
| `brvm_companies.name` (STRING) | Display name | Available: catalog is the proposed display authority; preserve source names as evidence. |
| `brvm_companies.sector` (STRING) | Sector display/filter; input to category mapping | Available / Confirm: taxonomy, origin and updates. Sector alone is not a verified bank/insurer/non-financial classification. |
| `brvm_companies.activity_description` (STRING) | Business description and category review | Available / Confirm: use with issuer evidence, not name-based guessing. |
| No supplied issuer/class/effective-date fields | Historical identity and calculation category | Add verified mapping with source, validity dates and supported category. Unsupported/mixed entities retain facts without an invented industrial score. |

### 3.2 Shares

| Source field | Target/use and units | Status and required treatment |
|--------------|----------------------|-------------------------------|
| `shares.symbol` (STRING), `name` (STRING) | Join to catalog; source display evidence | Available / Confirm: resolve issuer and share class; names are not join keys. |
| `shares.date` (DATE) | Actual exchange session date | Available / intended meaning confirmed by stakeholder. Current scraper uses runtime `datetime.now()` at line 54; source-session attribution and historical correctness remain unverified. Preserve original labels, add verified source-session mapping and separate collection time. |
| `shares.open` (FLOAT64) | Raw opening price, XOF/share; chart | Available / Confirm: genuine session observation and source precision. Missing open blocks a complete raw candle, not necessarily close-based EMA/RSI. |
| `shares.high`, `shares.low` (FLOAT64) | Raw session range, XOF/share; ATR/chart | Available / Confirm: genuine high/low on the same session and price basis. Never replace missing traded-session high/low with close. |
| `shares.close` (FLOAT64) | Raw closing price, XOF/share; indicators, valuation, execution | Available / Confirm: genuine intended-session close versus carried reference, revision identity and precision. |
| `shares.volume` (FLOAT64) | Individual shares traded in the session | Available / unit confirmed by stakeholder on 2026-09-20: individual shares, not lots or XOF turnover. Validate nonnegative whole-share values during normalization. This confirms the volume unit used by the approved close-times-volume estimate, not complete liquidity-window coverage. Zero-volume OHLC meaning and source no-trade/suspension status remain unconfirmed. |
| No supplied turnover field | Actual traded value, XOF/session | Unavailable in supplied schema. Use the approved complete-window close-times-volume estimate when its prerequisites hold; do not require actual turnover acquisition for that fallback. |
| No supplied trade-status/suspension fields | `traded`, `confirmed_no_trade`, `unknown`; current suspension evidence | Add from verified source semantics/evidence. Missing row is unknown, not zero volume or a closed exchange. |
| No supplied collection/availability/revision fields | `collected_at`, `validated_available_at`, source revision and evidence | Add prospectively. Availability is first committed usable time for that revision, stable across retries. Do not fabricate historical platform-availability timestamps. |
| No supplied adjustment/event fields | Comparable indicator series and paper-event handling | Unavailable: verified split/bonus factors and relevant price/share-basis events. Unresolved events block affected advice; adjustment factors never silently rewrite paper positions. |

Source FLOAT64 columns do not establish exact money. Preserve source values and obtain verifiable decimal/precision semantics before execution normalization. Normalized monetary fields must satisfy the API contract; do not round unsupported execution-price precision merely to fit it. Technical indicators follow the financial contract's deterministic numerical convention, not the paper-ledger money representation.

### 3.3 Financials

| Source field | Target/use | Status and required treatment |
|--------------|------------|-------------------------------|
| `symbol` (STRING) | Matching ordinary issuer claim | Available / Confirm: entity/share-class mapping and consolidated versus standalone scope. |
| `fiscal_year` (INT64) | Annual period identifier | Available / Add: actual period start/end and full-year status. Do not assume every issuer closes on December 31 or use year alone for freshness. |
| `revenue` (FLOAT64) | Non-financial activity series | Available / Confirm: reported revenue, currency/scale and comparable scope. Do not relabel it as bank PNB or insurance premiums without source evidence. |
| `net_income` (FLOAT64) | Ordinary-owner earnings, growth, ROE, valuation | Available / Confirm: attribution to ordinary owners and preferred/noncontrolling interests where applicable. A valid reported loss is not missing data. |
| `total_equity` (FLOAT64) | Matched attributable equity, average equity, valuation | Available / Confirm: same claim/scope as earnings and capitalization. Opening balance for the oldest ROE year is not established. |
| `total_debt` (FLOAT64) | Non-financial interest-bearing debt | Available / Confirm: supplied description ambiguously includes total liabilities. Do not treat total liabilities as interest-bearing debt. |
| `cash_and_cash_equivalents` (FLOAT64) | Non-financial unrestricted cash | Available / Confirm: restrictions, scope, period and units. |
| `collected_at` (TIMESTAMP) | Collection evidence | Available: not an issuer publication timestamp. Sample August 2026 collection does not prove when reports became publicly available. |
| `document_link` (STRING) | Source-report navigation/evidence retrieval | Available / Confirm: sample URLs are article/detail links, not verified direct PDFs. Do not infer publication dates from URL text. Resolve original report and immutable evidence during integration. |
| No supplied currency/scale/scope/publication/revision fields | Comparable annual inputs and point-in-time evidence | Add source-backed metadata, retaining original units and restatements. Unknown publication timing limits historical evaluation. |
| No supplied current assets/current liabilities | Non-financial current ratio | Unavailable; cannot derive from debt, cash and equity alone. |
| No supplied PNB/premiums/capital-coverage requirements | Bank/insurer activity and resilience | Unavailable until source-backed sector extraction is added. Ratings do not replace these inputs. |
| No supplied ordinary shares or matched issuer market cap | Earnings/book valuation | Unavailable. Do not substitute free float, trading volume or weighted-average EPS shares. |

### 3.4 Dividends And Ratings

| Source field | Target/use | Status and required treatment |
|--------------|------------|-------------------------------|
| `dividends.symbol` (STRING) | Issuer/share class | Available / Confirm: identity compatible with the quoted share and any adjustment factors. |
| `dividends.dividend` (FLOAT64) | Reported payment amount | Available / Confirm: gross versus net, per-share versus total, ordinary versus exceptional, currency/scale. Until resolved, show only accurately labeled source facts; no numeric yield derived from ambiguous amounts. |
| `dividends.payment_date` (DATE) | Actual cash-payment date | Available / Confirm: paid versus scheduled/declared date. Trailing yield uses actual payments, not fiscal-year labels. |
| `dividends.fiscal_year` (INT64) | Source fiscal attribution | Available / Confirm: preserve explicit attribution; never infer payment year minus one. |
| No supplied payment ID/status/coverage/source fields | Deduplicated installments, payment evidence and coverage interval | Add source-backed identity/status/provenance; confirm coverage. Symbol/year alone cannot distinguish installments. Missing payment records are not confirmed zero dividends. |
| `ratings.symbol` (STRING), `rating_year` (INT64) | Rating subject and coarse period | Available / Confirm: issuer versus instrument; actual effective/publication dates required for ordered changes. |
| `ratings.rating_short_term`, `rating_long_term` (STRING) | Original rating display | Available / Confirm: agency, scale and outlook/watch distinctions. Do not compare unlike scales or short-term to long-term labels. |
| `ratings.collected_at` (TIMESTAMP) | Collection evidence | Available: not effective date or evidence of the historical publication date. |
| No supplied agency/scale/source/effective-date fields | Interpretable downgrade context | Add when evidence exists; otherwise display original dated labels without declaring an ordinal downgrade. No numerical Growth contribution is introduced. |

## 4. Swing And Paper Calculation Mapping

Stable mapping IDs below identify dependencies, not new BRD requirement IDs. The financial contract remains authoritative for formulas and boundary cases.

| ID | Result | Inputs and transformation | Availability and missing-input behavior |
|----|--------|---------------------------|-----------------------------------------|
| SW-01 | Session grid | Approved BRVM holiday/schedule sources plus verified exceptions; ordered exchange sessions and versioned completion times | Add. Current-year holidays alone do not certify historical sessions. Unknown calendar coverage blocks dependent timing/counts. |
| SW-02 | EMA20 / EMA50 | Confirmed comparable close series; SMA seed then approved recursive EMA; continue versioned checkpoints | Derive after SW-01 and price semantics. Known no-trade analytical carry is explicit; unknown close breaks the chain. Seeded chart values may appear before mature scoring. |
| SW-03 | RSI14 | Same analytical closes; 14 changes/15 closes for Wilder seed, then recursive gains/losses | Derive. Apply approved 100/0/50 boundaries; unknown close breaks the chain. |
| SW-04 | ATR14 | Genuine traded-session high/low, previous analytical close and verified comparable basis; Wilder true-range smoothing | Derive. Confirmed no-trade modeled TR=0 is labeled, never a fabricated candle. Unknown true range breaks ATR independently. ATR=0 is an indicator value but cannot support normalized scoring. |
| SW-05 | 20-session traded value and frequency | Prefer 20 known actual XOF turnover values; otherwise raw close times raw share volume for the entire window, confirmed no-trade zeros only; median and confirmed-trade count | Derive / Confirm. No mixed actual/estimated basis. Missing status or incomplete window makes liquidity eligibility unknown. Approved boundaries: median >=5m XOF and >=18/20 traded sessions. |
| SW-06 | Swing strength and Buy eligibility | SW-02..05; all required chains mature for 250 uninterrupted exchange-session closes; current and five-session-old EMA; genuine current trade, suspension and structural guards | Derive, not demonstrated by sample. Use approved score and >=70 threshold unchanged. Show assessable score even when a guard fails; missing core inputs means unavailable score. Failure to qualify for Buy is not Sell. |
| PT-01 | Order execution timing/price | SW-01; genuine raw intended-session close and immutable revision/availability timestamp; acceptance time, original deadline and frozen fee | Add / Derive. No carried or adjusted indicator close used as an execution price. Timely data may be processed later; late data expires the order under the existing grace rule. No backdated availability for imported history. |
| PT-02 | Keep/Sell and exit explanations | Application position cost/quantity, opening session, highest genuine close since opening, latched activation, frozen policy; EMA/RSI and genuine current price | Add application state / Derive. Additional buys/partial sells follow approved state rules. Independently assessable exits such as duration can yield Sell despite missing price checks; incomplete checks cannot default to Keep. |
| PT-03 | Cash, P&L and reservations | Application opening cash, explicit fee, accepted orders, actual executions and cash movements; latest valid valuation close | Add application-owned ledger/state. No market table contains these records. Incomplete valuation stays explicitly incomplete, not zero; exact money and proportional fee/cost rules unchanged. |


## 5. Long-Term Calculation Mapping

| ID | Result | Inputs and transformation | Availability and missing-input behavior |
|----|--------|---------------------------|-----------------------------------------|
| LT-01 | Comparable history | Five consecutive completed annual periods with matched currency, scope, category and publication evidence; six equity dates for five average-equity denominators | Confirm / Add. Private samples do not certify five consecutive years. No interpolation or using four observations as five years. Full-source coverage remains unconfirmed. |
| LT-02 | Activity/earnings growth, 30 points | Verified revenue/PNB/premiums by category and ordinary-owner earnings; approved three-year endpoint CAGR and loss/recovery handling | Derive after semantic confirmation. Supported standalone endpoint metrics can be shown with their periods and limitations; they do not certify complete history or a full score. |
| LT-03 | Profitability/consistency, 25 points | Latest and five-year ROE using average opening/closing matched equity; five-year positive earnings count | Derive only with LT-01 and matched income/equity. Missing opening equity is not replaced by closing equity; distinguish observed nonpositive equity from unavailable equity. |
| LT-04 | Non-financial resilience, 20 points | Interest-bearing debt minus unrestricted cash over matched equity; current assets/current liabilities | Partial candidate inputs available, semantics unconfirmed; current assets/liabilities unavailable. An assessable debt metric does not fill the missing current-ratio contribution. |
| LT-05 | Bank/insurer resilience, 20 points | Banks: minimum matched disclosed-to-required coverage across applicable constraints. Insurers: eligible-to-required solvency capital | Unavailable in supplied schemas. Source dates, jurisdiction/scope and applicable requirements must be evidenced; do not invent a common regulatory minimum or proxy with industrial debt. |
| LT-06 | Valuation, 25 points | Positive genuine close and matching ordinary shares excluding treasury, or verified aggregate ordinary market cap; latest matching earnings/equity | Capitalization inputs unavailable. Price, equity and earnings alone cannot supply market cap. Multiclass issuers need a verified matching aggregate claim. |
| LT-07 | Growth score and advisory state | LT-02..06 applicable to category; full required history; guard facts, report period-end <=18 months, actual last-trade age <=5 sessions, suspension and observed risk evidence | Full score not established from supplied material. Publish supported dimensions separately, no weight redistribution. Apply known-fail versus unknown guard behavior from financial contract; stale metrics may remain readable without eligible current advice. |
| LT-08 | Dividend research facts | Reported payment records with confirmed units/basis, actual dates, attribution, ordinary/exceptional status and coverage description | Available fields / Confirm. Display dated supported facts for the available year. Unknown years are neither zeros nor evidence of inconsistency. No dividend-history backfill requirement. |
| LT-09 | Historical ordinary cash yield | Gross ordinary paid DPS summed once in `(valuation date minus 12 calendar months, valuation date]`, verified complete coverage and matching share basis, divided by valid compatible close | Conditional Derive. One stored year does not prove this window is complete. Unknown paid/gross/DPS/type/coverage/basis means yield unavailable, not a substitute score. |
| LT-10 | Rating and observed risk context | Comparable agency/scale/subject/effective dates and original labels; source-backed suspension/default/going-concern observations | Confirm / Add where available. No broad event-surveillance service added; absent flags are not certified absence of risk. Uninterpretable ratings remain original labels. |
| LT-11 | Dividend/Balanced scores, rankings and score-based recommendations | Earlier five-year dividend formulas | Deferred. Emit explicit deferred states, no numeric substitute or automatic activation when more records arrive. |

## 6. Integration And Join Rules

Use separate normalized logical entities for company identity, sessions, price revisions, annual financial revisions, capital/share basis, dividend events/coverage and rating history. These are datasets within existing components, not new services or a commitment to a specific physical table/view layout.

| Rule | Required behavior |
|------|-------------------|
| Time-aware financial selection | Select the applicable complete report known at analysis time, retaining fiscal period and publication/availability evidence. Never join annual results to daily prices merely by matching calendar year. Unknown publication evidence limits historical claims. |
| Different data grains | Keep prices at symbol/session/revision, financials at issuer/period/scope/revision, dividends at payment identity, ratings at subject/agency/scale/effective revision. Aggregate/select each grain deliberately before joining to avoid multiplying observations. |
| Revisions | Preserve originals and select a deterministic evidenced revision. Corrections create new analytical batches; do not rewrite published recommendations or accepted order references. Corrected execution-price selection follows the approved integration baseline and API/data contract. |
| Units and claim | Normalize currency/scale while retaining source units. Match issuer, share class, scope and period; never infer financial units from magnitude alone. |
| Zero versus absence | Only verified no-trade or no-payment evidence can supply a meaningful zero. Unknown is unavailable, not a carry, a zero or permission to skip a session. |
| Application ownership | User settings, portfolios and command/recovery records are backend-owned. Analytical ingestion does not directly manufacture executions, reset generations or user balances. |

The embedded join SQL in the supplied transcript is not an implementation baseline: calendar-year matching risks look-ahead and multirow events can multiply daily rows. This mapping replaces that suggestion without executing it.

## 7. Ingestion Worklist

These are proposed work items, not created issues or completed implementation. Ordering reflects dependencies; Swing and Long-Term adapters can proceed in parallel once their input contracts are established.

| ID | Work and reuse | Output / completion evidence | Dependency | Owner |
|----|----------------|------------------------------|------------|-------|
| MAP-01 | Document existing source meanings and revision keys using supplied metadata and source evidence | Mapping confirmations for dates, amounts, scope and identity; unresolved fields explicitly unavailable | Section 8 responses/evidence | Data owner with ingestion implementer |
| MAP-02 | Extend existing company-reference ingestion/mapping | Verified issuer/share-class/sector/category validity with provenance, including unsupported categories | MAP-01 | Ingestion |
| MAP-03 | Add approved calendar ingestion and manual exception input to existing pipeline | Versioned session grid, historical coverage statement, completion-time convention and correction handling | Official calendar/schedule evidence; operator assignment | Ingestion / Pipeline Orchestration |
| MAP-04 | Extend shares normalization without changing source evidence | Genuine versus carried status, units, original session, revision, collection/availability timestamps; exact execution-price representation | MAP-01..03 | Ingestion / Analytical Data |
| MAP-05 | Implement daily Swing derivations and versioned checkpoints | SW-02..06 fixtures, 250-session coverage outcomes, whole-window turnover basis and explicit unavailable results | MAP-03..04; verified comparable price basis | Analysis Engine |
| MAP-06 | Extend annual financial extraction and period metadata | Matched ordinary-owner fields, six equity dates, non-financial current assets/liabilities, bank/insurer activity and capital evidence where obtainable | MAP-01..02; source reports | Ingestion |
| MAP-07 | Acquire/normalize capitalization and corporate-action evidence | Matching dated ordinary shares/capitalization and verified adjustment factors, or explicit unsupported status | MAP-02; source evidence not yet identified | Ingestion / Analytical Data |
| MAP-08 | Normalize existing dividend year and rating history | Stable payment identities, confirmed amount/payment semantics and coverage; rating agency/scale/dates where available | MAP-01..02 | Ingestion |
| MAP-09 | Implement Growth dimensions, guards and dividend facts | LT-01..10 coverage per issuer; supported metrics preserved, incomplete totals unavailable; LT-11 deferred | MAP-04,06..08 | Analysis Engine |
| MAP-10 | Integrate market results with paper-state calculations | Genuine next-session execution, frozen fee/policy, independent holding advice and retry-stable availability fixtures | MAP-03..05; application contracts | Paper Trading / Application Store |

Do not open a V1 task to acquire five years of dividends or fabricate missing 2024 financials. Additional actual-turnover ingestion is optional while the approved estimated-window method is usable. Missing mandatory Growth inputs remain visible implementation dependencies, not reasons to remove the Long-Term workspace.

## 8. Grouped Confirmation Questions

These questions concern unconfirmed source meanings, not decisions already approved. Lack of an answer does not block implementing explicit unavailable states or fixture-based interfaces.

| ID | Question and why it matters | Conservative treatment until answered | Validation owner |
|----|----------------------------|--------------------------------------|------------------|
| Q-SRC-01 | Partially resolved: `date` is intended to mean trading date, but the scraper assigns runtime date; `volume` is confirmed as individual shares traded. On 2026-09-20 the stakeholder stated they do not know whether zero-volume OHLC are carried prices. Transfer that question to implementation source verification, not another stakeholder decision. Export filter and verified source-session attribution remain unconfirmed. | Treat the private share sample as a non-certifying sample. Until source evidence resolves zero-volume observations, classify their trade/price status as unknown: no fresh traded close, paper execution, confirmed no-trade carry or modeled zero TR may be inferred from them alone. Apply the existing unknown-input behavior to affected calculations. Do not re-ask the intended date meaning, volume unit or unknown zero-volume convention, or assume historical dates are proven wrong. | Ingestion implementer; source evidence reviewed by financial-domain reviewer |
| Q-SRC-02 | Implementation verification: establish financial currency/scale/scope and debt/cash/owner attribution, plus dividend per-share/total, gross/net and actual-paid meaning from source evidence. Identify company categories, shares/capitalization and report dates rather than assuming those fields exist. The approved coverage policy does not require the stakeholder to confirm accounting semantics from memory. | Preserve supported metrics/facts; dependent normalized metrics, yields, full scores and advice remain unavailable wherever a required meaning/input is unresolved. Review measured coverage before launch; do not silently weaken the scorecard. | Ingestion implementer with financial-domain reviewer; product owner reviews launch coverage |

The existing uncertainty about A potentially missing fiscal year remains recorded; it is not being asked again. Additional dividend years are known unavailable and are not requested. Source facts may be settled by documentation or future adapter tests rather than requiring the stakeholder to know every accounting field.

Zero-volume verification belongs to MAP-04: compare original source records and available dated exchange documentation to establish what the displayed OHLC represent, then encode evidenced behavior in adapter fixtures. Repeated equal prices alone do not prove carry-forward. This is a bounded ingestion verification task, not a new data-quality feature. Until resolved, retain source values with unknown status and withhold only dependent outputs; independently assessable holding-duration exits remain governed by the financial contract.

## 9. Verification And Handoff

Implement these checks in ordinary unit/contract/integration tests, not a separate data-quality product:

- Calendar gaps, date versus collection time, explicit no-trade versus unknown, zero-volume carried OHLC and price revision selection.
- EMA/RSI/ATR seed and 249/250-session boundaries; independent chain interruption; no invented raw candles; complete actual versus estimated turnover windows.
- Duplicate-key handling without arbitrary averaging, point-in-time joins without annual look-ahead and no price-row multiplication from installments or rating histories.
- Whole-share/price units and supported monetary precision; retry-stable availability; timely-price/late-worker and late-price cases; immutable execution evidence.
- Five consecutive fiscal years and six equity dates; missing 2024 remains unavailable; debt versus liabilities, category-specific activity/capital inputs, matched owner/capitalization basis and period freshness.
- One-year dividend facts versus proven trailing-window completeness; paid versus declared, gross versus net, ordinary versus exceptional and installment deduplication; Dividend/Balanced remain deferred.
- Supported component metrics remain visible when an overall score or advisory state is unavailable. Missing independent evidence must not become a misleading zero or Keep action.

This evidence-based mapping guides adapter tasks under architecture v1.0. It does not certify production coverage or empirical financial effectiveness. Source questions above are implementation verification with conservative unavailable behavior, not unanswered stakeholder architecture choices. The approved recovery lifecycle is specified in the integration/API contracts; measured costs, coverage, named operating ownership and restore verification remain release gates in architecture section 13. Mapping status remains provisional until source evidence is verified.
