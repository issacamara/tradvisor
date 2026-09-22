## Public Baseline: Architecture (2/3)

- Contract tests cover deterministic scoring, interpolation endpoints/interiors, score bounds and contribution totals, unrounded minimum-score boundaries, liquidity gates, structural guard boundaries, missing mandatory inputs, zero/negative ATR, historical version preservation, and strategy changes across publication boundaries. Explicit fixtures reject a flat/falling EMA20 despite a theoretical 20+0+30+30=80 score and an extension >=3 ATR despite a 20+20+30+0=70 score. A score exactly 70 qualifies only when every guard passes. These synthetic boundary fixtures do not establish realizable market performance. This is an extension of the existing Analysis Engine, not a new component.

Indicator references: [EMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema), [RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI), and [ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr). These explain indicator definitions and limitations; they do not validate a Tradvisor strategy or select its parameters.

### 5.5 Investor Application

- Purpose: serve invited users with separate Swing, Long-Term, and paper-portfolio views.
- New: README confirms the previous Streamlit application was removed.
- Interfaces and ownership: authenticated analysis reads, objective preferences, order submission, and reset requests. The backend determines user identity.
- Technology: confirmed Next.js App Router, React, and TypeScript frontend with static export; FastAPI/Python backend direction. The deployment baseline uses Firebase Hosting for the static frontend and uses request-billed Cloud Run for the API, with zero minimum instances. Firestore is selected; Firebase Authentication is confirmed for email/password sign-in, verified email and password reset with backend-enforced manual allowlist admission. Static export replaces the earlier request-time server-rendering proposal without changing the selected UI libraries.
- Boundary: users cannot select another user's portfolio by changing a request identifier.

#### Confirmed Frontend Stack

| Concern | Selected technology | Responsibility |
|---------|---------------------|----------------|
| Framework | Next.js App Router, React, TypeScript | Routes and interactive client components; confirmed static shell with authenticated API reads |
| Styling and primitives | Tailwind CSS and shadcn/ui | Shared dark-theme tokens, tabs, sheets, badges, forms, dialogs, and tables |
| Tables | TanStack Table v8 | Sorting, filtering, selection, and column state for screeners and paper records |
| Swing charts | TradingView Lightweight Charts | Candlesticks, volume, and display of backend-provided indicator series |
| Research and performance charts | Recharts with shadcn chart components | Score contributions, dividend history, and simulated equity/P&L series |
| Desktop layout | react-resizable-panels through shadcn Resizable | Adjustable list, chart, and detail panes |

Use Recharts directly with shadcn's chart utilities; adding Tremor would introduce another component layer for the same V1 chart needs. These libraries are selected dependencies for a new frontend, not existing repository assets.

#### Rendering and Interaction Boundaries

- Confirmed rendering model: generate a static application shell at build time and use authenticated client requests for live and user-specific data. Do not embed private data at build time. This replaces the earlier request-time Server Component reads; do not use Server Actions or other request-time Next.js server features. Use Client Components for interactive tables, charts, panel resizing, and paper-order forms.
- Keep user-specific routes as static workspaces that load authorized data at runtime. Prebuild known stock-detail paths or use a static detail route with a symbol parameter; do not depend on runtime generation of unknown paths. Verify direct navigation and refresh against the exported files and hosting configuration.
- The static shell is publicly downloadable; invitation-only protection applies to all API data and commands. A client-side login gate is navigation behavior, not an authorization boundary. Live market updates do not require a frontend rebuild.
- Initialize Lightweight Charts in the browser after its container exists; a Client Component declaration alone does not eliminate Next.js prerendering. Isolate browser-only initialization, release chart resources on unmount, and resize charts when their panels change size.
- Lazy-load chart-heavy stock detail where appropriate. Preserve date alignment between candle, volume, and indicator series, and show missing observations without fabricating prices.
- Display the configured EMA as a price overlay, RSI and ATR in appropriately scaled panels, and traded value as an XOF activity series or detail. Include each indicator's value, period, definition, and interpretation; distinguish estimated traded value from source turnover. These are the only V1 core indicator families.
- Keep indicator values, score contributions, fee amounts, cash, and P&L authoritative on the backend. Frontend formatting and chart scaling do not redefine financial calculations.
- Keep shared market results separate from per-user holding advice in both the response contract and UI. Show the analysis date and recommendation evidence in the stock detail.
- After a successful order or reset command, refresh the affected paper state from the backend. Pending orders must never be displayed as completed fills optimistically.
- Keep authenticated user state out of shared caches. The browser must not receive infrastructure credentials or call analytical storage directly.

