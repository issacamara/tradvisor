# Analytical Source Storage Contract

Status: repository-level contract only. No BigQuery table is asserted to exist or to be provisioned by this change. This document does not rename, replace, truncate, migrate, or delete `shares`, `financials`, or existing revision tables.

## Canonical Shares And Financial Revisions

Incoming share files and retained raw source evidence live in GCS. Canonical BigQuery `shares` rows are keyed by `(symbol, date)` and retain the dated history required for Swing indicators, charting, and analytical warm-up. A correction may upsert the matching canonical row. Source observation identifiers remain valid for provenance or in-memory deduplication, but V1 does not require a persisted share-price revision table or point-in-time replay of share corrections.

`annual_financial_revisions_v1` is the owner-selected additive, versioned canonical annual-financial contract. It preserves the legacy `financials` table and keys a revision by company, fiscal period, report scope, source, source observation, and `revision_id`. The financial fields mirror the normalized V1 annual contract: currency, accounting basis, and original scale; revenue, ordinary-owner earnings, equity, opening equity and its evidenced date; interest-bearing debt, unrestricted cash, current assets, current liabilities; publication status and reason codes; plus source/revision metadata. The four additional `NUMERIC NULLABLE` amounts apply to non-financial operating-company inputs and require source evidence with coherent issuer, reporting scope, period, units, and currency. `accounting_basis` and `opening_equity_date` are also nullable; unknown accounting basis or an unavailable/unverified opening-equity date remains `NULL`. Unsupported, unreported, restricted, or otherwise unverified values remain `NULL`; null is not zero, and reason-code semantics remain unchanged. The contract is versioned in the table name so a future incompatible shape can be introduced without silently reshaping existing rows.

## Retention And Physical Selection

Keep GCS source archives and their hashes while any retained analytical result depends on them. Keep canonical share history through the active indicator warm-up and chart horizon; keep annual financial history needed by the five-year Growth window, opening-equity denominators, published recommendations, and corrections. The additional nullable financial amounts do not change this retention basis. The 12-month recommendation retention is not a cutoff for source history. Exact source-object lifecycle periods, snapshot URI conventions, dataset location, legacy physical schema, and existing table partitioning have not been verified here. Do not delete evidence where dependency or cleanup eligibility is unknown.

Candidate partition columns to benchmark against representative query shapes are the existing canonical shares date and `fiscal_period_end` and `collected_at` for annual revisions. The four additional amounts do not change annual partition candidates or select a physical partition. No partition field is selected: no production/development query or cost measurement was authorized or run. Compare scan bytes, query latency, and write behavior using approved representative data before physical provisioning. Cluster candidates (symbol/company and session/fiscal period) are likewise unmeasured.

## Retry-Safe Load Boundary

The existing `upsert_into_bigquery` helper documents that its load identity and isolated staging table do not provide a distributed lock. Orchestration must guarantee at most one active writer per target across all invocations, retries, and schedules. A share correction updates its canonical `(symbol, date)` row; this does not imply a persisted revision history or replay capability. Annual-financial revision adapters must pass their complete immutable key, including `revision_id`, and set `update_matched=False`; reuse of a key with different contents is a conflict to reject, not an update. These added nullable amounts do not alter that serialized-writer boundary. Retries with identical keys and values may safely converge under the serialized-writer condition. Schedule activation and infrastructure mutation remain separately gated.

## Safe Blockers Before Physical Provisioning

- Verify actual dataset/table locations and existing `shares`, `financials`, and annual-revision schemas through an approved infrastructure review; this contract makes no compatibility claim about them.
- Establish source-observation and source-revision identity derivation from the adapters. Where source evidence supplies no stable identity, preserve snapshot hash plus parser/source metadata and keep the mapping explicit; do not synthesize a claim of source publication identity.
- Measure partition and clustering candidates before selecting physical options.
- Verify source-archive and financial-revision retention dependencies and cleanup ownership before setting lifecycle rules.
