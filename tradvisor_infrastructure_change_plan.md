# Tradvisor - Infrastructure Change Plan

**Status:** PROPOSAL; preparation plan only, not a Terraform execution plan
**Date:** 2026-09-20
**Target:** `V1` in `dev-tradvisor`
**Reference:** `prod-tradvisor`, read-only
**Inputs:** [Environment assessment](tradvisor_environment_assessment.md), [filtered state ownership](tradvisor_infrastructure_ownership.json), [architecture](tradvisor_architecture.md)

## 1. Recommendation

Reconcile the existing development Terraform configuration with its own state first, preserving legacy resources. Then add production-parity ingestion resources and the approved V1 application resources in separate reviewed changes. Do not replace development Terraform wholesale with production Terraform, copy production state, or apply the current V1 configuration as it stands.

No infrastructure configuration, backend, state or cloud resource was changed in this assessment. No Terraform init/plan/apply/import, pipeline execution, data copy or secret access API was executed. State JSON was processed in memory solely to emit resource addresses and selected non-secret resource IDs; raw state, resource secret attributes and state outputs were not printed or saved. The JSON evidence is a filtered ownership snapshot, not a reusable state file.

## 2. Verified Ownership

| Environment | Backend bucket | Prefix / workspace | State snapshot | Managed instances |
|-------------|----------------|--------------------|----------------|-------------------|
| Development | `dev-tradvisor-tfstate` | `tradvisor/V1` / `default` | Serial 210, Terraform 1.10.2 | 67 |
| Production | `prod-tradvisor-tfstate` | `state/prod` / `default` | Serial 1532, Terraform 1.9.8 | 88 |

These are the current state objects listed in the two known buckets on the assessment date. Other buckets, historical states and external owners were not exhaustively enumerated. Recheck serials and ownership before preparing an executable plan; these snapshots do not lock state or prove live existence.

Development already owns its dataset, three ingestion buckets, eight functions, four workflows, four schedules and legacy web service. No import is needed for those resources at their current addresses. Production owns five lowercase BigQuery table resources; development's inspected state owns none of its individual tables. Existing development tables must not be silently adopted or deleted.

### Preservation Blocker

Development state contains the following addresses absent from current V1 configuration:

- `google_cloud_run_v2_service.tradvisor_service`
- `google_cloud_run_service_iam_policy.noauth`
- `google_secret_manager_secret.bigquery_creds`
- `google_secret_manager_secret.tradvisor_gmail_acc`
- `google_service_account.brvm_dashboard_sa`

Their omission can lead Terraform to propose deletion. Restore ownership declarations compatible with current live configuration before a full plan, or separately approve an explicit ownership transfer that does not destroy the resources. Simply adding `prevent_destroy` elsewhere or leaving the resource absent is not a preservation strategy. The recommended V1 path is to retain ownership and preserve them; no state removal or transfer is authorized here.

The local `production` ref still has `terraform/service.tf`, `terraform/workflows.tf` and `.github/workflows/deploy.yml`, absent from V1. Reuse relevant definitions as source material, not as a wholesale replacement. State structures differ: development has 13 project IAM binding resources, while production has 18 project IAM member resources; workflow and scheduler addresses also differ.

Production state records `google_cloud_run_v2_service.tradvisor_service` as the `prod-tradvisor` service in `europe-central2`. A direct live describe returned “Cannot find service.” Do not recreate this production service or mirror it into development just because it appears in state. The existing development `tradvisor` service was observed live in the first assessment and remains protected.

## 3. Dependency Results

