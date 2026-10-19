# V1 Pilot Acceptance and Activation Decisions

## Decision Summary

**Pilot release decision: NO-GO pending owner acceptance of missing evidence.**

The implementation and contract gates are delivered, but this record does not silently convert absent live/operator evidence into approval. The application may remain a private development artifact. No production deployment, data seed, schedule activation, or public launch is authorized by closing this issue. Those actions are not authorized here.

## Completion-driven publication evidence

Issue [#258](https://github.com/issacamara/tradvisor/issues/258) verifies the completion-driven publication amendment with credential-free integration evidence. The matrix covers changed shares and financial inputs, ratings and failed imports, debounce coalescing, duplicate delivery, concurrent dispatch claims, bounded analytical retries, and the timing evidence emitted by the serialized control seam:

- `tests/integration/test_completion_driven_publication.py`
- `tests/workflow_dispatcher/test_publication_control.py`
- `tests/publication/analysis/test_analysis.py`
- `tests/jobs/test_daily.py`
- `tests/api/test_app_contract.py`
- `frontend/src/app/swing/page.test.tsx`
- `frontend/src/features/swing/chart-state.test.ts`

These checks are offline and sanitized. They do not activate schedules, execute a batch, call providers, run paid queries, access production state, or make request-time BigQuery calls. The existing immutable publication tests establish that a partial or failed replacement cannot displace the previous complete active batch; the API and frontend tests establish distinct chart-local and publication-wide unavailable states.

## Twelve-Factor engineering audit

This audit is limited to public, merged V1 implementation evidence. It does not
claim a live deployment, a production control, a financial-effectiveness result,
or an independent review approval. The exact integration-head CI evidence is
[V1 CI run 38973133406](https://github.com/issacamara/tradvisor/actions/runs/38973133406)
for commit `0303f5f8a19e566ebdd8d96e3e53307c2058147b`; both `validate` and
`frontend` completed successfully.

| Factor | Status | Public evidence |
| --- | --- | --- |
| 1. Codebase | PASS | One canonical repository and V1 integration branch; the delivery workflow builds from the checked-out commit. |
| 2. Dependencies | PASS | [#221](https://github.com/issacamara/tradvisor/pull/237) locks backend resolutions; [#225](https://github.com/issacamara/tradvisor/pull/241) locks packaged ingestion; [#226](https://github.com/issacamara/tradvisor/pull/243) pins delivery tools and verifies drift. |
| 3. Config | PASS | [#217](https://github.com/issacamara/tradvisor/pull/233) validates runtime targets and safe examples; [#218](https://github.com/issacamara/tradvisor/pull/234) applies the shared contract to ingestion. |
| 4. Backing services | PASS | [#219](https://github.com/issacamara/tradvisor/pull/235) declares protected staging; [#220](https://github.com/issacamara/tradvisor/pull/236) serves charts from published batches; [#223](https://github.com/issacamara/tradvisor/pull/239) and [#224](https://github.com/issacamara/tradvisor/pull/240) use run-scoped managed staging. |
| 5. Build, release, run | PASS | [#228](https://github.com/issacamara/tradvisor/pull/245) creates the immutable release manifest; [#230](https://github.com/issacamara/tradvisor/pull/247) requires verified artifacts and the exact reviewed Terraform plan. |
| 6. Processes | PASS | [#229](https://github.com/issacamara/tradvisor/pull/246) verifies restart-safe cloud ingestion and publication without local durable state. |
| 7. Port binding | PASS WITH LIMITATIONS | The existing API process exposes its configured service interface and the configuration contract is validated; no live deployment evidence is claimed here. |
| 8. Concurrency | PASS | Run-scoped staging and immutable publication/retry evidence are covered by [#223](https://github.com/issacamara/tradvisor/pull/239), [#224](https://github.com/issacamara/tradvisor/pull/240), and [#229](https://github.com/issacamara/tradvisor/pull/246). |
| 9. Disposability | PASS | [#229](https://github.com/issacamara/tradvisor/pull/246) covers process replacement, retries, and preservation of the last complete active batch. |
| 10. Development/production parity | PASS WITH LIMITATIONS | [#228](https://github.com/issacamara/tradvisor/pull/245) records target-bound artifacts and fingerprints; no production deployment or byte-identical rebuild claim is made. |
| 11. Logs | PASS | [#222](https://github.com/issacamara/tradvisor/pull/238) emits sanitized JSON stdout events and [#227](https://github.com/issacamara/tradvisor/pull/244) wires them into runtime failure paths. |
| 12. Admin processes | PASS | [#231](https://github.com/issacamara/tradvisor/pull/248) packages same-release admission/recovery commands with stable operation IDs, fencing, sanitized output, and nonzero failure exits. |

### R1–R7 contract evidence

| Requirement | Result | Consumed and exposed evidence |
| --- | --- | --- |
| R1 — locked dependencies and reproducible calculations | PASS | Consumes the backend and packaged-ingestion locks; exposes pinned toolchains, image digest, and lock-drift checks through [#221](https://github.com/issacamara/tradvisor/pull/237), [#225](https://github.com/issacamara/tradvisor/pull/241), and [#226](https://github.com/issacamara/tradvisor/pull/243). |
| R2 — external validated configuration | PASS | Consumes explicit environment inputs; exposes fail-closed target validation and secret-free examples through [#217](https://github.com/issacamara/tradvisor/pull/233) and [#218](https://github.com/issacamara/tradvisor/pull/234). |
| R3 — immutable complete serving batches and bounded reads | PASS | Consumes Terraform-owned staging and the [#171 publication artifact](https://github.com/issacamara/tradvisor/pull/176); exposes managed staging and published-batch chart reads through [#219](https://github.com/issacamara/tradvisor/pull/235), [#220](https://github.com/issacamara/tradvisor/pull/236), [#223](https://github.com/issacamara/tradvisor/pull/239), and [#224](https://github.com/issacamara/tradvisor/pull/240). |
| R4 — build/release/run separation | PASS | Consumes locked inputs and explicit environment settings; exposes the immutable release manifest and exact reviewed-plan handoff through [#228](https://github.com/issacamara/tradvisor/pull/245) and [#230](https://github.com/issacamara/tradvisor/pull/247). |
| R5 — stateless processes and DuckDB retirement | PASS | Consumes cloud-owned canonical/publication state; exposes cloud-only restart/retry behavior through [#229](https://github.com/issacamara/tradvisor/pull/246), with the earlier cloud-only retirement artifacts retained on V1. |
| R6 — structured sanitized telemetry | PASS | Consumes the existing operational event contract; exposes bounded JSON stdout and failure-path sanitization through [#222](https://github.com/issacamara/tradvisor/pull/238) and [#227](https://github.com/issacamara/tradvisor/pull/244). |
| R7 — trusted same-release administration | PASS | Consumes validated settings, release image, safe events, and existing admission/recovery interfaces; exposes packaged commands, stable operation IDs, explicit targets, fencing, and nonzero failure exits through [#231](https://github.com/issacamara/tradvisor/pull/248). |

The engineering evidence above is complete for the merged V1 wave, subject to
the limitations stated in each row. The unresolved items below are release
acceptance gates, not reasons to invent evidence or authorize operations.

## Gate Matrix

| Gate | Evidence | Status | Required owner/operator action |
| --- | --- | --- | --- |
| API, analytical publication, ingestion and recovery contracts | Merged V1 implementation plus CI and regression tests | PASS | None for code gate |
| Source/company coverage | `docs/validation/coverage.md` and focused tests | PASS WITH LIMITATIONS | Accept visible partial/unavailable states |
| Financial rule effectiveness | `docs/validation/effectiveness.md`; offline known-at evaluator | BLOCKED | Review an approved holdout report before actionable publication |
| Accessibility | `docs/validation/accessibility.md`; automated checks | BLOCKED | Named operator runs keyboard and screen-reader checks and records results |
| Restore/recovery | `docs/validation/restore.md`; reconciliation tests | BLOCKED | Approve isolated development target and execute the drill |
| Performance and placement | `docs/validation/performance.md`; offline benchmark | BLOCKED | Approve bounded development load measurement |
| Cost | `docs/validation/cost.md` | BLOCKED | Accept measured development cost evidence and assumptions |
| Privacy/advisory scope | `docs/validation/compliance.md` | PASS WITH LIMITATIONS | Keep V1 private, invited-group, informational |
| Monitoring | `docs/operations/monitoring.md`; opt-in Terraform declarations | PASS WITH LIMITATIONS | Name destination/operator and separately approve activation |

## Named Decisions Required

Before pilot acceptance, record the owner’s decision on: (1) whether the missing live gates are accepted as blockers, (2) the named operator/support contact for the pilot, (3) whether private invited-group testing may begin in development, and (4) whether any deployment, seed, or schedule activation request should be prepared. These are separate decisions; none is implied by this document or by issue closure.

## Separate Activation Requests

| Request | Default state | Separate approval needed |
| --- | --- | --- |
| Deploy the static frontend/API to development | Not requested | Yes, with target project and image/source evidence |
| Seed or copy data/users/secrets | Prohibited by current scope | Yes, explicit resource and data-safety approval |
| Activate ingestion/publication schedules | Paused | Yes, named schedule, window, retry and cost ceiling |
| Run isolated restore drill | Not executed | Yes, isolated target, operator and cleanup plan |
| Public or commercial launch | Out of V1 scope | New product/compliance decision |

## Release Record

At the time of this record, no operator/support name, live holdout report, accessibility session record, restore drill evidence, approved load measurement, or measured cost report is present in the public repository. Private infrastructure evidence must remain local and must not be copied here.
