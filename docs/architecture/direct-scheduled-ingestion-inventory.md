# Direct scheduled-ingestion trigger inventory

Status: read-only V1 evidence for issue #274, captured from the `V1` integration
branch at commit `2aae141`.

This inventory describes the currently declared legacy path. It does not change
or authorize cloud resources. The direct Scheduler-to-Workflows target is the
follow-on implementation in issue #276.

## Scheduled workflows and legacy callers

All four recurring workflows use the same ordered Cloud Workflows shape: each
workflow calls its listed Cloud Functions in order, and each function writes to
the listed Terraform-managed BigQuery table.

| Workflow | Ordered functions | Target table | Legacy queue | Scheduler job | Schedule (Africa/Bamako) | Minimum interval |
| --- | --- | --- | --- | --- | --- | --- |
| `shares-wf` | `scrape_shares` → `insert_shares` | `stocks.shares` | `shares-writer` | `shares-job` | `0 20 * * 1-5` | 24 hours between eligible weekday runs |
| `dividends-wf` | `scrape_dividends` → `insert_dividends` | `stocks.dividends` | `dividends-writer` | `dividends-job` | `0 20 1 * *` | 28 days |
| `financials-wf` | `scrape_financials` | `stocks.financials` | `financials-writer` | `financials-job` | `0 20 1 * *` | 28 days |
| `ratings-wf` | `scrape_ratings` → `insert_ratings` | `stocks.ratings` | `ratings-writer` | `ratings-job` | `0 20 1 * *` | 28 days |

The declared Scheduler caller posts to the Cloud Tasks REST API for the matching
`<workflow>-writer` queue. Each queue then calls the internal
`/internal/workflows/<workflow>-wf/dispatch` endpoint on the Cloud Run
`workflow-dispatcher`, which starts and waits for the named Workflows execution.
These are the complete scheduled-ingestion callers found in the repository.

## Duration, retry, and overlap evidence

- Each recurring ingestion function has a declared 180-second timeout. The
  one-time `scrape_financials_init` function has a 600-second timeout and is not
  one of the four recurring workflows.
- The legacy dispatcher has a 900-second request timeout and polls until the
  Workflows execution reaches a terminal state.
- Each recurring workflow has at most two 180-second function calls in series,
  so its declared function-time ceiling is 360 seconds (180 seconds for
  financials). The 900-second dispatcher bound leaves no declared function
  timeout longer than the dispatcher, but provider and orchestration overhead
  still requires measurement during the approved development verification.
- Legacy queue serialization is explicit: one concurrent dispatch and one
  dispatch per second. Queue retry configuration is `max_attempts = 1`; a failed
  task is not silently replayed by this configuration.
- The four schedules have a minimum interval of 24 hours (weekday shares) or
  28 days (monthly workflows), each materially greater than the 900-second
  dispatcher bound. The direct path must preserve the same workflow-level
  idempotency before queue retirement: the existing ingestion loaders collapse
  exact retries and retain canonical source identity for changed observations.

Conclusion: the repository evidence supports the overlap assumption for the
declared schedule cadence and bounded workflow path. It does not claim that a
live execution has been measured; issue #278 remains the separately approved
development verification gate.

## Shares rate-limit resilience

The Terraform-managed `scrape_shares` function is capped at two instances with
one request per instance. This conservative ceiling limits duplicate upstream
pressure and keeps the change within the owner-approved development cost
boundary; the other ingestion functions retain their existing one-instance
ceiling. The generated `shares-wf` retries only HTTP 429, 500, 502, 503, and 504
from `scrape_shares`, for at most three retries with exponential backoff from
five seconds to a sixty-second maximum. `insert_shares` remains a separate
ordered step and is reached only after a successful scrape.

These limits are Terraform configuration, not a live-operation authorization.
No Terraform apply, schedule activation, production change, or paid data
operation is part of issue #337; development deployment requires the normal
reviewed plan and owner-approved delivery workflow.

## Retirement boundary

The safe scheduled-ingestion retirement set is limited to the four
`workflow_writers` queues, their `roles/cloudtasks.enqueuer` IAM members, the
legacy Scheduler-to-Cloud-Tasks targets, the Cloud Run workflow-dispatcher
service, and its `roles/run.invoker` grant—after issue #276 proves the direct
path and the later wave tickets complete their own review.

The completion-driven publication-control queue, its IAM, and the Cloud Tasks
API enablement are explicitly excluded from this set. The public architecture
assigns that control plane to completion-driven analytical publication, not
scheduled ingestion. No scheduled-ingestion caller in this repository targets
that queue; no live resource deletion or cloud-state assertion is made here.

## Source contracts

- `terraform/functions.tf`: four workflow stages, queue rate/retry settings,
  and Scheduler HTTP targets.
- `terraform/iam.tf`: legacy queue enqueuer and dispatcher invoker grants.
- `terraform/runtime.tf`: dispatcher timeout, concurrency, and service boundary.
- `terraform/variables.tf`: four schedule expressions and the
  `manage_legacy_schedules` ownership gate.
- Existing ingestion loaders and tests: retry-safe canonical writes and
  duplicate/revision behavior.
