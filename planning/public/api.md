# Tradvisor V1 - API And Data Contract

**Version:** 0.13
**Date:** 2026-09-20
**Status:** FINAL - architecture handoff baseline; not an implemented API
**References:** BRD v1.23; architecture v1.0; financial calculation contract v1.1

## 1. Authority And Review Boundary

**Integration baseline approved 2026-09-20:** [Integration Design v1.0](tradvisor_integration_draft.md) is normative for session timing, execution-price publication and recovery-register ordering/completeness. Its sections 2-4 supersede earlier unspecified integrations and fence-first reset sequencing. Use a verified officialization-plus-60-seconds cutoff; publish immutable execution revisions with server timestamps and transactionally checked control records; persist restrictive recovery intent before live fencing/denial. Scan register intents and ordered heads before reopening, block globally on incomplete inventory, and block affected subjects on unresolved chains/intents. Isolate the old database and workers before reopening the restored target. The linked verification matrix remains required implementation work.

Preserve the approved financial rules, private admission, deferred Dividend/Balanced scoring, and operating/retention requirements. This document specifies transport and logical data contracts, not a new service or a change to investment rules. Existing source tables are inputs, not evidence that every field below is already available. BRD controls scope and the financial contract controls calculations.

Lower-level details below, including integer representation, key encoding, clock-skew allowance, cursor lifetime and scalar ceilings, are engineering defaults supporting that approved package, not separately elicited business requirements. Validate them through typed schemas and boundary/concurrency tests. Integration design is approved in the linked integration baseline; existing financial-report processing is reused without a new extraction benchmark or allowance prerequisite; company-reference direction and WCAG 2.2 AA target are approved in architecture section 11. Approval is not evidence of implementation or passing tests, and implies no live database access, migration or deployment.

## 2. Transport, Identity And Scalars

- Base path `/v1`; JSON uses `snake_case`. Reject unknown request fields, non-finite numbers and invalid enum values. Additive response fields are permitted; removal, changed semantics or new required request fields require a versioned migration.
- Every listed endpoint requires verified authenticated identity, verified email and current allowlist admission. Identity and owner UID come from backend verification, never request bodies. Check admission on every request, including receipt replay. Static sign-in/reset-password/verification screens remain public; application data does not.
- Ordinary application credentials never authorize worker fills, analytical publication, allowlist writes or arbitrary cash/position changes. Password handling stays with the identity provider. Application responses use `Cache-Control: private, no-store`; browser storage must not act as an authorization boundary.
- Dates are `YYYY-MM-DD`. Instants are UTC RFC3339 strings. Session dates and timestamps are distinct; a timestamp cannot substitute for an authoritative exchange session. Symbol is an exact reference-catalog identifier, not an unconstrained free-text issuer name.
- Opaque IDs are case-sensitive strings, maximum 128 ASCII characters. Batch IDs are immutable opaque identifiers. Versions/counters are nonnegative integer JSON numbers within the exact safe-integer range.
- Indicators/scores are finite JSON numbers. Score bounds are `0..100`; serialize canonical calculation precision, round only in the UI. Score percentages are signal strength, not probabilities.

## 3. Response And Availability Model

Success envelope:

```json
{
  "data": {},
  "meta": {
    "request_id": "opaque-request-id",
    "server_time": "2026-09-20T12:00:00Z",
    "schema_version": 1
  }
}
```

List data is `{items: [...], next_cursor: string|null}`. Shared analytical responses additionally identify `batch_id`, `market_session`, `published_at`, `input_snapshot_id`, `rule_version` and `strategy_id` where applicable.

Each calculated metric has `status`, nullable `value`, `unit`, `reason_codes`, `evidence_refs` and its effective date/period. Status is one of `assessable`, `warming_up`, `missing_inputs`, `unsupported_basis`, `deferred_scope`. Missing/deferred values are null, never zero. Warm-up indicator values may be visible but cannot authorize a Buy. Evidence records carry source and publication/collection timestamps, original units and actual/estimated/modeled basis. Freshness is separate from calculability: an assessable historical value may still fail an advice guard.

