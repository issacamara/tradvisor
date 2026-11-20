# FI-1 financial ingestion Job

The archive scripts dependency input and lock remain shared by existing archive
function packages and retain their Firestore dependency. FI-1 no longer uses
that client, but dependency cleanup would change unrelated package sources and
is deferred to a separately scoped change.

Terraform provisions the FI-1 Cloud Run Jobs and their single direct monthly
Cloud Scheduler target only when `manage_fi1_financial_job` is true. The image input,
`fi1_financial_job_image`, must be an immutable `@sha256:` digest supplied by
the FI-1 release integration from `fi1_job.digest` in the commit-bound release
manifest. Delivery resolves it to the environment-local Artifact Registry
image. The image is built from the locked FI-1 dependencies and contains no
environment values or secrets. Both switches default off: the jobs are absent
by default, and a provisioned Scheduler target remains paused until
`activate_fi1_financial_schedule` is explicitly enabled.
After provisioning, keep `manage_fi1_financial_job` enabled; both Jobs and the
Scheduler resource are destroy-protected. The financial-specific legacy
Functions, Workflows, Scheduler target, source packaging, runtime identity and
IAM grants have been retired from Terraform configuration. Terraform state
migration removes the old trigger and execution resources while leaving
historical source ZIP objects unmanaged and intact.

Schedule activation also requires `manage_legacy_schedules`, which keeps the
remaining non-financial Scheduler inventory under Terraform ownership. The
financial scheduler and both financial Workflows are removed by the explicit
retirement state blocks. All non-financial schedules remain configured, and
historical archive and annual-financial revision assets are preserved.

Both FI-1 Jobs use the dedicated runtime identity. It can read the Terraform-managed
`stocks.brvm_companies` selector table, edit only
`stocks.financials` and `stocks.financials_staging`, submit BigQuery jobs, and
access the existing Terraform-managed OpenRouter secret. It receives no
Firestore or bucket grants. The Scheduler caller has only job-scoped
`roles/run.invoker` grants on the protected legacy and replacement Jobs.
Terraform continues to own and protect both financial tables.

Each Job runs one task at a time (`task_count = 1`, `parallelism = 1`), has no
automatic task retries, and is limited to 3600 seconds. Runtime configuration
caps work at serial RichBourse requests, five reports per symbol,
and one attempt per configured model. The OpenRouter key is injected from
Secret Manager at runtime; no secret payload or version is managed here.

## Staged Cloud Run job rename

The protected rollback Job retains the name `tradvisor-fi1-financials`; the
replacement Job is `scrape-financials`. Both use the same Terraform-managed
runtime identity, Secret Manager reference, table contracts, and execution
limits. Terraform keeps the old Job's existing image digest from state while it
creates the replacement from the current immutable release digest.

The single Scheduler resource remains
`tradvisor-fi1-financials-monthly`, with its existing caller identity, cadence,
time zone, and pause control. Its target is independently selected by
`fi1_financial_scheduler_target`, which defaults to `legacy`. The replacement
Job and its job-scoped `roles/run.invoker` grant are provisioned before a
separately approved cutover changes the variable to `replacement`; the same
Scheduler resource then changes target after Terraform has both Job bindings
ready. No second schedule is created. Rollback changes the target to `legacy`
through a separately approved delivery. Do not remove the rollback Job or its
invoker grant until a separate retirement decision is approved.

Repository inventory: Terraform and this runbook are the only hard-coded
Cloud Run job-name references found. The development and release workflows
resolve the FI-1 image from the commit-bound `fi1_job.digest` and do not name
the Cloud Run Job. The documented manual execution command uses a caller
supplied `FI1_JOB` name; the repository contains no FI-1 name-based alert or
monitor definition. Before cutover, the operator must check external scripts,
operator notes, dashboards, and alerts for the old name and update those
references as needed. Confirm the effective target and both job-scoped grants
in the reviewed plan before any approved cutover. The monthly trigger remains
paused unless schedule activation is separately approved.

For manual execution, set `FI1_JOB` to the approved current target from
`fi1_financial_scheduler_target` and confirm the project and region. Manual
execution and any historical override still require their separate approvals.

## Execution overlap contract

Owner amendment v2.0 allows scheduled, manual historical, duplicate-delivery,
and retry executions to overlap. `task_count = 1` and `parallelism = 1` limit
tasks within each execution only. Cross-run serialization is not provided.
Concurrent runs can both read the same stale BigQuery state, repeat provider
calls, and write the same `(symbol, fiscal_year)` key. The table does not enforce
that key as unique, so insert races may create duplicate rows; update races may
conflict or the last successful write can win. There is no automatic repair or
deletion. Operators must inspect run-specific receipts and current table state
when resolving a conflict; receipts do not identify a global winner.

This configuration does not authorize Terraform plan/apply, job execution,
schedule activation, secret provisioning, provider calls, or production
operations. Use the repository's existing reviewed delivery gates when those
actions are separately approved.

## Runtime commit boundary

