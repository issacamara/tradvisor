# FI-1 financial ingestion Job

Terraform provisions the FI-1 Cloud Run Job and its direct monthly Cloud
Scheduler target only when `manage_fi1_financial_job` is true. The image input,
`fi1_financial_job_image`, must be an immutable `@sha256:` digest supplied by
the FI-1 release integration from `fi1_job.digest` in the commit-bound release
manifest. Delivery resolves it to the environment-local Artifact Registry
image. The image is built from the locked FI-1 dependencies and contains no
environment values or secrets. Both switches default off: the job is absent by
default, and a provisioned Scheduler target remains paused until
`activate_fi1_financial_schedule` is explicitly enabled.
After provisioning, keep `manage_fi1_financial_job` enabled; the Job and
Scheduler resources are destroy-protected. The financial-specific legacy
Functions, Workflows, Scheduler target, source packaging, runtime identity and
IAM grants have been retired from Terraform configuration. Terraform state
migration removes the old trigger and execution resources while leaving
historical source ZIP objects unmanaged and intact.

Schedule activation also requires `manage_legacy_schedules`, which keeps the
remaining non-financial Scheduler inventory under Terraform ownership. The
financial scheduler and both financial Workflows are removed by the explicit
retirement state blocks. All non-financial schedules remain configured, and
historical archive and annual-financial revision assets are preserved.

The FI-1 Job uses its own runtime identity. It can read the Terraform-managed
`stocks.brvm_companies` selector table, edit only
`stocks.financials` and `stocks.financials_staging`, submit BigQuery jobs, and
access the existing Terraform-managed OpenRouter secret. It also receives the
same project-level `roles/datastore.user` grant as the existing V1 runtime so
#362 can use the approved Firestore transactional control path for its lease.
No new Firestore lock resource or table is created. It receives no bucket
grants. The Scheduler caller has only `roles/run.invoker` on this Job. Terraform
continues to own and protect both financial tables.

The Job runs one task at a time (`task_count = 1`, `parallelism = 1`), has no
automatic task retries, and is limited to 3600 seconds. Runtime configuration
caps work at serial RichBourse requests, five reports per symbol,
and one attempt per configured model. The OpenRouter key is injected from
Secret Manager at runtime; no secret payload or version is managed here.

## Execution overlap contract

Cloud Run Jobs exposes task parallelism within an execution, but no Terraform
setting that guarantees only one execution exists at a time. A manual run or a
duplicate delivery could overlap another execution even with one task and
`parallelism = 1`. This infrastructure does not add a lock or other state. The
one-active-execution guarantee is completed by #362's lease implementation
through the existing Firestore control path; Terraform supplies only the
identity grant needed to reach that path.

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
batches remain durable if a later symbol, writer, lease, or deadline failure
stops the run. Each processed symbol emits one bounded terminal outcome, and
each committed batch emits insert/update counts only after its managed receipt
validates. State, selector, lease, writer, and completion failures emit only a
bounded stage and error class. A single sanitized completion is sent only after
all current run batches commit successfully and no failure remains. PDFs,
extracted text, prompts, provider responses, credentials, titles, links, and
exception bodies remain non-retained process material and never enter stdout.

## Financial-year selection and operations

Design authority is the [FI-1 architecture amendment](https://github.com/issacamara/tradvisor/issues/1#issuecomment-6779080647)
delivered through predecessor PRs [#416](https://github.com/issacamara/tradvisor/pull/416),
[#417](https://github.com/issacamara/tradvisor/pull/417), and
[#418](https://github.com/issacamara/tradvisor/pull/418) for issues #412–#414.

The scheduled monthly run uses the Terraform-injected
`TRADVISOR_FINANCIALS_SELECTION_MODE=previous_year`. At the start of each
execution the Job captures the current UTC calendar year once; in 2026 this
mode considers only 2025 annual reports, and in 2027 it considers only 2026
annual reports. It selects at most one eligible annual report per symbol after
the existing origin, redirect, annual-report, and unchanged-link checks. A
symbol with no eligible report, or whose link is unchanged, does no extraction
or write work. Selection uses the report's fiscal-year label, not its
publication or announcement date: a 2025 fiscal-year report published during
2026 remains eligible in `previous_year` mode. Extraction must return the same
fiscal year as the source label.

The FI-1 Job sends the existing sanitized `financials` completion only after
changed rows have committed and the whole run has no failures; the existing
completion-control path then requests Long-Term publication. A run with no
committed changed rows (for example, no candidates or only unchanged links)
does not emit completion, and any failed run suppresses completion even if an
earlier batch committed. A bounded `lease` failure means another FI-1
execution currently owns the shared lease. Let that execution finish and
release its lease before retrying; do not start an overlapping run or clear the
lease manually. After the earlier execution has ended, a new invocation reads
current committed BigQuery state: committed batches remain durable and are
skipped by matching link, while incomplete work can be retried from persisted
state. Do not attempt to resume in-memory work from the failed process.

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

If the monthly `previous_year` behavior needs to be rolled back, restore the
last reviewed FI-1 release configuration and image through the approved
development delivery workflow, retaining the monthly trigger's paused state
unless schedule activation is separately approved. Validate the resolved
selection mode with the image's offline `--check-config` smoke check before
delivery. A rollback must not run a catch-up execution or change production.
