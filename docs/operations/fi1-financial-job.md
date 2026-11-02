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
stops the run. A single sanitized completion is emitted only after all current
run batches commit successfully and no failure remains. PDFs, extracted text,
prompts, provider responses, credentials, and exception bodies remain
non-retained process material.
