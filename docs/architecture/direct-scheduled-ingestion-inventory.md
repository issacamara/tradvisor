# Scheduled ingestion trigger inventory

This inventory reflects the FI-1 financial-ingestion cutover delivered by
issues #363–#365. It describes Terraform configuration; it does not assert
that any environment has been applied or that a schedule is active.

## Automated ingestion paths

| Source | Trigger target | Schedule | Terraform input |
| --- | --- | --- | --- |
| Shares | Scheduler → `shares-wf` | `0 20 * * 1-5` (Africa/Bamako) | `manage_legacy_schedules` |
| Dividends | Scheduler → `dividends-wf` | `0 20 1 * *` (Africa/Bamako) | `manage_legacy_schedules` |
| Ratings | Scheduler → `ratings-wf` | `0 20 1 * *` (Africa/Bamako) | `manage_legacy_schedules` |
| Financials | Scheduler → FI-1 Cloud Run Job | `0 20 1 * *` (Africa/Bamako) | `manage_fi1_financial_job`; paused unless separately activated |

There is no financial Scheduler-to-Workflow path, financial Cloud Function, or
financial initialization Workflow in the active Terraform configuration. The
FI-1 job emits the existing sanitized completion outcome after its changed
financial `MERGE` commits, preserving the completion-driven Long-Term
publication control. Runtime execution remains bounded to 60 minutes.

## Retirement and retained assets

Terraform state migration explicitly retires the old financial scheduler,
recurring Workflow, initialization Workflow, and three financial Functions.
The corresponding legacy source ZIP objects are removed from Terraform state
without deleting them. The historic source modules remain available to the
FI-1 image; this change removes only their legacy Cloud Functions packaging.

Financial PDF archive objects, annual-financial revision assets, canonical
BigQuery rows and Terraform-managed financial tables are not deleted or
migrated. Shares, dividends and ratings workflow/scheduler/function
configuration remains intact. The completion-driven publication-control
queue and IAM are outside the retirement boundary.

## Operational boundary

This inventory is not evidence of an apply, deployed topology, or active
schedule. No Terraform plan/apply, schedule activation, job execution, paid
provider call, paid query, or production operation is authorized by this
documentation. Use the separately approved delivery path for environment
changes.

## FI-1 monthly and historical behavior

The monthly financial Scheduler is configured to pass
`TRADVISOR_FINANCIALS_SELECTION_MODE=previous_year` to the FI-1 Job. The Job
captures UTC calendar year Y once per execution and considers only annual
reports for Y−1, with at most one eligible report per symbol. Normal origin,
redirect, report-type, duplicate-year, and unchanged-link rules still apply.
No eligible or unchanged report produces no extraction, provider request, or
financial write for that symbol. Completion remains contingent on every
changed batch committing successfully.

Omitting the mode remains a backward-compatible `historical` selection across
Y−5 through Y−1, bounded by the configured cap. Blank and unsupported values
fail validation before service access. Historical catch-up is for explicitly
authorized manual executions only; it must use an execution-only mode override
and must not persistently change the monthly Scheduler or Job configuration.
Development execution and any paid provider/query activity require their own
approval. The configured schedule remains paused until separately activated.
If a report arrives after its fiscal year is no longer Y−1, the monthly run
will skip it; an authorized historical run can select it only while it remains
inside the Y−5..Y−1 window. Missing older history can leave Long-Term Growth
coverage incomplete even though existing financial rows are retained, and
same-URL source corrections remain undetected.

For rollback, restore the last reviewed release configuration and immutable
image through the approved delivery workflow, then verify its effective mode
offline. Keep schedule activation separate and preserve the paused state unless
it is separately approved. This inventory describes intended configuration;
it is not evidence that a release, rollback, execution, or schedule activation
occurred.