| Check | Observed result | Consequence |
|-------|-----------------|-------------|
| Development workflow endpoints | Four workflows reference their matching development Cloud Run endpoints and development service account | Preserve these dependencies; inspected source contains no dynamic expressions, but runtime data/config dependencies still need integration tests |
| Production workflow endpoints | Six workflows reference production Cloud Functions endpoints and production service account | Rebuild development references from development resource outputs, never literal production URLs |
| Financial workflow shape | Daily/monthly financial workflow calls `scrape-financials`; initialization calls `scrape-financials-init` then `insert_financials_function` | Model the two paths explicitly, not a generic two-step rule |
| Ratings workflow shape | Regular and initialization workflows each call their respective scraper; neither inspected workflow lists `insert_ratings_function` | Preserve observed shape initially; validate actual persistence path before activating it, without assuming every deployed loader is invoked by a workflow |
| Function capacities | Core shares functions: 512 MiB, 180 s, max 1 instance; regular financials: 512 MiB, 300 s; financial initialization/insertion: 4 GiB, 600 s, max 1 | Use per-function settings rather than the repository's global 512 MiB/180 s definition; tune only with tests, no extraction benchmark prerequisite |
| Selected function runtime | All selected core/financial/ratings descriptions report Python 3.11 and `entry_point` | Do not revert these functions to the V1 Terraform's Python 3.9 setting |
| Secret references | Selected function descriptions do not return secret-environment bindings; existing financial code expects `OPENROUTER_API_KEY` | Absence of bindings is not proof of missing credentials: plaintext environment values were deliberately not requested. Configure development through secret references, populated separately; never copy production values |
| IAM | Both project policies include project-local `github-actions-sa` and ingestion identities; no opposite-project identity was observed in those direct project bindings | Reuse identity candidates only after trust checks; inherited IAM, resource policies, groups and impersonation were not assessed, so full isolation is not yet proven |
| IAM breadth | Existing deployment identities have broad admin roles; runtime identities have storage/run admin and project-wide secret access | Do not clone these broad grants for new V1 workloads. Separate API, batch, ingestion and deployment permissions; migrate old grants only with a reviewed consumer-safe plan |
| Build triggers | Empty Cloud Build trigger lists in `global` and `europe-central2` for both projects | Do not assume Cloud Build triggers deploy V1; reuse/adapt the production-branch GitHub workflow after inspecting its auth/branch targeting |
| Enabled APIs | Core ingestion APIs enabled in both; Firebase management/Hosting, Identity Toolkit and Firestore absent from returned enabled lists | Enabling V1 dependencies belongs to a separately approved deployment; no Firebase setup or empty database is inferred from this result |
| Backend protection | Both state buckets have 7-day soft delete, uniform bucket-level access disabled, public-access prevention marked inherited. Development explicitly reports versioning enabled; production returns no versioning field | Verify effective ACL/IAM protection before policy changes; do not claim state buckets are public or equivalently protected from these fields alone |

Missing `minInstanceCount` and `eventTrigger` fields in selected descriptions are not treated as proof of explicit zero-minimum configuration or complete trigger absence. Inspect effective backing-service settings during deployment preparation without exposing environment values.

### Data Compatibility

Both `stocks` dataset metadata responses report `europe-central2` and 168-hour time travel. Neither returned an explicit `isCaseInsensitive` field; preserve the observed uppercase/lowercase distinction and confirm effective behavior before creating tables.

Development `SHARES` has nullable uppercase fields, `DATE: STRING` and `SYMBOL: STRING` nullable. Production `shares` has `date: DATE` and `symbol: STRING` required. OHLC and volume are FLOAT in both observed schemas. This is a schema migration, not just a name change. It does not override the exact-money contract for the V1 application ledger.

Create the lowercase development contract separately, validate date parsing and required symbols through fixtures, and retain the uppercase table and its consumers. No historical rows were inspected and no backfill is approved. Remaining source table schemas should be captured as metadata-only fixtures before their IaC definitions are implemented. The earlier `source=sikafinance` label discrepancy remains provenance verification, not a basis for changing the approved financial rules.

## 4. Ordered Change Sets

