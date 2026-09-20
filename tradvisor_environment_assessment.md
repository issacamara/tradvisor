# Tradvisor - Development Environment Alignment

**Status:** Read-only assessment; deployment plan proposed, not applied
**Date:** 2026-09-20
**Branch:** `V1` (verified locally; production ancestry stated by stakeholder)
**Target:** `dev-tradvisor`
**Reference:** `prod-tradvisor`

**Follow-up:** [Infrastructure Change Plan](tradvisor_infrastructure_change_plan.md) records the subsequent read-only dependency and state-ownership checks. Its findings supersede the initial unknowns below, including backend prefixes and state ownership. The initial-pass evidence is retained for traceability.

## 1. Scope And Evidence

The stakeholder approved the application architecture and requested development to mirror the production baseline plus V1 additions. This means functional infrastructure parity with isolated identities, configuration and data, not destructive replacement or automatic copying of production users and secrets.

Read-only CLI calls inspected live function metadata, storage bucket metadata, schedules, development workflows and Cloud Run services, production Cloud Asset metadata, development artifact repositories, and BigQuery dataset/table listings. No table rows, bucket objects, secret values, Terraform state contents or user records were read. No jobs, queries, builds, plans, applies, imports, API activation or deployments were run.

Leaf-command help was checked before gcloud execution. Inventory requests explicitly selected their project and projected metadata. Service-specific regional checks covered `europe-central2`, the repository's configured region. Production's narrowed Cloud Asset listing also reported matching resources across the project. This is a useful initial comparison, not a complete project-wide dependency audit or deployment-ready Terraform plan.

Cloud Asset API is disabled in development; service-specific APIs supplied the inventory instead. Firestore API is disabled in both projects, so database existence was not established. No API was enabled. A broad production asset response exceeded the output budget; its contents were not used as an exhaustive inventory. A subsequent narrowed query supplied the production service/workflow/dataset/repository evidence below. Scheduler was read through its own API after its asset type was rejected by Cloud Asset search.

## 2. Observed Environment Differences

| Area | Production evidence | Development evidence | Proposed disposition |
|------|---------------------|----------------------|----------------------|
| Region | Ingestion resources in `europe-central2` | Same inspected region | Reuse regional baseline; verify all V1 service locations before provisioning |
| Core functions | Four shares/dividends scrape/insert functions, Python 3.11 | Same four functions, Python 3.11 | Reuse existing development resources; reconcile configuration and package V1 code |
| Financial functions | `scrape-financials`, `scrape-financials-init`, `insert_financials_function`, all Python 3.11 | Not present in regional function listing | Add development equivalents using existing scripts, preserving explicit name/entry-point mappings |
| Ratings functions | `scrape_ratings_function`, `scrape_ratings_init_function`, `insert_ratings_function`, all Python 3.11 | Not present in regional function listing | Add development equivalents for production baseline parity; do not expand V1 product scope |
| Legacy functions | Bonds/capitalizations absent from inspected production listing | Four bonds/capitalizations functions, Python 3.9 | Preserve; no removal or redeployment until an explicit disposition is approved |
| Workflows | `shares-wf`, `dividends-wf`, `financials-wf`, `financials-init-wf`, `ratings-wf`, `ratings-init-wf` | `shares-wf`, `dividends-wf`, `bonds-wf`, `capitalizations-wf` | Reuse common workflows; add financial/ratings workflows; preserve development-only workflows |
| Scheduler | Six jobs, all enabled; see schedule matrix | Four jobs; bonds paused, others enabled | Preserve current state initially; new development schedules start paused pending verification/activation approval |
| Cloud Run | Narrowed inventory lists ten function-backed services | Eight function-backed services plus standalone `tradvisor` service | Do not manage function-backed services twice; preserve `tradvisor`, add V1 API separately after name checks |
| Storage | `archive-1099228110329`, `data-1099228110329`, `tmp-1099228110329`, managed function-source bucket | Equivalent buckets with suffix `287433769824`, plus managed function-source bucket | Reuse development buckets after policy/configuration comparison; never copy production bucket names into development |
| Terraform state buckets | `prod-tradvisor-tfstate` exists | `dev-tradvisor-tfstate` exists | Keep separate backends; bucket existence does not establish state prefix, resource ownership or completeness |
| Artifact Registry | `gcf-artifacts` and `tradvisor`, both in `europe-central2` | `gcf-artifacts` only in all-location listing | Preserve managed artifacts; propose development `tradvisor` repository for versioned V1 artifacts |
| `stocks` dataset | `europe-central2`; five tables below | `europe-central2`; three legacy tables below | Reuse dataset; explicit schema and naming migration required |
| `trading_dashboard` | Dataset in `EU`, containing `users` | Dataset in `EU`, containing `users` | Preserve, isolate from V1 authentication, no user migration or copying implied |
| Firestore | API disabled; database inventory unavailable | API disabled; database inventory unavailable | Planned V1 dependency; enable/provision only through approved deployment after checks |
| Firebase Auth/Hosting | Not inspected | Not inspected | Planned V1 capabilities; verify existing registration/sites/configuration before adding anything |

