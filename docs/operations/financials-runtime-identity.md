# Retired legacy financial runtime identity

The dedicated Cloud Functions identity documented here belonged to the
financial Cloud Function and Workflow topology retired by issue #365. Its
Terraform service account, BigQuery access, bucket grants, and OpenRouter
secret binding are removed from the active configuration. FI-1 runs with the
dedicated `fi1_financial_runtime` identity and table-scoped BigQuery access;
the current grants are defined in `terraform/iam.tf` and summarized in
`fi1-financial-job.md`.

The `financials_runtime` identity's retirement does not delete stored financial
PDF archives, annual revision assets, canonical BigQuery rows, or the shared
non-financial ingestion identity. Historical source ZIP objects are retained
in place and are no longer managed by Terraform.

Any cloud-side retirement is performed only through the separately approved
delivery workflow. This implementation does not authorize a plan, apply,
schedule activation, job execution, provider call, or production operation.