| Result | Fields and invariants |
|--------|-----------------------|
| Shared Swing entry | `entry_action`: `buy`, `no_clear_signal`, `insufficient_data`; `buy_strength` metric; indicator metrics; eligibility guards. Keep/Sell is never a shared stock-only conclusion. || Growth | `growth_score`, `overall_score` (equal to Growth), dimension contributions, independent advisory state: `candidate`, `watchlist`, `low_score`, `review_required`, `insufficient_evidence`. Apply the financial contract guards. |
| Dividend research | Recorded ordinary/exceptional/unclassified payments with coverage and semantics; optional assessable trailing ordinary yield. `dividend_score` and objective score are null with `deferred_scope`, reason `dividend_scoring_deferred_v1`. No suitability ranking or one-year consistency/sustainability inference. |
| Balanced compatibility response | Null overall score, `deferred_scope`, reason `balanced_scoring_deferred_v1`; not an active UI scoring mode. |

Guard shape: `{code, status: pass|fail|unknown, observed, threshold, evidence_refs}`. Observed/threshold may be null where not numerical. Explanations use stable reason codes plus readable messages; clients do not parse prose. Nullable facts remain explicitly unknown. Recommended reasons include `history_incomplete`, `calendar_unavailable`, `no_current_trade`, `liquidity_unavailable`, `atr_nonpositive`, `share_basis_unverified`, `financial_inputs_missing` and `ttm_coverage_incomplete`.

## 4. Read And Preference Endpoints

| Method/path | Request | Response contract |
|-------------|---------|-------------------|
| `GET /me` | None | Verified UID and email. No allowlist contents. |
| `GET /swing/recommendations` | Optional `batch_id`, `limit`, `cursor`, exact `symbol` or `sector` filter | Shared entry results. Symbols sorted ascending, stable within batch. |
| `GET /long-term/rankings` | `objective`: `growth`, `dividend` or `balanced`; optional batch/filter/page | Growth: eligible candidates by unrounded score descending then symbol, followed by watchlist/low-score, review-required and insufficient-evidence groups, each with explicit state. Dividend: research facts ordered by symbol, not yield suitability. Balanced: explicit deferred response and no ranked items. |
| `GET /stocks/{symbol}` | Optional `batch_id` | Company reference and evidence, both analysis workflows, dated prices and source links. Unknown catalog symbol returns 404. |
| `GET /stocks/{symbol}/chart` | Required inclusive `from`, `to`; optional `batch_id`; `series` subset of `ohlcv,ema20,ema50,rsi14,atr14,traded_value20` | Max 1,000 exchange sessions per request; dates ascending. Reject larger ranges. Known no-trade/missing-price rows have explicit status; do not manufacture candles. Indicators have per-point status/basis. Last-traded close and analytical carried close are distinct. |
All paths above append to `/v1`. Lists default to 50 and permit `1..100` items; no unbounded history response. Opaque authenticated cursors bind to analytical batch, filters, order and last key. Expire cursors after 24 hours or earlier if the referenced snapshot is no longer retained. Return 409 `cursor_stale` on state/generation/filter mismatch and 410 `snapshot_expired` on expiry; clients restart pagination. Shared batches remain pinned when the latest publication changes. Do not silently mix batches.

## 5. Errors

```json
{
  "error": {
    "code": "generation_mismatch",
    "message": "The simulation changed. Refresh before submitting.",
    "retryable": false,
    "request_id": "opaque-request-id"
  }
}
```

| HTTP | Cases |
|------|-------|
| 401 | Missing/invalid authentication. |
| 403 | Unverified email or not currently admitted. |
| 404 | Unknown or inaccessible resource; never reveal another user's records. |
| 409 | Generation/version mismatch, stale recommendation/cursor, insufficient cash/shares, idempotency conflict/expiry, existing setup. Refresh-required is not permission to automatically resubmit a new intent. |
| 410 | Requested retained snapshot/cursor has expired. |
| 413 / 422 | Oversized body / invalid field, precision or unsupported value. |
| 429 | Rate limited; include bounded `Retry-After`. Exact per-endpoint limits remain deployment configuration to benchmark. |
| 503 | Required service/calendar unavailable, admission check unavailable, no published analysis. Include safe retry guidance; do not imply a failed timeout means no commit. |

