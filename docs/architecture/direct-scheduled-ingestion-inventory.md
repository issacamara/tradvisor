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
