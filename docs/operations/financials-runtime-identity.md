# Financials runtime identity

Issue #347 separates the recurring `scrape_financials` and `insert_financials`
Cloud Functions from the historical shared ingestion identity. Terraform creates
`financials_runtime` with `prevent_destroy`; the initialization function and all
other ingestion functions, Workflows, and Scheduler jobs continue to use the
shared identity.

## Runtime access inventory

The repository code and Terraform wiring show these non-secret needs:

| Access | Evidence | Grant scope |
| --- | --- | --- |
| Submit BigQuery queries and write financial rows | Both entry points query BigQuery; `insert_financials` upserts canonical financial records | `roles/bigquery.jobUser` on the project and `roles/bigquery.dataEditor` on the `stocks` dataset |
| List, read, write, and archive financial PDFs and extraction evidence | `scrape_financials` and `insert_financials` list/read/write objects in the data bucket and copy/delete processed PDFs in the archive bucket | `roles/storage.objectUser` on the data and archive buckets only |
| Emit function events | Ingestion observability emits structured events to stdout for platform collection | No explicit Cloud Logging API grant |

The `stocks` dataset IAM grant is managed independently of
`manage_legacy_bigquery_datasets`. That preservation flag controls ownership
of the existing dataset, not access required by the dedicated runtime identity.

The recurring `financials-wf` invokes `scrape_financials` with OIDC. The
one-time `financials-init-wf` invokes `insert_financials` with OIDC after the
separate initialization step. Both Workflows and the Scheduler execution caller
remain on the shared ingestion identity; their invocation grants are unchanged.
The `scrape_financials_init` function also remains on the shared identity.

No Secret Manager permission is granted here. Secret resource access and
function secret injection are separate work in issue #344. The shared account's
existing historical bindings are preserved by this change.

Terraform owns the new account and grants. Applying this change requires the
repository's normal reviewed development plan and delivery gates; this document
does not authorize a plan, apply, deployment, or schedule activation.
