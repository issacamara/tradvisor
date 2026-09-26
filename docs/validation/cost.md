# V1 Whole-Stack Cost Review

This review is a decision record, not a bill and not a promise that the MVP will cost five euros per month. Prices, credits, free-tier eligibility, regions, quotas, billing-account status, and workload shape can change. A live measured estimate requires separately approved development usage evidence.

## Cost Model

| Surface | Idle behavior | Scheduled/active driver | Bound in V1 | Evidence status |
| --- | --- | --- | --- | --- |
| Static frontend | Static hosting and CDN requests only | Page and asset transfer | No server process; cache immutable assets | Local build/test evidence; live transfer volume unavailable |
| Protected API | Cloud Run scales to zero; no request keep-alive | Request CPU, memory, concurrency and cold starts | Bounded timeout, instance count and concurrency | Terraform declarations; live p95/cold-start measurement unavailable |
| Daily batch | No always-on worker | Batch CPU and memory after inputs are ready | One bounded task, finite timeout and retries | Local calculation/placement benchmark; live batch cost unavailable |
| BigQuery | Storage/query cost depends on retained data and scans | Scheduled indicator/publication queries | Partition/date bounds, selected columns, bounded backfills | No paid query executed for this review |
| Firestore | Stored documents and indexes remain | Reads/writes, transactions and retries | Owner-scoped pages, bounded limits, finite retries | Contract and emulator tests; production usage unavailable |
| Cloud Storage | Retained objects and recovery register | Ingestion, backup and restore transfer | Retention and isolated restore procedure are explicit | Restore drill not executed; actual backup cost unavailable |
| Logging/monitoring | Finite retained application logs | Event volume and alert evaluation | 30-day log retention, sanitized events, finite check interval | Terraform declarations; destination and volume evidence unavailable |
| Extraction/build artifacts | No extraction while schedules are paused | Scrape/PDF work, CI builds, artifact storage/transfer | Existing source reuse, finite retries and no unapproved backfill | No external extraction allowance used |

## Bounds and Measurement Plan

The owner-approved development measurement should capture: API request count and GB transfer, cold versus warm latency, batch wall time and retry count, BigQuery bytes processed and slot/on-demand charge, Firestore document reads/writes, storage GB-month and egress, log bytes, and build/artifact transfer. Record the interval, region, free-tier eligibility, billing account, and whether values are estimates or observed.

Backfills require an explicit row/date range and a maximum attempt count. A failed run must not silently expand its scan or retry budget. Alerting must surface budget pressure; it must not automatically shut down the product or change scoring to reduce cost.

## Decision

Recommended V1 placement remains: daily indicators and publication in bounded batch/analytical queries; request-time reads from immutable serving copies; paper mutations in short transactional requests; static frontend scale-to-zero hosting. This is an architecture recommendation, not a cost acceptance.

The cost gate is **pending owner acceptance** of measured development evidence. The release process must not claim the five-euro target passed, must not activate schedules solely to collect evidence, and must not treat free-tier assumptions as guaranteed credits.