| Order | Change set | Concrete scope | Acceptance before proceeding |
|-------|------------|----------------|------------------------------|
| 0 | Preserve development ownership | Restore missing legacy declarations; pin exact development backend inputs; guard project selection; preserve existing resource addresses and current scheduler pause states | Reviewed eventual full plan contains no unapproved legacy destruction, replacement, key rotation or IAM member removal |
| 1 | Reconcile ingestion baseline | Per-function runtimes/packages; explicit workflow definitions; retain existing four workflow indices and four scheduler keys; add six financial/ratings functions, four workflows and four schedules | Packages contain initialization modules/mapping assets; endpoints and identities resolve only within development; new schedules paused |
| 2 | Add source-table contracts | Five lowercase source tables in existing development `stocks`; preserve uppercase tables and `trading_dashboard.users`; reuse production schema definitions only after metadata verification | No dataset recreation, implicit rename or user migration; schema/loader tests pass; any data seed is separately approved |
| 3 | Add V1 platform resources | Development artifact repository if still absent, approved static frontend/auth integration, API, batch publication, Firestore application state and independent recovery register | Existing names checked; service locations compatible; narrowly scoped identities; API/secret provisioning approved; scale-to-zero and cost controls verified |
| 4 | Restore development delivery automation | Adapt production GitHub workflow to V1 and explicit development backend/project; immutable artifacts; isolated deployment identity and reviewed plan approval | Branch-to-project guard and auth trust tested; production credentials/backend unavailable to development execution; no automatic apply from pull requests |
| 5 | Validate and activate | Functional, contract, cross-project isolation and recovery tests; review resource cost and development schedules | Explicit approval of executable infrastructure plan and any schedule activation/data seeding; no production changes |

This is a file/resource-level work plan, not an actual `terraform plan` result. No numerical add/change/destroy count is claimed. Resources mentioned as additions still require collision checks at execution time.

### Address Preservation

Keep `google_bigquery_dataset.stocks`, the existing bucket addresses and the eight `google_cloudfunctions2_function.functions[...]` addresses during baseline reconciliation. For existing workflow instances, keep this mapping stable:

| Current address | Live workflow |
|-----------------|---------------|
| `google_workflows_workflow.workflows[0]` | `shares-wf` |
| `google_workflows_workflow.workflows[1]` | `bonds-wf` |
| `google_workflows_workflow.workflows[2]` | `dividends-wf` |
| `google_workflows_workflow.workflows[3]` | `capitalizations-wf` |

Keep existing scheduler keys `job1` through `job4` mapped to shares, bonds, dividends and capitalizations respectively. New workflows/schedules should use separately named resources or stable keys without shifting existing indices. A later address refactor requires explicit reviewed moved mappings; changing names to resemble production is not itself a reason to recreate a resource.

Do not layer project IAM member resources for a role onto an authoritative binding still managed elsewhere without reconciling ownership. Keep existing members intact while planning least-privilege migration. Do not import backing Cloud Run services already owned through function resources into a second Terraform resource.

## 5. Executable-Plan Boundary

An executable Terraform plan should be prepared only after change set 0 is represented safely in code. Use a dedicated development working directory/backend configuration rather than relying on the repository's existing `.terraform` initialization. Verify current state serial, ownership and identity first; retain locking and serialize infrastructure work. Treat plan files as sensitive artifacts, never publish raw plan JSON or state in CI logs.

A plan is rejected if it targets production, removes legacy declarations, deletes/recreates data stores, rotates existing keys unexpectedly, removes required IAM principals, enables paid processing implicitly, or schedules initial backfills without approval. Apply requires approval of the concrete reviewed plan, not just this document. Production state remains untouched even where stale entries were observed.

Remaining checks are bounded implementation prerequisites, not new product decisions: metadata fixtures for remaining tables; value-safe dependency/configuration validation; GitHub identity federation/trust; effective resource-level IAM; Firebase registration/site/database checks after approved API setup; and compatible service locations. Complete other-region discovery if deployment scope expands beyond the observed ingestion region. No passing tests or full project-wide audit is claimed.

## 6. Immediate Next Work

Orchestrate this work under architecture v1.0 section 13. Change set 0 is an early infrastructure implementation task, not a prerequisite to backlog creation or independent fixture-based application work. Implement it as a local, reviewable Terraform configuration change without deployment; reuse relevant production-branch code selectively and preserve all current development-owned resources. Then prepare and review the development-only Terraform plan before adding or activating resources. No Terraform edit or deployment was performed by architecture finalization.
