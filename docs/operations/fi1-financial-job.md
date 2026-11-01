# FI-1 financial ingestion Job

Terraform provisions the FI-1 Cloud Run Job and its direct monthly Cloud
Scheduler target only when `manage_fi1_financial_job` is true. The image input,
`fi1_financial_job_image`, must be an immutable `@sha256:` digest supplied by
the FI-1 release integration. Both switches default off: the job is absent by
default, and a provisioned Scheduler target remains paused until
`activate_fi1_financial_schedule` is explicitly enabled.
After provisioning, keep `manage_fi1_financial_job` enabled; the Job and
Scheduler resources are destroy-protected. Pause the schedule with the
activation switch, and retire resources only through the later approved
retirement work.

Schedule activation also requires `manage_legacy_schedules`. On activation,
Terraform pauses only the legacy `financials` Scheduler target. It retains the
financial Workflow, function packaging and IAM resources, every non-financial
schedule, and all historical archive or revision assets for the later legacy
retirement work. The activation precondition requires the legacy financial
target to be in Terraform's managed schedule set before FI-1 can be activated.

The FI-1 Job uses its own runtime identity. It can read the Terraform-managed
`stocks.brvm_companies` selector table, edit only
`stocks.financials` and `stocks.financials_staging`, submit BigQuery jobs, and
access the existing Terraform-managed OpenRouter secret. It receives no
bucket grants. The Scheduler caller has only `roles/run.invoker` on this Job.
Terraform continues to own and protect both financial tables.

The Job runs one task at a time (`task_count = 1`, `parallelism = 1`), has no
automatic task retries, and is limited to 3600 seconds. Runtime configuration
caps work at four concurrent RichBourse requests, five reports per symbol,
and one attempt per configured model. The OpenRouter key is injected from
Secret Manager at runtime; no secret payload or version is managed here.

## Execution overlap limitation

Cloud Run Jobs exposes task parallelism within an execution, but no Terraform
setting that guarantees only one execution exists at a time. A manual run or a
duplicate delivery could overlap another execution even with one task and
`parallelism = 1`. This infrastructure does not add a lock or other state.
Strict cross-execution exclusion remains an unresolved runtime contract for
#362 and must be resolved before claiming the one-active-execution acceptance
criterion is fully met.

This configuration does not authorize Terraform plan/apply, job execution,
schedule activation, secret provisioning, provider calls, or production
operations. Use the repository's existing reviewed delivery gates when those
actions are separately approved.
