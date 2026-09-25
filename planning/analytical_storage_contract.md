# Additive Analytical Source Storage Contract

Status: repository-level, versioned logical contract only. No BigQuery table is asserted to exist or to be provisioned by this change. These definitions supplement the existing source tables; they do not rename, replace, truncate, migrate, or delete `shares`, `financials`, or existing revision tables.

## Revision Tables

`share_price_revisions_v1` stores one immutable source revision per `(symbol, session_date, revision_id)`. It maps the normalized price contract and retains its original source date, basis, trade status, session-date status, source observation/revision identity, collection/known/publication timestamps, parser version, and optional source snapshot URI/hash. `session_date_status` records `trading`, `non_trading`, or `unknown`; it is distinct from `trade_status` (`traded`, `confirmed_no_trade`, `unknown`). Corrections append another revision. A retry of the same revision is an insert/no-op, never an update of committed values.

`annual_financial_revisions_v1` is the owner-selected additive, versioned canonical annual-financial contract. It preserves the legacy `financials` table and keys a revision by company, fiscal period, report scope, source, source observation, and `revision_id`. The financial fields mirror the normalized V1 annual contract: currency and original scale, revenue, ordinary-owner earnings, equity and opening equity, publication status, and reason codes, plus source/revision metadata. Unknown publication or accounting evidence remains explicit; nullable values are not interpreted as zero. The contract is versioned in the table name so a future incompatible shape can be introduced without silently reshaping existing rows.

## Retention And Physical Selection

Keep source snapshots and their hashes while any retained analytical revision or published result depends on them. Keep price history through the active indicator warm-up/replay horizon and any active paper execution references; keep annual financial history needed by the five-year Growth window, opening-equity denominators, published recommendations, and corrections. The 12-month recommendation retention is not a cutoff for source history. Exact source-object lifecycle periods, snapshot URI conventions, dataset location, legacy physical schema, and existing table partitioning have not been verified here. Do not delete evidence where dependency or cleanup eligibility is unknown.

Candidate partition columns to benchmark against representative query shapes are `session_date` and `collected_at` for share revisions, and `fiscal_period_end` and `collected_at` for annual revisions. No partition field is selected: no production/development query or cost measurement was authorized or run. Compare scan bytes, query latency, and write behavior using approved representative data before physical provisioning. Cluster candidates (symbol/company and session/fiscal period) are likewise unmeasured.

## Retry-Safe Load Boundary

The existing `upsert_into_bigquery` helper documents that its load identity and isolated staging table do not provide a distributed lock. Orchestration must guarantee at most one active writer per target across all invocations, retries, and schedules. Concurrent insert-first `MERGE` operations are outside the helper's safety guarantee. Every revision adapter must pass its complete immutable key, including `revision_id`, and set `update_matched=False`; reuse of a key with different contents is a conflict to reject, not an update. Retries with identical keys and values may safely converge under the serialized-writer condition. Schedule activation and infrastructure mutation remain separately gated.

## Safe Blockers Before Physical Provisioning

- Verify actual dataset/table locations and existing `shares`, `financials`, and revision-table schemas through an approved infrastructure review; this contract makes no compatibility claim about them.
- Establish source-observation and source-revision identity derivation from the adapters. Where source evidence supplies no stable identity, preserve snapshot hash plus parser/source metadata and keep the mapping explicit; do not synthesize a claim of source publication identity.
- Measure partition and clustering candidates before selecting physical options.
- Verify snapshot and revision retention dependencies and cleanup ownership before setting lifecycle rules.