Per-stock unavailable analysis is a successful 200 response with explicit calculation states, not an HTTP failure. Do not return credentials, internal stack traces or private cross-user data.

## 6. Logical Analytical Inputs

[Source-To-Calculation Mapping v0.5](tradvisor_source_mapping.md) supplies the field-level mapping, sample evidence, conditional derivations, unavailable inputs and ingestion worklist for these logical entities. Source labels do not establish verified trading dates, financial scope or complete history; unresolved fields retain the unavailable behavior specified here and in the financial contract.

These are normalized contracts to map from the supplied tables, not confirmed physical columns. `required` means necessary to the dependent computation, not that ingestion may fabricate it. Each record carries schema/parser version and source evidence references. Missing semantic fields leave dependent results unavailable.

**Calendar source evidence (2026-09-20):** The stakeholder supplied the official [BRVM holiday page](https://www.brvm.org/fr/jours-feries) as the holiday source. On inspection its dated rows cover 2026, although its introductory text still says 2023. It flags some movable holidays as subject to a one-day variation confirmed by public notice. Parse explicit dated rows and test year consistency; do not infer coverage from the heading or treat provisional dates as confirmed. Retain the retrieved evidence/version. The official [trading-hours page](https://www.brvm.org/fr/horaires-de-cotation) distinguishes closing fixing from market closure/officialization, lists normal and exceptional schedules, notes public-notice changes and a +/-60-second timing variation. These sources do not by themselves establish historical session coverage or precise execution deadlines. No scraper or live calendar has been implemented.

**Calendar approach (approved 2026-09-20):** Ingest BRVM holiday dates and combine them with the official trading schedule. For V1, trusted operators manually maintain verified exceptions based on BRVM public notices; no separate administration interface or automated notice-reading service is required. Integrate this with the existing ingestion/data model, not a new standalone service. Engineering defaults: retain each exception's source notice, affected dates, effective schedule, recorded-at timestamp and operator identity; verified date-specific exceptions take precedence over the base schedule. Publish immutable calendar versions rather than rewriting the evidence used by accepted orders. Do not assume every holiday eve uses the exceptional schedule without a supporting notice. Historical coverage requires verification; completion uses the approved conservative officialization-plus-60-seconds application cutoff, not an observed exchange timestamp. Section 5 now governs post-acceptance corrections. The technical operator owns verified exceptions; nominate the individual before launch.

| Entity / logical key | Required content and meaning |
|----------------------|------------------------------|
| Company: issuer ID + symbol mapping validity | Name, sector/activity, verified financial category, share-class/ordinary-owner basis and source. Retain historical symbol mappings; do not join solely by mutable names. |
| Exchange session: calendar version + session ID | Date, exchange timezone, official close instant, monotonic session index and source. Distinguish exchange closure from stock inactivity. |
| Price observation: symbol + session + revision | Raw OHLC, volume in shares, optional actual XOF turnover, trade status (`traded`, `confirmed_no_trade`, `unknown`), suspension evidence, original source date, collected/validated-available timestamps and price-basis reference. No-trade analytical carry/zero TR are derived fields, not fabricated raw candles. |
| Corporate action: issuer/class + event ID + revision | Effective date, action type, verified comparable price/share factors, source and known-at timestamps. Unsupported rights/complex actions block affected calculations. |
| Annual financials: issuer + fiscal period + scope + revision | Period start/end, publication/ingestion dates, currency/scale, ordinary-owner income/equity and opening equity, category-specific activity, matched debt/cash/current assets/liabilities or capital constraints/requirements, source report. Missing 2024 remains missing, not interpolated. |
| Ordinary capitalization: issuer/class + effective date + revision | Outstanding ordinary shares excluding treasury or verified matching aggregate market cap, price/share basis and effective/known-at timestamps. Do not substitute EPS weighted-average or free-float shares. |
| Dividend payment: issuer/class + payment ID + revision | Gross/net and per-share/total semantics, ordinary/exceptional/unclassified type, paid/declared status, actual payment date, fiscal attribution, installment identity, share-basis adjustments, source and known-at time. Fiscal-year-only keys cannot collapse installments. |
| Dividend coverage: issuer + covered interval + basis | Explicit completeness/no-payment evidence for the actual interval. One year in storage does not by itself prove complete trailing-12-month coverage. No five-year history acquisition is required for V1. |
| Rating: issuer + agency + scale + effective date + revision | Original rating, rated entity/instrument, publication/collection dates and source where available; no replacement for required regulatory capital. |

Retain original extraction values and units alongside normalized values. Historical evaluations use information actually known at the evaluation time; collected timestamps or fiscal years cannot silently stand in for publication timestamps. Unknown publication timing limits point-in-time validation. Resolve dividend natural-key/source rules and trade-date semantics during adapter integration, without a separate data-quality product.

## 7. Published And Transactional Records

| Record | Minimum fields / ownership |
|--------|----------------------------|
| Analysis batch | ID, input snapshot, calendar/rule/schema versions, effective session, creation/publication times, per-symbol coverage, manifest references and status (`building`, `validated`, `published`, `failed`). Analysis Engine owns it. |
| Published pointer | Complete batch ID and publication version. Advance only after all declared serving records and coverage states validate. Per-stock missing inputs do not mean a partially copied batch. Never expose building records. |
| Recommendation | Immutable reference, symbol, batch/rule/evidence references, shared entry/Long-Term fields from section 3. Corrections produce a new batch, not rewritten evidence. |
| Portfolio control | Owner UID, active generation, configured fee, schema/state/preference versions and update time. Backend-only writes. |
| Generation summary | Starting cash, cash/reserved cash, pending count, state version, creation time, active status. Available cash = cash minus reservations. |
| Position | Symbol, quantity/reserved sell quantity, remaining gross cost and purchase fees, opening session, high-water close/evaluated-through session, latched trail activation and frozen exit-policy reference. |
| Order | Owner/generation, request and recommendation references, side/quantity, acceptance time, advice action/evaluation session/exit-policy and state version at acceptance, derived override flag and acknowledgment, intended session/grace deadline, snapshotted fee, reservation, status/reason and terminal time. |
| Execution | Order ID unique within owner/generation, true intended-session price/source revision/availability time, quantity, gross, fee, allocated cost/fees, signed cash effect and processed timestamp. |
| Cash movement | Stable opening/execution-based ID, signed amount, generation, optional execution reference, occurrence and processing times. |
| Admission / preference | Authoritative admin-only membership separate from user-editable objective/fee preferences. Verified UID owns private records. An email change does not transfer ownership. |
| Command receipt | Section 6; backend-only, outside reset generations, logical expiry enforced even before physical deletion. |

Money and ledger invariants, generation fencing and atomic acceptance/execution/reset boundaries remain as in architecture section 7. No schema migration of the supplied production tables is assumed here. Personalized holding advice is tied to generation/version and cannot be cached as globally shared analysis.

## 8. Retention, Recovery And Verification

Apply approved retention: recommendations 12 months with evidence, active simulation history for its lifetime, old reset operational data deleted within 7 days, minimal receipts and operational logs 30 days, daily application backups retained 7 days. Evidence referenced by active calculations/positions survives general recommendation expiry. Reset hides old data immediately, not after cleanup.

Recovery target: 24 hours after acknowledgement. Under the approved 2026-09-20 relaxation, recover from the latest successful usable daily backup; there is no strict 24-hour maximum application-change loss or replacement guaranteed maximum. Keep daily backups and 7-day retention, monitor backup age/failures, and report the actual recovery point and potential lost-change interval. Report unavailable recovery if no usable backup exists. Before reopening, reconcile ledger/reservations/receipts, republish serving copies from canonical batches, enforce current admission and reapply reset exclusions. The approved backup/register mechanism is specified below; implementation, integration verification and cost validation remain outstanding. Missing exclusion evidence keeps affected accounts closed. The relaxed loss target never permits resurrection of reset history or removed access. Restore testing and cost validation remain release gates; no claim of zero-loss recovery is made.

### Approved Backup Mechanism And Recovery Register

**Approved 2026-09-20:** Use Firestore managed daily backups retained for seven days and a private Cloud Storage recovery register independent of database backup/restore. Preserve reset exclusions and access-removal decisions in that register. Restore into an isolated database, apply the current register and admission restrictions, reconcile application state, and only then reopen user access and order workers. Cost validation and a successful restore drill remain release prerequisites. This is an approved design, not deployed infrastructure. Backups do not replace separately maintained security-rule and retention-policy configuration.

**Failure-handling design:** Firestore and Cloud Storage writes are not one atomic transaction. First validate and persist a minimal restrictive reset intent independently of Firestore under a durable operation ID, then transactionally revalidate and fence the affected portfolio; competing writes/workers and reads of the retiring generation must respect that fence. Then confirm the ordered independent exclusion decision under that same operation ID, before committing the replacement generation and final command receipt. Report reset success only after both the exclusion and final database transition are confirmed. Do not perform the external write inside a retried database transaction callback. A timeout or interrupted operation remains pending/blocked and is resumed using the same operation ID, never silently abandoned or retried as a new reset. If the external exclusion exists but completion cannot be established, recovery excludes the old generation and keeps the account blocked until reconciled; it does not reconstruct cleared trades or claim the replacement balance was recovered.

Register records contain only recovery identifiers, affected generation or admission subject, operation type, ordering/version information and timestamps; no trades, balances, passwords or tokens. Only trusted backend/admin identities may write them; normal user credentials cannot read or modify them. Access removal first persists a restrictive intent, then immediately denies live admission and confirms the ordered register decision before reporting success. Failed live denial is surfaced and retried under the same operation ID; durable intent alone is not proof that live access was removed. Re-admission requires an explicit newer authorized decision, never restoration of an older allowlist. Ambiguous or missing recovery evidence fails closed. Recovery-register completeness, access-change ordering, write permissions and retry/reconciliation behavior must be tested before release.

**Register lifecycle (approved 2026-09-20):** Do not apply the seven-day backup expiry or 30-day command-receipt expiry blindly to the recovery register. Retain reset exclusions until verified inventory shows that no retained backup, restored database or other restorable copy can resurrect the excluded generation. If that cannot be proven, retain the minimal exclusion. Keep effective access restrictions until explicitly superseded by a newer authorized access decision; an old restored allowlist cannot supersede them. No indefinite retention of cleared financial history is authorized. Restores must not roll the register back with the database. The approved integration baseline defines complete inventory/chain verification, predecessor-checked access ordering and global versus subject-specific failure closure; implementation and fault-injection checks remain required.

**Restored orders (approved 2026-09-20):** With users and workers still blocked, reconcile the surviving ledger and reservations, then reject restored pending orders with `recovery_reconfirmation_required` and release their surviving reservations exactly once. Do not replay them, infer missing fills, or reconstruct lost cash movements. Preserve surviving terminal orders. Excluded/reset generations remain inaccessible and must not mutate the replacement portfolio. Inconsistent accounts stay blocked. Reopening requires the section 6 command fence and explicit new confirmation for any replacement orders. Report the actual recovery point and possible lost-change interval; these protections do not promise recovery of lost trades.

**Operational ownership (approved 2026-09-20):** One nominated technical operator owns calendar exceptions, pipeline failures, backup alerts and recovery. The stakeholder is product owner for Long-Term coverage acceptance, measured-cost review and launch approval. The technical operator's name and support contact must be assigned before launch; no individual is presumed appointed. Support remains best-effort with the 24-hour recovery target measured from incident acknowledgement. Passing calculation/contract tests, a successful restore drill, company/sector coverage review and a whole-stack cost estimate are release gates, not evidence already obtained.

Required implementation contract tests:

- Calendar corrections racing with fills reject affected pending orders and release reservations once; unrelated corrections do not reschedule orders. Price-revision selection respects the deadline, known invalidations and immutable completed executions.
- Restore rotates the recovery identifier and rejects old commands before receipt replay, including fresh keys and setup/reset. Old workers cannot mutate either database after reopening. Restored pending orders are rejected exactly once without fabricating fills; inconsistent accounts remain blocked.
- Register cleanup requires evidence that all resurrecting copies are gone; access restrictions survive restoration and only explicit newer authorized decisions supersede them. Test incomplete inventory and ambiguous access ordering fail closed.

- Authentication/admission on reads, mutations and receipt replay; ownership, email changes and no direct client writes.
- Setup/reset boundaries 100,000 / 1,000,000 / 100,000,000 XOF; reject fractional/out-of-range/overflow; no top-ups.
- Exact money serialization, quantity/fee limits, partial-sale residuals, full-close reconciliation, unpriced holdings and no premature rounding of exit comparisons.
- Every null/status/reason combination; deferred Dividend/Balanced never numeric; stale evidence never becomes fresh; held/unheld presentation and independent Sell triggers.
- Freshness at exchange-session completion boundaries, weekends and non-session dates; latest-published but outdated advice remains readable and cannot authorize new orders. Refresh requires renewed confirmation, while already accepted orders retain execution/expiry rules through publication delays and signal changes.
- Initial idempotency-key time boundary, within-window retries, changed payload, concurrent submission, logical receipt expiry and physical purge, reset between commit/retry, clock skew and lost response.
- Atomic setup/order/reset, state/preference races, sell reservations, insufficient fees/cash at execution, deterministic worker order, one execution per order, calendar holes, timely-price/late-worker versus late-price cases.
- Keep-to-Sell requires explicit acknowledgment; server-derived immutable override evidence; changed acknowledgment changes the idempotency fingerprint; retries reserve/fill only once. Sell-from-Sell needs no override. Reject stale/reset/unowned/missing-advice references and insufficient available shares even with acknowledgment. A later recommendation change does not cancel an accepted override order.
- Pagination at batch changes, expired batch, reset/state change, invalid filters, page bounds and incomplete chart ranges without fabricated observations.
- Retention dependency checks and restore drills that cannot resurrect reset portfolios or removed access.
- Fault injection between restrictive-intent persistence, reset fencing, ordered register confirmation and final database commit; duplicate and ambiguous writes; unavailable register; restored pending operations; removed access and explicit later re-admission. Confirm no success without durable protection and no reopening before exclusions/current admission are reconciled.
- Recovery from a usable backup older than 24 hours reports its actual recovery point without claiming a 24-hour loss bound; failed backups and absence of any usable backup are surfaced. Recovery-time measurement still starts at incident acknowledgement, and reset/admission protections remain mandatory regardless of backup age.
- Price arrival exactly at/before/after the persisted deadline; timely data with a late worker versus late data; identical re-ingestion preserves availability, corrected revisions cannot inherit earlier availability, and execution evidence retains the selected revision/timestamp. Never infer historical platform availability from a source trading date.
- Calendar parsing uses explicit row years; provisional holidays, source-backed exception precedence, missing historical coverage and calendar-version retention are tested. No unsupported holiday-eve schedule inference or silent change to an accepted order's calendar reference.

## 9. Review And Handoff

Sell-from-Keep with recorded acknowledgment, command freshness, the section 1 technical package, the section 8 calendar approach, correction behavior, recovery command fencing, restored-order rejection, register retention and operational roles are approved. Session-completion rules, race-safe price publication and recovery-register ordering/completeness/failure scope are also approved through the integration baseline. Company-reference enrichment direction and WCAG 2.2 AA target are approved; actual provenance and conformance require verification. Reuse `scrape_financials.py` and `scrape_financials_init.py`, including the existing downstream insertion path; no new extraction implementation, standalone benchmark or EUR 1/month allowance is required. Verify integration, extracted-field contracts and actual operating costs during delivery. This correction authorizes no provider calls or production runs. Source semantics/category mapping, financial-input coverage, generated schemas, calculation/concurrency tests, backup costs and restore drills are implementation or release verification, not outstanding approval of these policies. Name the technical operator and support contact before launch. Approval does not establish implementation or passing checks.

Implementation should generate versioned OpenAPI from typed backend request/response models and derive the TypeScript client. This finalized contract specifies those models, not evidence they exist or have passed tests. Version 0.13 synchronizes the frozen handoff baseline; the approved v0.14 amendment above changes only V1 cash-history ordering. Preserve the architecture's seven component boundaries. Architecture v1.0 section 13 separates task readiness from infrastructure/deployment and release acceptance gates.