The job reads `(symbol, fiscal_year, document_link)` state once, discovers the
selector once, and requests symbol pages serially in selector order. A symbol
is added to the in-memory write buffer only after every selected non-skipped
report succeeds; one failed eligible report discards all newly derived rows for
that symbol. The existing staging/`MERGE` writer runs after each ten terminal
symbols and once for a final partial batch when that batch is non-empty. Every
flush has a distinct run identifier, and inserted/updated counters and lookup
state advance only after the managed receipt validates. Earlier committed
batches remain durable if a later symbol, writer, or deadline failure
stops the run. Stdout shows one short outcome for each processed symbol and
insert/update counts after a non-empty batch's managed receipt validates. Fatal
state, selector, writer, completion, configuration, or deadline failures
produce a brief message without exception text. A single sanitized completion
is sent only after all current run batches commit successfully and no failure
remains. PDFs, extracted text, prompts, provider responses, credentials, titles,
links, and exception bodies remain non-retained process material and never
enter stdout.

## Financial-year selection and operations

Design authority is the [FI-1 architecture amendment](https://github.com/issacamara/tradvisor/issues/1#issuecomment-6779080647)
delivered through predecessor PRs [#416](https://github.com/issacamara/tradvisor/pull/416),
[#417](https://github.com/issacamara/tradvisor/pull/417), and
[#418](https://github.com/issacamara/tradvisor/pull/418) for issues #412–#414.

The scheduled monthly run uses Terraform-injected
`TRADVISOR_FINANCIALS_SELECTION_MODE=publication_year`. At the start of each
execution the Job captures the UTC calendar year once, then scans each
RichBourse symbol listing sequentially from newest to oldest. It pairs the
publication date with its document link and considers up to the configured
limit of annual documents published in that year, in listing order. Interim
reports, missing source fiscal-year labels, and off-origin links are skipped.
Empty or repeated pages end pagination, as does a page older than the captured
publication year. In 2026, a report published in 2026 with fiscal year 2025 is
eligible; the fiscal year still controls extraction validation and BigQuery row
identity. FI-1 tries later eligible links when an earlier document fails
validation, then stops after the first valid new result for that symbol. The
existing unchanged-link skip and write/receipt/completion boundary remain in
force.

The `historical` and `previous_year` modes remain supported for explicit
historical use and rollback; `previous_year` continues to select by source
fiscal-year label.

The FI-1 Job sends the existing sanitized `financials` completion only after
changed rows have committed and the whole run has no failures; the existing
completion-control path then requests Long-Term publication. A run with no
committed changed rows (for example, no candidates or only unchanged links)
does not emit completion, and any failed run suppresses completion even if an
earlier batch committed. A retry is a new independent invocation that reads
current committed BigQuery state once; it may repeat provider calls or race an
active run. Matching links present in its initial snapshot are skipped, but
later concurrent writes are not visible to that snapshot. Per-run receipts and
completion describe only that invocation; another run may still be active or
later change the same row. Do not attempt to resume in-memory work from the
failed process. Investigate duplicate rows or write conflicts manually; do not
delete or repair financial rows automatically.

When the selection-mode variable is omitted, the runtime preserves the
backward-compatible `historical` mode: it considers the existing Y−5 through
Y−1 window, up to the configured cap of five reports per symbol. An explicit
blank or unknown value fails configuration validation before backing services
are accessed. Do not infer the mode from a schedule name or report count.

Historical catch-up is an operational exception for an explicitly authorized
manual run. Use the same immutable FI-1 image and inject
`TRADVISOR_FINANCIALS_SELECTION_MODE=historical` for that execution only; do
not change the scheduled Job's persistent environment or activate a schedule
to perform catch-up. For example, after approval, an operator can invoke the
existing Job with an execution-scoped environment override:

```sh
gcloud run jobs execute FI1_JOB \
  --project=DEV_PROJECT \
  --region=REGION \
  --wait \
  --update-env-vars=TRADVISOR_FINANCIALS_SELECTION_MODE=historical
```

Replace placeholders only after confirming the development Job, project, and
region. Before execution, verify effective permission for both
`run.jobs.run` and `run.jobs.runWithOverrides` on the target Job; the override
permission is required when using `--update-env-vars`. Obtain separate
approval for the development Job execution and for any paid provider call or
BigQuery query. The override applies to this execution and does not change the
stored Job or monthly schedule. Record only the approved change/run identifiers,
selected mode, sanitized outcome, and result. Do not retain source documents,
extracted data, prompts, provider responses, credentials, or raw exception
messages.

If a missing fiscal-year report arrives after its year is no longer Y−1, the
monthly mode will not select it. For example, a 2025 report arriving in 2027
requires an authorized historical run; it remains eligible only while inside
the historical Y−5..Y−1 window. A report older than that window needs separate
review. Existing financial rows for older years remain stored, but missing
history can leave Long-Term Growth coverage incomplete. A source correction
that keeps the same document URL remains outside detection because unchanged
links are skipped.

If the monthly `publication_year` behavior needs to be rolled back, restore the
last reviewed FI-1 release configuration and image through the approved
development delivery workflow, retaining the monthly trigger's paused state
unless schedule activation is separately approved. Validate the resolved
selection mode with the image's offline `--check-config` smoke check before
delivery. A rollback must not run a catch-up execution or change production.
