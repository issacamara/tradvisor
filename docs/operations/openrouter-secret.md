# OpenRouter financials secret operations

## Ownership and runtime wiring

Terraform manages only the environment-local Secret Manager metadata selected
by `openrouter_secret_id` in `project_id`, with `prevent_destroy`. The default
non-secret ID is `openrouter-api-key`; development and production create
separate secret resources in their respective projects and have independent
payloads. Terraform never creates a version or receives, reads, or stores the
key payload.

Only `scrape_financials` and `insert_financials` receive the secret through the
Cloud Functions 2nd gen `OPENROUTER_API_KEY` secret environment configuration.
The `financials_runtime` service account receives
`roles/secretmanager.secretAccessor` on that declared secret resource only.
Other ingestion functions retain their existing identity and configuration.

## Initial provisioning

1. An authorized operator provisions the key as a Secret Manager version
   directly in the intended environment project, using the approved secure
   credential-handling procedure.
2. Confirm from version metadata that the intended version is enabled. Do not
   read or print its payload as part of this check.
3. Dispatch the reviewed delivery workflow for that environment with the
   non-secret secret ID. Use that same ID for plan and apply; review the saved
   plan to confirm it names the selected environment-local secret, then follow
   the environment's approval gate before applying function wiring.

Never place the payload in Terraform inputs or state, GitHub, workflow inputs,
source, tests, diagnostic fixtures, logs, or artifacts. Do not copy the value
between development and production.

## Rotation and rollback

1. An authorized operator adds a new version directly in the correct project
   through the same secure procedure.
2. Confirm the new version is enabled using metadata only.
3. Run a fresh reviewed plan and approved apply so both functions refresh their
   `latest` secret environment version. Verify function health without
   retrieving or logging the payload.
4. Retain the previous enabled version until the updated functions are
   verified. For rollback, select the prior version as the enabled version and
   use a new reviewed plan and approved apply to refresh the functions.

Secret version creation, rotation, and function apply are operator actions.
This document does not authorize their execution.
