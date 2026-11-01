# FI-1 cutover verification record

Status date: 2026-11-01

Integration branch: `development`

Current integration commit: `80eec3e3ed0dec2c1a888b65110c4581bc887ce9`

This record contains public, sanitized evidence only. It contains no cloud resource inventory, credentials, source documents, extracted values, prompts, or provider responses.

## Merged implementation and release evidence

| Evidence | Result |
|---|---|
| #363 infrastructure | Present in `development` history as `e0520ad`; private Job and monthly trigger are declared with activation disabled by default. |
| #364 release integration | PR [#371](https://github.com/issacamara/tradvisor/pull/371) merged at `87045ed9882ed11845c0e074750801b17d1835e0`. Successful development workflow [41324856354](https://github.com/issacamara/tradvisor/actions/runs/41324856354) passed `validate`, `frontend`, `release`, and `delivery`. |
| #364 immutable release evidence | The successful #364 release produced a manifest bound to its merged commit, with one immutable FI-1 image digest. The digest value and artifact reference are withheld from this public record as restricted infrastructure evidence. |
| Development image binding | The #364 development delivery completed successfully, and its release configuration verified the manifest-bound FI-1 image identity. Exact deployment and artifact details are withheld from this public record. |
| #365 retirement | PR [#372](https://github.com/issacamara/tradvisor/pull/372) merged at current integration commit `80eec3e3ed0dec2c1a888b65110c4581bc887ce9`. Its owner review checklist is recorded on PR head `c8fa3bd2b5d1f2fca7445318d13820dd5f6da2f9`. The review came from the shared `issacamara` account; this is owner review evidence, not an independent GitHub approval. |
| #365 PR verification | CI [41341568806](https://github.com/issacamara/tradvisor/actions/runs/41341568806) and Terraform plan [41341568762](https://github.com/issacamara/tradvisor/actions/runs/41341568762) passed for PR head `c8fa3bd2b5d1f2fca7445318d13820dd5f6da2f9`. |
| Current integration verification | Development CI [41341926311](https://github.com/issacamara/tradvisor/actions/runs/41341926311), for `80eec3e3ed0dec2c1a888b65110c4581bc887ce9`: `validate` and `frontend` passed; `release` was canceled before completion; `delivery` was skipped. Development Terraform plan [41341926239](https://github.com/issacamara/tradvisor/actions/runs/41341926239) passed. No apply or deployment completed for #365. |

The #364 checks establish that its immutable FI-1 release identity was bound to development configuration; its value and delivery artifact details remain in restricted owner-controlled evidence. This does not establish that the later #365 retirement commit `80eec3e…` was released or applied. The #365 current-head release and delivery remain unverified because their jobs did not complete.

## Offline acceptance evidence map

Run the listed offline checks against the candidate integration head before cutover. These exercise fixtures and static configuration only; they do not call a provider or mutate cloud data.

| FI-1 area | Offline evidence |
|---|---|
| Source parsing, extraction validation, model fallback and bounded attempts | `tests/ingestion/financial_pipeline/test_fi1_contracts.py`, `tests/ingestion/financial_pipeline/test_fi1_job_runtime.py` |
| State read, staging, MERGE ordering, idempotency and failure behavior | `tests/ingestion/financial_pipeline/test_fi1_job_runtime.py` |
| No source/extraction persistence and sanitized completion | `tests/ingestion/financial_pipeline/test_fi1_job_runtime.py`, `tests/infrastructure/financials/test_fi1_job.py` |
| Locked packaging and release digest/config binding | `tests/ci/test_delivery_inputs.py`, `tests/infrastructure/release/test_manifest.py`, `tests/packaging/test_cloud_only_ingestion.py` |
| Terraform identity, limits, one active trigger and managed tables | `tests/infrastructure/financials/test_fi1_job.py`, `tests/infrastructure/financials/test_financials_runtime_identity.py`, `tests/infrastructure/workflows/test_direct_schedule_inventory.py` |
| Legacy retirement and archive/revision preservation | `tests/infrastructure/financials/test_fi1_job.py`, `tests/packaging/test_function_archives.py`, `tests/packaging/test_cloud_only_ingestion.py` |

The existing FI-1 acceptance behaviors are covered by these offline suites. Measured runtime completion and real source/provider behavior are not established by fixture tests; collect them only during the separately approved development verification below.

Local #366 verification ran with Python 3.12.3: 107 tests passed across the listed parser/runtime, Terraform, release, packaging, retirement, and cutover-record suites. The repository CI remains authoritative and uses its pinned Python 3.11.11 runtime.

The broader local `python3.12 -m pytest tests -q` run completed with 731 passed, 5 failed, and 5 errors. The unrelated failures were four API chart tests unable to import `google.cloud.bigquery`, one OpenAPI generated-file comparison differing in integer/float JSON formatting, and five Firestore emulator tests blocked from binding a loopback socket by this host. None touches the #366 files; the focused FI-1 suites above all pass.

## Owner-facing development verification gate

Use the following checklist only after separate owner approval for development deployment and execution. Record sanitized workflow/run identifiers and pass/fail outcomes; do not attach raw logs, source files, extracted content, prompts, provider responses, credentials, or private infrastructure inventory.

- [ ] Confirm the exact `development` commit, release-manifest commit, and one `fi1_job.digest`; confirm the development configuration resolves that digest without a mutable tag.
- [ ] Confirm there is one declared automated financial trigger: the monthly Scheduler targets the FI-1 Cloud Run Job directly; no financial Workflow or legacy Function trigger is configured. Record activation separately because it requires owner approval.
- [ ] Confirm one active execution for the verification run.
- [ ] Confirm RichBourse request concurrency never exceeds four.
- [ ] Confirm the current selector completes within 60 minutes.
- [ ] For a successful changed run, confirm exactly one state read and one staged `MERGE` precede successful completion publication.
- [ ] Confirm no source document, extracted text/value, prompt, provider response, or extraction evidence was persisted.
- [ ] Confirm historical source archives and annual-financial revision assets remain preserved.
- [ ] Confirm the job reports completion/failure without a legacy automated financial trigger.
- [ ] Record the workflow, Terraform plan and sanitized verification result against the exact commit and image digest.

Required approvals remain separate: development Terraform apply/deployment, FI-1 schedule activation, any paid provider call or BigQuery query, and production promotion. Production promotion requires a human to review and approve the same immutable image digest; no production action is authorized by this record. Schedule activation and provider/query execution are not part of this verification checklist unless separately approved.