Function-backed Cloud Run services are backing resources, not additional independent ingestion components. ACTIVE function/workflow status does not prove successful processing, current source code parity or dependency health.

### Table Names

Production `stocks`: `brvm_companies`, `dividends`, `financials`, `ratings`, `shares`.

Development `stocks`: `BONDS`, `DIVIDENDS`, `SHARES`.

Listings returned fewer than the 100-item limit. Names and table types were inspected, not schema equivalence, row coverage or financial correctness. Preserve uppercase tables until consumers and dataset case-sensitivity configuration are checked. Establish the approved lowercase V1 contracts through an explicit migration or compatibility plan, not implicit renaming, overwrite or dataset recreation. No data copy is authorized. Separately define any bounded market/reference-data seed and its cost before execution.

Production `shares` carries a `source=sikafinance` label, while earlier source descriptions identified BRVM. This is a provenance discrepancy to verify against actual ingestion configuration, not proof of either source's correctness. Production labels indicating Terraform provisioning do not establish that the current V1 Terraform owns those tables.

### Schedule Matrix

| Job | Production | Development |
|-----|------------|-------------|
| `shares-job` | `0 20 * * 1-5`, enabled, Africa/Abidjan | Same expression, enabled, Africa/Bamako |
| `dividends-job` | `0 20 1 * *`, enabled, Africa/Abidjan | Same expression, enabled, Africa/Bamako |
| `financials-job` | `0 6 1 * *`, enabled, Africa/Abidjan | Not listed |
| `financials-init-job` | `0 6 1 1 *`, enabled, Africa/Abidjan | Not listed |
| `ratings-job` | `0 6 5 * *`, enabled, Africa/Abidjan | Not listed |
| `ratings-init-job` | `0 6 2 1 *`, enabled, Africa/Abidjan | Not listed |
| `bonds-job` | Not listed | `0 20 1 * *`, paused, Africa/Bamako |
| `capitalizations-job` | Not listed | `0 20 1 7 *`, enabled, Africa/Bamako |

Observed Scheduler HTTP targets point to workflows in their own project and use project-local service accounts. This is not a transitive guarantee: workflow bodies, function configuration and IAM still require dependency validation. Use the approved Africa/Abidjan convention for V1; schedule definitions and activation are separate settings. Initialization schedules must not trigger automatic development backfills merely to match production.

## 3. Repository Deployment Risks