#### Layout and Accessibility

- Swing desktop view combines a stock table, price/volume chart, and recommendation detail with resizable panes.
- Long-Term view combines objective selection, ranking, and company factor detail using the same table and theme conventions.
- Paper-portfolio view exposes balances, pending orders, positions, and simulated performance without implying real brokerage holdings.
- On narrow screens, use stacked content or tabs instead of requiring side-by-side resizable panes. Set minimum chart dimensions and constrain table overflow within its workspace.
- Preserve keyboard focus through stock selection, drawers, and order confirmation. Expose chart values and factor contributions as readable text or tables, and include explicit recommendation labels rather than relying on color.

#### Compatibility and Verification

Pin TanStack Table to the selected v8 major and implement against its v8 APIs. The current shadcn Data Table guide uses v9 APIs, so generated or copied examples must be adapted rather than assumed compatible. Pin a tested set of Next.js, React, shadcn primitive, Recharts, and resizable-panel dependencies in the lockfile during implementation.

Acceptance checks cover desktop/mobile navigation, keyboard flows, panel/chart resizing, browser-only chart initialization, empty/unavailable results, theme contrast, and pending-order/reset refresh. Add the attribution notice and TradingView link required by Lightweight Charts.

Official references checked during stack selection: [Next.js Server and Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components), [shadcn Data Table](https://ui.shadcn.com/docs/components/data-table), [shadcn Chart](https://ui.shadcn.com/docs/components/chart), [shadcn Resizable](https://ui.shadcn.com/docs/components/aria/resizable), and [Lightweight Charts](https://tradingview.github.io/lightweight-charts/docs).

### 5.6 Paper Trading

- Purpose: accept manual orders, enforce cash and holding limits, execute eligible orders, calculate P&L, and generate personalized holding advice.
- New: the inspected repository contains no retained transactional paper-trading implementation.
- Interfaces and ownership: owns order and execution rules, fee calculations, position state, and reset behavior.
- Technology: a module within the application backend plus a scheduled execution entry point; use database transactions for balance changes.
- Boundary: balanced stop, activated trailing, technical-deterioration and duration conditions create personalized advice only. They never initiate a sell order. Shared technical inputs are produced once by the Analysis Engine; Paper Trading combines them with position state, rather than recalculating indicators per user.

### 5.7 Application Store

- Purpose: persist user admission, preferences, virtual cash, paper orders, executions, and positions.
- New: no inspected implementation supplies the V1 transactional paper ledger. Existing application data is not this ledger and must be preserved; no identity/data migration is implied.
- Interfaces and ownership: owns atomic updates, application-enforced idempotency, simulation generation, per-user data ownership, and rebuildable serving copies of published analysis.
- Technology: confirmed structured transactional model using Firestore Standard in Native mode, the eligible default database, and Python server SDK. This replaces the relational-store proposal; Cloud SQL and database VMs are excluded by the stakeholder. Use multi-document transactions and stable document identities for order/ledger consistency. Do not use SQLAlchemy or Alembic for Firestore; version document schemas and migration routines explicitly.
- State model: keep current cash and per-symbol positions ready to read. Commit execution and cash-movement records alongside those updates for reconciliation; do not reconstruct every interactive response by replaying an event stream. Collection layout and transaction contracts are specified in section 7.
- Constraints: no implicit relational joins or database foreign-key constraints. Enforce references and ownership in backend code. Represent money as documented fixed-point integers, not floating-point values. Deny direct browser database access; the backend enforces invitation and per-user access using its verified identity context.

## 6. Reuse Inventory

Reuse the existing Python source adapters, financial PDF extraction and loading stages,
company discovery/mapping, BigQuery load helpers, Terraform foundation and CI workflow.
These are reuse candidates, not certified live services. Adapt source-specific contracts,
retry-safe loading, immutable evidence and explicit pipeline dependencies.

Detailed environment inventory, state addresses, identities and observed security findings
remain in restricted operator evidence and are intentionally not published here.
Before deployment, verify current ownership and preserve existing development resources.
Production is a read-only functional reference, not a configuration/state/data clone.


## 7. Data Architecture

Source-To-Calculation Mapping v0.5 (companion baseline document) maps the five supplied schemas and two read-only CSV samples to Swing, paper, Growth and dividend-research dependencies. It distinguishes field presence from verified semantics/coverage, identifies derivations and missing inputs, and provides MAP-01 through MAP-10 adapter work with two grouped source-confirmation questions. The source-mapping pass did not query production rows; later environment checks inspected metadata and selected schemas; a targeted scraper read confirmed runtime-date assignment, distinct from the stakeholder's intended trading-date meaning. This is a reviewed-document integration aid, not certification of production coverage or a change to the financial rules.

Analytical data includes source identity, collection time, effective market or fiscal period, source snapshot reference, and revision. Daily results additionally record rule version and analysis batch. Corrections produce a new revision rather than silently changing a published historical recommendation.

Normalize each production adapter into documented BRD-facing contracts. Shares and financials use lowercase names; dividends still emit uppercase fields while their loader expects lowercase names. Inspect actual BigQuery schemas before migration rather than assuming producer and consumer contracts already match.

For each ingestion run, record source, run ID, collection timestamp, covered period, parser version, raw snapshot URI and hash, row count, and load/publication outcome. A committed load is distinct from an attempted scrape. Replay uses the stored source evidence rather than a fresh request to the source website.

Share history is keyed by symbol and trading-session date. Dividend history requires a stable distribution identity that preserves separate installments for the same fiscal year; its exact natural key depends on source evidence. Financials retain source-report revisions alongside the current symbol/year result. Ratings retain observed/effective dates, agency where available, original rating text, and mapped scale instead of relying only on a year for downgrade history.

An extraction artifact records the PDF hash and storage reference, source publication date, extractor/prompt version, actual model identifier, provider response, and accepted normalized fields. The analytical snapshot references this artifact. The reproducibility contract begins with the persisted extraction result: rerunning a probabilistic model is not assumed to reproduce its earlier output. Ingestion must preserve available publication dates to avoid treating later financial information as known at an earlier analysis date.

Application data includes invited-user identity, investment objective, paper-portfolio settings, simulation generation, pending orders, executions, fee amounts, cash movements, and holdings. Store monetary values with exact decimal or fixed-point semantics.

### Structured Firestore Model

The following physical layout implements the confirmed option 2. Field names are engineering defaults, not existing deployed data. API And Data Contract v0.13 (companion baseline document) specifies logical fields and the approved technical baseline for exact-money semantics, resource limits and command behavior; it does not claim these schemas are implemented.

| Document path | Responsibility / principal fields |
|---------------|-----------------------------------|
| `users/{uid}` | Investment objective and preference version; identity comes from verified authentication, never a caller-supplied UID; authoritative allowlist membership is separate and admin-only |
| `paper_portfolios/{uid}` | One portfolio control record per user: active generation, configured fee rate, schema version, update timestamp |
| `paper_portfolios/{uid}/generations/{generation}` | Current summary: starting cash, cash balance, reserved cash, pending-order count, state version, creation timestamp |
| `.../generations/{generation}/positions/{symbol}` | Quantity, reserved sell quantity, remaining gross purchase cost, unallocated purchase fees, opening session, highest valid close since opening and its evaluated-through session |
| `.../generations/{generation}/orders/{order_id}` | Symbol, side, quantity, recommendation and analysis references, accepted timestamp, intended session, grace deadline, fee snapshot, reservation, status, terminal reason |
| `.../generations/{generation}/executions/{order_id}` | At most one full execution per order: price, quantity, gross amount, fee, allocated purchase cost/fees for a sell, net cash effect, intended session, processed timestamp, source revision |
| `.../generations/{generation}/cash_movements/{movement_id}` | Opening balance and trade cash movements; stable IDs, signed amount, execution reference where applicable, timestamp |
| `paper_portfolios/{uid}/command_receipts/{receipt_id}` | Idempotency record scoped to user, command, key, and expected generation; payload fingerprint and minimal committed outcome |
| `analysis_batches/{batch_id}` and bounded child collections | Rebuildable published Swing, Long-Term, and chart-serving records, keyed by symbol and bounded series chunk |
| `publication_state/current` | Active complete analysis batch and publication metadata |

The ellipsis in paths expands to `paper_portfolios/{uid}`. Histories and chart series are separate documents, never indefinitely growing arrays. Per-record schema versions support explicit migrations. Keep operational fields needed for scheduled pending-order selection on the order documents and define only the indexes required by actual queries, including collection-group selection by status and intended session.

Persist money as checked signed 64-bit millionths of XOF, using arbitrary-precision intermediates and rejecting overflow or unsupported source precision. Serialize six-decimal strings plus currency in JSON. Round executed fees once to whole XOF half-up; allocate partial-sale costs/fees half-up to the internal unit, consuming all residuals on final sale. API/data contract section 2 fixes these engineering defaults and limits; generating schemas and boundary tests is implementation work, not an unresolved money-policy choice.

### Confirmed Calculation Rules

- Manual Sell override (approved 2026-09-20): users may sell held shares from Keep as well as Sell advice. Keep requires explicit acknowledgment with the current advice visible. Persist the validated advice action/reference, evaluation session, exit policy and generation/state version plus override evidence at acceptance. Do not change the analytical recommendation. Ownership, available shares, reservations, fees and next-session execution remain mandatory. Already accepted override orders do not depend on a later Sell signal. Missing or stale advice cannot authorize an override.
- Recommendation freshness (approved 2026-09-20): new orders require current advice evaluated for the latest completed authoritative exchange session at acceptance, not simply the latest available batch. Reject stale references with a refresh-and-reconfirm response. Dated results remain readable during source delays, but outdated advice blocks new orders. Already accepted orders retain their original execution and expiry rules through batch or signal changes. Validate personalized Sell/Keep advice against the current position, generation and state; Keep still requires explicit override acknowledgment.

- Starting cash (approved 2026-09-20): prefill 1,000,000 XOF at initial setup; accept whole-XOF amounts from 100,000 to 100,000,000 inclusive at setup or confirmed reset. Validate server-side before any generation/state change; reject fractional and out-of-range amounts without partial writes. Preserve the existing exact-money JSON representation. Store the selected starting cash immutably per generation and initialize cash to that amount. No active-simulation funding/top-up endpoint or preference edit may alter it. These limits do not cap subsequent trading balances. Reset uses the existing idempotency and generation-fencing contract. Test minimum/default/maximum, adjacent invalid bounds, fractional input, mutation attempts, and reset/retry behavior.

- Require explicit nonnegative fee-rate selection at setup; zero is allowed without being silently preselected. Snapshot the rate on order acceptance. For either side, `fee = round_half_up(quantity * closing_price * rate / 100, whole_XOF)`. Charge only on execution. Later fee changes affect new orders, not pending orders or history.
- For a position with quantity `Q`, remaining gross purchase cost `C`, and remaining purchase fees `F`, the gross average entry price is `C / Q` and fee-inclusive basis is `C + F`. Buying `q` at price `p` with fee `f` changes these totals to `Q + q`, `C + q*p`, and `F + f`.
- Selling `q` allocates `C*q/Q` of gross purchase cost and `F*q/Q` of purchase fees. Gross realized P&L is `q*p - allocated_cost`; net realized P&L subtracts the allocated purchase fees and actual sell fee. Subtract the allocated quantities/costs/fees from the position; on the final sale allocate all remaining residuals and clear the position's holding references.
- With a valid valuation price `v`, gross unrealized P&L is `Q*v - C` and net unrealized P&L is `Q*v - C - F`. Do not subtract a hypothetical future sell fee or double-count purchase fees already allocated to closed shares. Mark valuation freshness explicitly when the latest close is unavailable.
- Holding duration begins at the intended execution session of the opening buy and continues through additional buys and partial sells. Stop-loss advice uses `E = C / Q` excluding fees. Trailing-stop advice uses `H`, the highest valid daily close from the opening session onward, without resetting after an additional buy or partial sale. A fully closed then reopened position starts a new period and high-water reference. The balanced V1 exit baseline is approved for evaluation; no alert creates an order.
- Balanced exit contract: at daily close `P`, loss advice triggers at `P <= 0.95 * E`; trailing protection activates when a close reaches `P >= 1.08 * E`, with activated trailing advice at `P <= 0.96 * H`. Technical exit is `(P(t) < EMA20(t) AND P(t-1) < EMA20(t-1) AND RSI14(t) < 45) OR EMA20(t) <= EMA50(t)`. Here `t-1` is the preceding exchange session, not the last available stock observation. Maximum holding duration is 30 exchange sessions. Any established trigger produces Sell with all triggered reasons; technical confirmation does not defer another trigger.
- Holding-advice availability: Keep requires all applicable exit checks to be assessable and none triggered. If no exit can be established but a required check is unavailable, publish unavailable checks instead of Keep. Preserve any independently established Sell reason when another check is unavailable. Buy score below 70, entry overextension, or failed Buy liquidity eligibility alone does not trigger Sell. Do not derive Sell strength by complementing the Buy score.
- Confirmed activation state: persist whether trailing protection has activated and the activation session/evidence. Once active it stays active until full closure or portfolio reset, including after additional buys and partial sells. Before activation, compare each new valid session close with `1.08 * E` for that session; do not apply a revised entry retrospectively to an old high. Preserve `H` independently. An already active position with `H=1,150` retains its 1,104 trailing level when an additional buy raises `E` to 1,100. Session-ordered processing and retries must preserve the activation event, using historical position state rather than a later entry balance.
- Confirmed duration contract: elapsed sessions are the authoritative exchange-session index difference from the intended execution session of the opening buy. Opening session is 0, the next is 1; duration advice applies at each session close with elapsed sessions >=30 while still open. Exchange holidays/weekends are excluded, but stock non-trading and missing prices do not pause the timer. Delayed execution processing does not shift the opening reference. An order manually submitted after the session-30 alert targets session 31's close; this is an advice deadline, not automatic liquidation.
- Confirmed exit-policy versioning: assign an immutable exit-rule/configuration reference when a position opens and retain it through additional buys and partial sells until fully closed. Newly opened positions use the then-active exit policy; do not silently migrate existing positions. Retain evaluators/configurations needed by open positions and historical results, including their indicator definitions/input requirements if future strategies change. Fully closing/reopening establishes fresh policy, activation, high-water and timing state. Portfolio reset remains generation-fenced and clears the prior simulation.
- Exit validation: cover equality at 95% entry, 108% activation and 96% high-water levels; RSI exactly 45; EMA20 equal to EMA50; consecutive-session comparisons with missing observations; simultaneous triggers; partially unavailable checks; entry changes; partial sells; reset fencing; and close/reopen behavior. With unchanged entry 1,000, expected levels are loss 950, activation 1,080 and trailing 1,104 after a high close of 1,150. Test persistent activation after entry rises, no retroactive activation using old highs, session 0/29/30/31 boundaries, holiday and missing-price counting, late processing, retry idempotency, and old-policy retention versus new-position policy assignment. Separately evaluate turnover, drawdowns and fee-adjusted outcomes under manual next-session-close execution. Fixed percentages are not volatility-adjusted or guaranteed loss limits; ATR-distance analysis does not introduce ATR-based exits.
- Calculation fixture: buy 10 shares at 1,000 XOF with a 100 XOF fee, then 10 at 1,200 with a 120 fee. Gross average entry is 1,100. Sell 5 at 1,300 with a 65 fee: allocated cost is 5,500, allocated purchase fee is 55, gross realized P&L is 1,000, and net realized P&L is 880 XOF. Remaining gross cost is 16,500 and purchase fees are 165 for 15 shares.

### Transaction Boundaries

- Order acceptance: verify admission and ownership; transactionally read the portfolio control, active generation, affected position when relevant, and command receipt. Validate the recommendation reference and request fingerprint, reserve cash or shares, create the pending order, update the summary/version, and write the receipt together. Snapshot the applicable fee; later preference changes do not reprice an accepted order. A reservation is not a completed cash movement.
- Execution: read immutable execution-price revisions and their publication/calendar/runtime controls inside the fill transaction, following integration design section 3. A prefetched BigQuery or price value alone never authorizes a fill. Recheck control, generation, order, summary, position, execution identity and available resources excluding other reservations. Atomically write execution/cash movement, update cash and position, release this reservation and finalize status. A repeated job has no second ledger effect.
- Rejection or expiry: atomically finalize the terminal status with its reason and release reservations, without creating a fill, fee, or trade cash movement. Reject an unaffordable order in full. Expire an order if its original intended-session close is unavailable within the confirmed one-additional-session grace period. Execution and expiry race on the same order/generation transaction checks, so only one terminal outcome is possible.
- Reset: require expected generation/state version, recovery identifier and idempotency key. Persist independent restrictive intent, transactionally fence/revalidate, confirm the ordered exclusion, then atomically finalize the new generation, opening balance and receipt. This cross-store protocol is not a single atomic operation; success requires durable register protection and the final database commit. Block ambiguous outcomes and resume under the same operation ID. Delete inaccessible old records in bounded retries; old workers cannot write into the replacement simulation. Integration design section 4 is normative.
- Retry discipline: transaction callbacks must have no external effects such as network calls, model calls, or job scheduling. Generate stable identifiers before entering a retriable transaction. A reused idempotency key with a different payload conflicts; after reset, retries for an old generation must never create a new order. Receipt retention must preserve the supported retry window without retaining cleared financial history.
- Read consistency: portfolio responses identify generation, state version, and valuation batch/session. Assemble summaries and positions from a consistent database snapshot or retry if their version changes; never combine generations during reset. Pending cash reservations and reserved share quantities are displayed separately from executed holdings and cash movements.
- Reconciliation: test that cash equals the opening balance plus signed cash movements, quantities agree with executions, reservations agree with pending orders, and cash/holdings cannot become negative. This is a tested current-state-plus-ledger design, not an event-sourced platform.

Confirmed paper-order behavior:

1. Accept a user command with an idempotency key, recommendation reference, side, and quantity.
2. Validate ownership and current cash or holdings; reserve resources so competing pending orders cannot reuse them.
3. Bind the order to a trading session strictly after acceptance. An old recommendation cannot be used to obtain a historical fill.
4. When that session's authoritative close is available within the grace period, revalidate resources including the snapshotted fee and commit the order, cash, and position changes atomically. Keep the intended pricing session separate from the processing timestamp.
5. If a Buy's actual cost exceeds available cash, reject the entire order at execution with a reason and release its reservation. No partial fill or execution fee is posted.
6. A repeated job must return the existing outcome without posting another execution.
7. Reset atomically replaces the active simulation generation and starting balance, immediately presenting empty positions, orders, and history. Every execution transaction checks the active generation; a job for the previous generation cannot modify the new simulation. Delete inaccessible old-generation records afterward in bounded, retryable batches rather than attempting an unbounded transaction.

If the intended close is delayed, retain the pending order and its reservations for one additional trading session, then expire it if the original price remains unavailable. Never substitute a later-session close or reopen an expired order after a late arrival. Approved cutoff: persist the verified officialization time plus 60 seconds of the immediately following trading session as the grace deadline, based on the authoritative calendar rather than weekdays. Record when the validated intended-session price became available to the platform; execution eligibility uses that timestamp so a delayed worker cannot backdate late-arriving data or expire a timely available price. The authoritative calendar/source-availability and recovery integrations are specified in the approved Integration Design v1.0; implementation and verification remain required. Retention and recovery targets are approved in section 9.

## 8. Interfaces & Integrations

**Price-availability policy (approved 2026-09-20):** Execution eligibility uses when the validated intended-session price first became committed and usable by the platform. Preserve that timestamp across retries so a late worker can process timely data without treating late data as timely. Retain revision/timestamp evidence; do not revive expired orders. API/data contract section 5 defines engineering defaults and remaining commit/publication and correction-selection details. No new service or data-quality interface is introduced.

**Calendar approach (approved 2026-09-20):** Reuse ingestion to combine official BRVM holiday dates and trading schedules, with trusted operators maintaining verified, date-specific exceptions backed by BRVM public notices. No separate administration interface or new calendar service is required. Retain source evidence and calendar versions; test provisional dates and exception precedence. API/data contract section 8 records source details and remaining coverage, timing and correction semantics. This approval does not establish a deployed calendar or verified historical coverage.

Internal processing interfaces remain separate from the browser-facing REST API:

| Interface | Input | Output / effect |
|-----------|-------|-----------------|
| Publish ingestion result | Source, run ID, covered period, snapshot reference, load outcome | Readiness record for downstream analysis |
| Calculate analysis | Input snapshot, session, rule version | Shared results, explanations, and batch manifest |
| Read Swing workspace | Authenticated user, published batch | Shared stock states plus separate holding advice |
| Read Long-Term ranking | Published batch, objective | Ranking, component scores, explanations |
| Submit paper order | User identity, recommendation reference, side, quantity, idempotency key | Pending order or explicit rejection |
| Execute or expire pending orders | Authoritative closing data and availability timestamp, grace deadline, portfolio generation | Atomic, idempotent execution, full rejection, or expiry with released reservations |
| Reset simulation | User identity, expected generation, starting balance | New empty simulation at the selected balance |

### Resource-Oriented REST API

Option 2 establishes the resource-oriented style. API And Data Contract v0.13 (companion baseline document) provides endpoint payloads, result/availability states and normalized input schemas. The stakeholder approved the technical package on 2026-09-20: six-decimal exact money/string transport, whole shares and overflow rejection, state/batch-bound pagination (50 default/100 maximum), 1,000-session chart limits, 16 KiB commands, duplicate protection with 30-day receipts and five-minute first submissions, explicit reconfirmation after uncertain outcomes, expected portfolio versions, separate setup/order/reset endpoints and generated typed clients. Lower-level encoding and scalar details are engineering defaults to validate in implementation. Sell from Keep with acknowledgment and recommendation freshness are also approved. Source/recovery integration design is approved in the integration baseline; this is not an implemented API. Financial calculations remain governed by financial contract v1.1.

| Method and path | Responsibility |
|-----------------|----------------|
| `GET /v1/me` | Current admitted user and preferences |
| `PATCH /v1/me/preferences` | Update investment objective and fee preference for future submissions; cannot modify admission, cash, positions, pending-order fee snapshots, or past execution fees |
| `GET /v1/swing/recommendations` | Shared entry results and signal strength, with separate generation-bound personalized holding advice; no probability-like confidence field |
| `GET /v1/long-term/rankings?objective=growth` | Growth rankings; `dividend` returns research facts with deferred-score status and no suitability ranking; `balanced` returns explicit deferred-scope status, never a numeric rating |
| `GET /v1/stocks/{symbol}` | Company detail and published Swing/Long-Term evidence |
| `GET /v1/stocks/{symbol}/chart` | Bounded dated OHLC/volume and EMA, RSI, ATR, traded-value series; allowlisted configurations with periods, warm-up status, and actual/estimated turnover basis |
| `GET /v1/paper/portfolio` | Active summary, positions, valuation freshness, and separate personalized holding advice |
| `GET /v1/paper/orders` | Paginated active-generation order history, with optional allowlisted status filter |
| `GET /v1/paper/executions` | Paginated active-generation fills and applied fees |
| `GET /v1/paper/cash-movements` | Paginated active-generation cash ledger |
| `POST /v1/paper/portfolio` | Initial setup: selected starting cash and explicit fee; creates the first generation only, not a top-up |
| `POST /v1/paper/orders` | Accept a manual recommendation-linked order as pending, never immediately fill it |
| `POST /v1/paper/reset` | Replace the active simulation using the expected generation and selected starting cash |

Contract rules:

- All endpoints require verified identity and current invitation access. Paper routes infer the owner from identity; they do not accept a target user ID. Browser code has no Firestore write access. Worker execution uses workload identity and an internal entry point, not a browser-authorized fill endpoint.
- An order request supplies recommendation reference, analysis batch, symbol, side, quantity, and expected generation. A reset supplies expected generation and starting cash. Both require `Idempotency-Key`. The backend validates the reference and determines acceptance time, fees, reservations, and execution-session eligibility.
- Initial successful order creation returns `201` with the pending order. Reset returns `200` with the new generation and summary; old-record deletion may still be running. Receipts make retries deterministic within the documented retry window and reject stale-generation reapplication.
- Use `401` for missing/invalid identity, `403` for non-admitted access, `404` for absent or inaccessible records, `409` for stale generation/resource conflicts or idempotency payload mismatch, and `422` for invalid fields. Errors expose a stable code, safe message, and request ID, never internal credentials or another user's data.
- Use bounded page sizes and opaque cursors for growing histories. Cursors bind to owner, generation, filters, and stable ordering; reset invalidates previous-generation cursors. Shared result pagination binds to a batch so daily publication cannot mix result versions across pages.
- Financial values remain authoritative on the backend. Shared analysis responses expose `batch_id`, effective market date, rule version, availability reason, and evidence. Paper responses additionally expose generation and state version. User-specific responses must not enter a shared cache.
- Publish versioned OpenAPI schemas from FastAPI/Pydantic and generate the TypeScript client from them. Contract tests cover schema compatibility, ownership, repeated submissions, concurrent reservations, duplicate executions, reset races, pagination, and stale batch/generation handling. Implement the approved technical baseline and its documented engineering defaults; generated schemas and passing tests remain delivery work, not completed by approval.

A coherent published batch must be visible to the application; intermediate processing results must not appear as a completed market update. Normal workspace requests read the published serving copy without launching BigQuery calculations. Serving records carry the canonical batch ID and are republished from BigQuery after a recoverable copy failure.

Frontend-facing analysis responses must identify symbol, analysis batch, effective market date, rule version, availability reason, and calculation evidence where applicable. Chart responses carry dated OHLC/volume or named indicator series; Long-Term responses carry objective and factor contributions. Personalized holding advice is a distinct field from the shared market result. Define the precise transport schemas with the backend API contracts.

The existing OpenRouter integration is part of financial ingestion, not an interactive recommendation service. Its API key belongs in managed secret configuration. Bound calls and retries per document and per batch; persist completed extractions so retries do not repeat paid work. Provider failure delays affected financial updates while the last complete analysis remains available with its original date. No external extraction request was made during this review.

## 9. Cross-Cutting Concerns

- Security (confirmed 2026-09-20): Firebase Authentication email/password sign-in, email verification and password reset; no Google account requirement. The API verifies identity and verified-email status and checks current administrator-managed email allowlist admission on every protected request, including analytical reads and paper commands. Fail closed on unavailable admission checks; do not rely only on token claims or frontend routing for current membership. Removal denies subsequent protected requests even while an authentication token remains valid; already downloaded information cannot be recalled. Store portfolio ownership by verified UID, never caller-supplied UID. An email change requires verification and fresh admission for the new address; do not transfer portfolios by matching an email.
- Admission administration: manual trusted tooling only, no invitation-management UI, public application admission or admin self-escalation. Store allowlist entries separately from user-editable preferences with admin-only writes. Authentication registration is distinct from application admission: creating an account does not grant protected access. Use consistent email matching without provider-specific alias rewriting. Google federation is not part of the committed V1 baseline. Verification and reset screens may be public; protected API data may not. Provider credentials/password handling stay with the identity provider, not the application database or logs.
- Access verification: test unverified/non-allowlisted/removed identities, valid-token removal, email changes, fail-closed admission reads and cross-user isolation, plus verification/reset flows. Identity integration is implementation work, no longer an unresolved product choice.
- Reproducibility: repeated analysis with the same snapshot and rule version must yield identical results. Repeated execution of an order must produce exactly one ledger effect.
- Financial extraction: record model outputs once and replay accepted artifacts for deterministic analysis. Include extraction usage and retry counts in the cost model; provider availability and pricing are not established by the repository.
- Resilience: retries use stable run and order identities. Failed analysis preserves the last complete publication with its actual date visible.
- Scalability and FinOps: calculate common analysis once per batch and serve persisted results. Compare BigQuery bytes billed, job duration, serving writes, storage, and transfer against the equivalent Python batch before choosing an execution engine. No per-user source-history recalculation, permanently allocated BigQuery capacity, or always-on worker is planned for V1.
- Cost controls: use BigQuery dry-run estimates and maximum bytes billed; bound retries, backfills, result sizes, and job timeouts. Select only required columns and history; use partitioning/clustering when measurement justifies them. Retain enough warm-up history to preserve calculations. Monitor container/image retention, source/PDF storage, builds, logs, scheduler/workflow activity, secrets, and network transfer as well as runtime compute. Confirm regional eligibility and shared-account consumption before relying on free allowances.
- Idle behavior: configure zero minimum Cloud Run instances with request-based API billing and accept cold starts; no periodic keep-alive calls. Static hosting and managed storage require no application VM, but retained data and background schedules can still incur charges. Do not suspend service automatically at EUR 5; this is a directional cost target, not a hard cap.
