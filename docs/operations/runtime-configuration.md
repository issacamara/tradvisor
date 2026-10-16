# V1 runtime configuration

API, daily publication and administrative processes read their configuration
from the process environment through `backend.configuration.RuntimeConfiguration`.
The same field names and validation rules apply to all three targets. Runtime
code does not load `.env` files, infer a project from its name, or fall back to
a development project. The sanitized reference is in
[`backend/.env.example`](../../backend/.env.example); it contains placeholders
only and is not a runnable cloud credential file.

The API container declares `TRADVISOR_RUNTIME_TARGET=api`; the batch job declares
`daily_job`; the internal workflow dispatcher declares `workflow_dispatcher`.
The dispatcher has a smaller configuration contract because it only submits
the explicitly selected workflow and does not access Firestore, BigQuery, or
Storage. Unsupported runtime-target names fail during application setup.

## Shared fields

| Environment variable | Required for | Meaning and validation |
| --- | --- | --- |
| `TRADVISOR_RUNTIME_TARGET` | API, daily job, workflow dispatcher, admin | Explicit process role: `api`, `daily_job`, `workflow_dispatcher`, or `admin`; it must match the validator target. |
| `TRADVISOR_ENVIRONMENT` | API, daily job, admin | Explicitly `development` or `production`; it is never inferred from the project ID. |
| `GOOGLE_CLOUD_PROJECT` | API, daily job, admin | Explicit Google Cloud project used for clients. |
| `TRADVISOR_TARGET_PROJECT_ID` | API, daily job, admin | Explicit intended project; must exactly match `GOOGLE_CLOUD_PROJECT`. |
| `TRADVISOR_ENVIRONMENT_PROJECT_ID` | API, daily job, workflow dispatcher, admin | Separately configured project authorized for the selected environment; must match both project fields above. |
| `GOOGLE_CLOUD_FIRESTORE_DATABASE` | API, daily job, admin | Explicit Firestore database ID, including `(default)` when that database is intended. |
| `TRADVISOR_SERVING_TARGET` | API, daily job, admin | Must be `firestore`, the approved V1 serving store. |
| `FIRESTORE_CURSOR_SECRET` | API, daily job, admin | Secret value injected from the runtime secret manager. Never put the value in source control, `.env.example`, command arguments, or logs. |

API configuration also requires `TRADVISOR_CORS_ORIGINS`, `WORKFLOW_REGION`,
`MARKET_DATA_TABLE`, and `TRADVISOR_RECOVERY_BUCKET`. Daily publication requires
`MARKET_DATA_TABLE` and `FINANCIALS_TABLE`. Administrative commands require an
explicit `TRADVISOR_RECOVERY_BUCKET` as well as the shared project and Firestore
target. The current command wrappers will consume the `admin` target as they are
introduced; this module does not add an administration command or UI.

Each BigQuery table must be a complete `project.dataset.table` identifier and
the project component must equal `TRADVISOR_TARGET_PROJECT_ID`. Bucket names,
Firestore database IDs, and workflow regions are validated before constructing
cloud clients. API origins must be origin-only HTTPS URLs. HTTP is accepted only
for localhost origins in development; wildcards, paths, credentials, queries,
and fragments are rejected. An intentionally empty CORS list is allowed.

The workflow dispatcher requires `TRADVISOR_ENVIRONMENT`,
`GOOGLE_CLOUD_PROJECT`, `TRADVISOR_TARGET_PROJECT_ID`, and `WORKFLOW_REGION`.
Its project IDs must agree and its region must be explicit before token
verification or workflow dispatch.

## Source precedence and local use

The process environment is the only configuration source. There is no implicit
`.env` loading, project discovery, ADC project fallback, or default production
target. The serving target and table IDs must be provided explicitly. The
Terraform runtime wiring passes the selected environment, project, and named
service resources to API and batch containers. Set `v1_environment_project_id`
independently for each Terraform environment; the runtime resources reject an
empty value or a mismatch with `project_id`. This explicit binding avoids
guessing the environment from project naming. The cursor secret is injected
through the existing Secret Manager reference.

For local tests, pass an explicit mapping to
`RuntimeConfiguration.from_environment(target, environ)` or use test doubles.
Do not export production values into a developer shell. To run an approved
development process, set its explicit development target and use only
development-scoped credentials and resources. A mismatch between the expected
and actual project fails before BigQuery, Firestore, or Storage client creation.

## Ingestion functions

Packaged ingestion functions use the same explicit environment/project binding
as the backend, with `TRADVISOR_RUNTIME_TARGET=ingestion`. Their archive
contains `ingestion_configuration.py` and the secret-free source endpoint map
in `config.yml`; every entry point validates both before a source, Storage, or
BigQuery client is used. The required process settings are
`TRADVISOR_INGESTION_SERVICE_ACCOUNT`, distinct
`TRADVISOR_INGESTION_DATA_BUCKET` and `TRADVISOR_INGESTION_ARCHIVE_BUCKET`,
`TRADVISOR_INGESTION_DATASET`, and the fully qualified project-bound tables
for shares, dividends, financials, and ratings. Terraform supplies the named
workload identity and these targets; it rejects an empty or cross-environment
project binding. Do not derive buckets from a project number, discover a
bucket, or substitute a source endpoint at runtime.

## Rule version boundary

Deployment configuration selects service targets and credentials only. It must
not override analytical scoring rules. Rule versions and immutable rule
configuration remain attached to the analytical batch and are changed only at a
publication boundary under the approved calculation contract.