| Evidence | Impact | Required preparation |
|----------|--------|----------------------|
| `terraform/variables.tf` registers only eight shares/bonds/dividends/capitalizations functions | Current Terraform does not represent the observed production baseline | Reconcile explicit resource inventory and state ownership before extending it |
| `terraform/functions.tf` pairs workflows by list position and fixed `+4` offset | Appending financial/ratings functions can mispair steps | Replace positional pairing with explicit workflow definitions during implementation |
| `terraform/functions.tf` fixes Python runtime to `python39`; core live functions and CI use `python311` | Applying current configuration could regress runtime settings | Select and test a supported runtime; preserve live settings until reviewed migration |
| `terraform/buckets.tf` packages only main/helper/config/requirements | Financial initialization imports and mapping assets can be omitted | Define complete source-specific packages and integration tests |
| `terraform/buckets.tf` sets `force_destroy=true`; `terraform/main.tf` enables dataset content deletion on destroy | A replacement/removal plan could destroy data | Add appropriate protection, review lifecycle changes and refuse unapproved deletions/replacements |
| `terraform/main.tf` manages API enablement with dependent-service disabling allowed | Infrastructure reconciliation can affect unrelated services | Review API ownership/lifecycle; no automatic disabling as part of alignment |
| `terraform/iam.tf` uses role-authoritative project IAM bindings | Applying an incomplete member set can remove existing access | Inventory policy ownership and design least-privilege, additive grants where appropriate |
| `terraform/iam.tf` creates a service-account key with a timestamp keeper, stores it as a secret; `outputs.tf` exposes a sensitive key output | Key churn and sensitive material in state | Prefer keyless deployment/runtime identities; preserve current consumers until an explicit migration is approved |
| `terraform/main.tf` has an empty GCS backend block; README uses placeholders | Correct state bucket/prefix cannot be inferred from default project variable | Verify backend and resource ownership separately for each environment, without exposing state secrets |
| `.github/workflows/ci.yml` validates syntax/Terraform on V1 but does not deploy | Branch ancestry does not provide environment deployment automation | Add separately approved, project-bound deployment workflow with immutable revision identification |
| `deploy.sh` contains Docker login and mostly commented deployment steps | Not a usable V1 deployment pipeline | Do not run; replace or retire through scoped implementation work |

No infrastructure files were modified during this assessment. Existing dirty ingestion files were left untouched.

## 4. Deployment Contract

1. `V1` targets only `dev-tradvisor`; production remains the read-only reference during development alignment. Production promotion is a separately approved operation.
2. Reuse the existing Terraform foundation, with explicit environment inputs and isolated state. Never point development at production state or import one live resource into two owning states.
3. Reconcile existing ownership before import. Start with a reviewed baseline that proposes no unintended changes; then separate production-parity additions from V1 additions in the change plan.
4. Use project-local runtime identities, bucket/dataset references, secrets, callback URLs and authentication settings. Verify workflow and application dependencies, not just top-level project flags. No production write permissions for development identities.
5. Preserve development-only resources and data. No removal is approved by this document. Do not replace the legacy `tradvisor` service in place as a shortcut for deploying V1.
6. Match functional behavior and schemas, not production data volume, user records, historical artifacts or spending. Development schedule activation and capacity may deliberately differ.
7. Deploy V1 frontend, API, analytical publishing, paper-trading store and recovery controls as additions to the approved architecture. Confirm existing resource names and Firebase setup first. Preserve scale-to-zero compute and bounded development processing.
8. Review the eventual infrastructure plan for project targeting, IAM changes, replacements, deletions, runtime changes and cost. This document is not authorization to apply that plan.
9. Rollback uses prior versioned application artifacts and compatible schemas. It must not restore production data into development, destroy the development dataset, replay paper orders or bypass the approved recovery contract.

## 5. Remaining Verification Before Deployment

- Delivery team: complete all-region/service coverage and inspect metadata for IAM, enabled APIs, Firebase, event triggers, build/deployment triggers, bucket policies, secrets references and workload capacity. No secret values needed.
- Delivery team: verify workflow bodies and dependency references with value-safe inspection, BigQuery schemas/case sensitivity and relevant view dependencies, and the actual source associated with the production `shares` label.
- Infrastructure owner: verify backend prefixes and resource addresses through a sensitive-state-safe process; reconcile existing ownership before import or planning.
- Delivery team: account for the legacy `tradvisor` service and `trading_dashboard.users` consumers. Preserve them unless an explicit migration/retirement is approved.
- Product/infrastructure owner: approve development schedule activation, any bounded data seeding, Firebase identity setup and the final resource change/cost plan.
- Delivery team: execute integration, isolation and recovery tests after authorized implementation. No passing test or completed parity is claimed here.

## 6. Recommended Sequence

Complete the remaining metadata/ownership checks, then prepare an environment-aware Terraform change set without applying it. Review the baseline alignment first, then the V1 resource additions. Deploy only after explicit plan approval. Application component boundaries and financial rules remain unchanged.
