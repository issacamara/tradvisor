## Public Baseline: Architecture (3/3)

- Deployment: V1 targets the existing development environment. Preserve existing resources and isolate configuration, identities, state and data. Use production as a read-only functional baseline. New schedules remain paused until dependency/cost checks and separate activation approval. Restricted infrastructure evidence is available only to authorized operators; do not publish it in issues or logs.
- Observability: track ingestion failures, publication age, execution failures, and processing cost. These are operational controls, not a user-facing data-quality module.

**Approved operating baseline (2026-09-20, NFR-07 through NFR-09):** 25 invited users, 5 concurrent sessions, 95th-percentile normal API reads within 2 seconds excluding cold start and network transit, and shared daily analysis published within 15 minutes after required market inputs are ready. Source delays retain the last published results with their effective date. Validate load and batch targets with representative tests; these are accepted requirements, not measured results.

- Availability: best-effort pilot, no overnight support or contractual uptime guarantee. Recovery target is within 24 hours of incident acknowledgement; no incident-to-acknowledgement guarantee is implied. Data-loss relaxation approved 2026-09-20: recover from the latest successful usable daily backup; changes after that recovery point may be lost, with no fixed maximum loss guarantee. Report the actual recovery point and potential lost-change interval; if no usable backup exists, explicitly report recovery unavailable. Daily backups, 7-day retention and mandatory reset/access-removal protections remain unchanged.
- Backup mechanism (approved 2026-09-20): Firestore managed daily backups retained for 7 days, plus a private Cloud Storage recovery register preserving reset exclusions and access-removal decisions independently of database restores. Restore into an isolated database; reapply register decisions, current admission and separately maintained security/retention configuration; reconcile orders/balances/receipts before reopening access or workers. The register belongs to the Application Store component, not a new service. Cost validation and a successful restore drill remain release gates, not completed work. Monitor backup age and failed/overdue backups.
- Reset failure handling: validate and persist an independent restrictive intent, transactionally revalidate/fence the affected generation, confirm the ordered exclusion under the same operation ID, then finalize the new generation and command receipt. Report success only after both stores are confirmed. Cross-store writes are not atomic; interrupted/ambiguous operations stay blocked and resume under the same operation ID. Recovery never exposes an excluded generation even if the final reset transaction was lost. Access removal follows equivalent durable protection before reporting administrative success. API/data contract section 10 specifies the failure-handling design, verification and approved register lifecycle and completeness/access-ordering integration.
- Analytical retention: retain 12 months of published recommendations and their source/configuration/version evidence. Preserve longer source history needed by active calculations, warm-up, financial windows or active simulation references; the recommendation cutoff is not a blanket source-history cutoff. Scarce financial history must not be deleted simply because a calendar year changes.
- Paper retention: retain all active-generation history. Reset makes the previous generation inaccessible immediately and schedules operational deletion within 7 days. Backup copies expire within their separate 7-day retention. Restore into an isolated environment, reapply durable reset exclusions and current admission restrictions, and only then reopen access. The exclusion mechanism must survive loss of the primary state; if it cannot be established, keep affected accounts inaccessible rather than exposing a pre-reset generation. Implement the approved completeness/access-ordering protocol and test the mechanism before release; the relaxed data-loss target does not authorize resurrection of reset history.
- Idempotency receipts: retain minimal command identity, payload fingerprint and outcome metadata for 30 days, outside reset generations without retaining cleared trade details. The supported retry window is 30 days within the current recovery identifier; restoration invalidates old commands before receipt replay. The approved five-minute first-submission window and logical receipt expiry prevent expired retries from becoming fresh mutations; implement the API contract's timestamped key and rejection checks. Generation fencing remains mandatory regardless of receipt expiry.
- Logs: retain operational logs for 30 days, excluding passwords, tokens and unnecessary personal data. Verify lifecycle deadlines and restore behavior in tests. These periods are operational decisions, not claims about legal obligations.

The cost priority remains minimizing total operating cost with scale-to-zero compute, using EUR 5/month as an indication rather than a guaranteed bill. Measure actual operating costs of the reused financial-report pipeline, backups and whole stack during integration; no new extraction benchmark or allowance is an architecture prerequisite; approved recovery targets require cost validation and a restore drill before release.

Official references for the revised cost and execution direction: [BigQuery computation optimization](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute), [BigQuery cost controls](https://docs.cloud.google.com/bigquery/docs/best-practices-costs), [BigQuery window functions](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/window-function-calls), [Cloud Run autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling), [Firestore transactions](https://firebase.google.com/docs/firestore/manage-data/transactions), and [Next.js static export](https://nextjs.org/docs/app/guides/static-exports). Product documentation supports capabilities, not a measured Tradvisor monthly cost; no workload benchmark or billing audit has been run.

### Approved Correction And Recovery Package

**Integration baseline approved 2026-09-20:** Integration Design v1.0 (companion baseline document) is part of this architecture. Its sections 2-4 specify the accepted officialization-plus-60-seconds cutoff, transactionally guarded execution-price publication and restrictive-intent-first recovery protocol. These supersede earlier timing placeholders and fence-first ordering. BigQuery retains analytical history; compact immutable execution revisions and calendar/publication/runtime control records belong to Application Store. Register intents and predecessor-checked decision heads remain within the existing private recovery register. No new component is introduced. Its verification matrix is mandatory delivery work, not passing test evidence.

Approved 2026-09-20; detailed contract in API/data contract sections 5, 6 and 10:

- A verified calendar correction changing a pending order's intended session or expiry deadline rejects that order and releases its reservation; replacement requires fresh confirmation. Do not silently reschedule orders.
- Execution selects the latest then-available validated intended-session price revision committed by the deadline. Never use a known-invalid revision without an eligible replacement. Preserve completed executions and their evidence; record later corrections for operator review, without automatic repricing.
- Retain minimal reset exclusions until no backup, restored database or other restorable copy can resurrect excluded history. Unproven cleanup eligibility means retention. Keep access restrictions until explicitly superseded by a newer authorized decision; never let a restored allowlist re-admit someone.
- Each restoration establishes a new recovery identifier, independently registered and enforced before receipt replay or mutation. Fence old workers and reject old client commands, including otherwise fresh keys. Refresh and explicit confirmation are required; no automatic replay with a new identifier.
- Before reopening, reconcile surviving state, reject restored pending orders and release surviving reservations once. Do not infer lost executions or reconstruct cash movements. Inconsistent accounts remain blocked; surviving terminal orders remain terminal. Report the actual recovery point and possible lost-change interval.
- Nominate one technical operator for calendar exceptions, pipeline failures, backup alerts and recovery. The stakeholder is product owner for coverage acceptance, measured-cost review and launch approval. Name the operator and support contact before launch. Best-effort support and the acknowledgement-based recovery target remain unchanged.
- Passing calculation/contract tests, a restore drill, company/sector coverage review and a whole-stack cost estimate are mandatory release checks, not completed evidence. No new service, automatic trading or real-portfolio tracking is introduced.

Trade-off accepted: exceptional corrections and restoration can require users to resubmit paper orders rather than changing or replaying their original instructions silently. Session-completion rules, race-safe publication and register completeness/access ordering are now approved in the integration baseline; no extraction benchmark or allowance decision remains an architecture prerequisite; section 11 records approved company-reference and accessibility choices.

## 10. Alternatives Considered & Trade-offs


| Option | Pros | Cons | Decision | Driver |
|--------|------|------|----------|--------|
| Shared signals plus personalized holding advice | Uses actual simulated entry and holding context for exits | Two related result types must be clear in the UI | Confirmed by stakeholder | Exit rules need position context |
| Sector-aware fixed Long-Term scorecard | Explainable rules with appropriate bank, insurer and non-financial interpretation | Requires category-specific metric/input definitions | Option 2 selected for V1; universal scorecard and percentile-based alternatives not selected | Growth attractiveness and sustainable dividend research without misleading cross-sector comparisons |
| Balanced exit baseline: 5% loss, +8% activation, 4% trailing decline, technical deterioration, 30 sessions | Combines loss alerts, profit giveback control and trend confirmation | Fixed percentages are volatility-sensitive; confirmation and manual execution delay exits | Selected as provisional V1 evaluation baseline; fast and patient alternatives not selected | Explainable Swing paper-position advice |
| One universal Buy/Keep/Sell result without holding context | Simple list | Entry-dependent exits cannot be evaluated for an unheld stock | Rejected in discussion | FR-SW-01, FR-SW-06 |
| Reuse production ingestion code and improve its operational behavior | Four BRD datasets already have extraction/loading implementations | Company-reference enrichment is incomplete; contract and deployment fixes remain | Confirmed location and direction | Stakeholder decision |
| Reuse model-assisted financial extraction with saved artifacts | Preserves existing PDF handling and limits repeated extraction work | Adds provider cost, credentials, and nondeterministic extraction | Selected reuse adaptation | NFR-02 and financial-source coverage |
| Build every ingestion adapter again | Uniform new implementation | Duplicates existing work | Not selected | Reuse-first constraint |
| Application modules with separate scheduled jobs | Few deployment boundaries and shared domain logic | Requires clear internal module ownership | Selected | Small invited group |
| Independently deployed service for every domain | Independent scaling and releases | Additional deployment and operational work | Not proposed for V1 | No evidence of that scaling need |
| BigQuery analysis plus a transactional application store | Fits shared calculations and atomic ledger changes | Two storage responsibilities | Selected | BRD data constraint and cash consistency |
| Next.js/TypeScript frontend with explicit client components | Matches stakeholder preference and supports interactive workspaces | Browser-only chart lifecycle requires deliberate integration | Framework and static rendering confirmed | Stakeholder frontend selection and cost direction |
| Firestore application state and compact serving copies | No database VM or continuously provisioned SQL instance; supports transactions | Explicit document modeling and application-enforced invariants; usage and storage charges remain | Confirmed through option 2 selection | BRD-A-03, BRD-A-04 |
| Option 1: compact current-state portfolio document with separate histories | Few reads and simple initial layout | Shared document contention and bounded embedded-position size | Not selected | Stakeholder chose option 2 |
| Option 2: structured transactional records and resource-oriented REST | Clear entity ownership, atomic updates, reconciliation, and paginated histories | More document operations and explicit invariants | Confirmed by stakeholder | BRD-A-04 |
| Option 3: event-sourced simulation with derived state | Replay and detailed reconstruction | Additional event/version/projection complexity; reset must purge prior simulation events | Not selected for V1 | Stakeholder chose option 2 |
| Cloud SQL or a self-managed PostgreSQL VM | Relational constraints and SQL tooling | Conflicts with the requested hosting model | Rejected by stakeholder | BRD-A-03 |
| Batch-first BigQuery SQL with bounded Python exceptions | Reuses analytical data location and avoids repeated interactive computation | SQL may be awkward or less economical for some exact algorithms; benchmark required | Direction confirmed; per-calculation placement to validate | NFR-05, BRD-A-03 |
| Static Next.js export on Firebase Hosting | Removes request-time frontend compute | No request-time SSR or Server Actions; authenticated data loads through API | Static frontend confirmed; Firebase Hosting is the deployment baseline | BRD-A-03 |
| Suspend application at EUR 5/month | Attempts a fixed spending cutoff | User clarified the amount is indicative, not a hard ceiling | Not selected | Stakeholder budget clarification |
| Lightweight Charts for Swing and Recharts for research/performance | Each chart library serves a distinct visualization need | Two chart integrations and a shared theme mapping to maintain | Confirmed | Candlestick analysis plus score/P&L visualization |
| Recharts with shadcn chart components, without Tremor | Uses the selected design system's chart utilities | Custom research layouts still require application code | Confirmed | Avoid duplicate component layers |
| TanStack Table v8 with version-matched examples | Honors the selected table API | Current shadcn v9 examples need adaptation | Confirmed | Stakeholder version selection |
| Resizable desktop panes and stacked/tabbed mobile views | Fits both dense desktop analysis and small screens | Requires responsive layout and chart-resize verification | Confirmed | Usability across screen sizes |

## 11. Assumptions

**Decision update, approved 2026-09-20:** Reuse `brvm_companies` as the starting catalog; verify issuer identity and market sector against official BRVM evidence and use issuer reports for financial calculation classification. Keep market sector distinct from calculation category. Record source, verification date and manual corrections; unknown classification blocks only dependent calculations. No new administration UI. Actual existing-table provenance remains delivery verification, not a reason to invent source evidence.

**Accessibility approved:** Target WCAG 2.2 Level AA across the V1 application, including authentication and complete paper-trading workflows. Verify with automated checks and manual keyboard/screen-reader testing. Do not convey advisory actions by color alone; supply accessible tabular chart equivalents and keyboard-operable tables, drawers and resizable panels. This is a target, not a conformance claim.

**Financial-report processing correction, confirmed 2026-09-20:** Reuse the existing `archive/legacy-ingestion/scripts/scrape_financials.py` and `scrape_financials_init.py` pipeline, including its existing downstream `insert_financials.py` path. PDF processing is an existing capability, not a new extraction implementation. No additional PDFs, standalone extraction benchmark or EUR 1/month allowance are required for architecture review. Verify execution-path integration, extracted-field contracts and actual operating costs during delivery. This correction supersedes the Extraction Cost Benchmark (companion baseline document) proposal and does not authorize provider calls or production runs. Company-reference and accessibility decisions above remain approved.

| ID | Provisional assumption | Validation owner |
|----|------------------------|------------------|
| ARCH-ASM-01 | Existing Google Cloud infrastructure remains the deployment starting point | Stakeholder |
| ARCH-ASM-03 | Python is suitable for shared analysis and application backend logic | Delivery team / stakeholder |
| ARCH-ASM-04 | The selected structured Firestore model meets the pilot's cost and latency targets; validate with measured document operations and transaction contention | Delivery team |
| ARCH-ASM-07 | Available source evidence can support useful pilot coverage. Verify session attribution, calendar history, zero-volume meaning, issuer/category provenance, share basis, fiscal scope and obtainable Growth inputs through MAP-01 through MAP-10. Until verified, withhold only dependent calculations/orders; do not infer missing years, zero activity or dividend completeness. Product-owner coverage acceptance is required before release. | Ingestion implementer and financial-domain reviewer; product owner accepts coverage |
| ARCH-ASM-08 | The approved private advisory-only design is the implementation baseline, not legal clearance. Determine applicable privacy, investment-advice, disclaimer and retention obligations before release; escalate any required architecture change before rollout. No jurisdiction-specific compliance is assumed. | Product owner with legal/security reviewer |
| ARCH-ASM-09 | Existing development resources can be preserved while adding V1 with isolated configuration, state and identities. Recheck ownership, backend serials, resource collisions, service locations and identity trust before planning/provisioning. Stop deployment if preservation or isolation cannot be demonstrated; no production writes, data cloning or secret copying. | Infrastructure implementer and technical operator |
| ARCH-ASM-10 | Functional acceptance and NFR-07 through NFR-10 are the delivery baseline; no numerical adoption, return, accuracy or delivery-date commitment is assumed. Product owner may set business success measures separately without weakening approved financial rules. | Product owner |
| ARCH-ASM-11 | One technical operator can own calendar exceptions, ingestion failures, backup monitoring and recovery under the best-effort support model. Name that person and support contact before launch, and pass the backup/restore and cost checks before claiming operational readiness. | Product owner appoints; technical operator validates |
| ARCH-ASM-12 | Adopted scoring parameters remain provisional evaluation settings. Implement deterministic fixtures and historical effectiveness evaluation separately; review results before actionable pilot publication. Failure requires explicit product-owner scope/rule review, never silent calibration or a claim of proven returns. | Financial-domain reviewer and product owner |

ARCH-ASM-02 is resolved: the stakeholder confirmed `archive/legacy-ingestion/scripts/` as the ingestion source. ARCH-ASM-05 is resolved: the stakeholder approved the pilot capacity, latency and operating baseline on 2026-09-20; measured verification remains required. ARCH-ASM-06 is resolved: the stakeholder confirmed full rejection of an unaffordable order without a partial fill. Remaining IDs are retained for continuity.

No unresolved architecture choice blocks task decomposition. The nine active assumptions above identify unverified facts, owners and conservative delivery treatment; resolved IDs are excluded from the handoff count. BRD OQ-01 maps to ARCH-ASM-10, OQ-02 to ARCH-ASM-07/12, OQ-03 to ARCH-ASM-07 and the approved integration baseline, OQ-05 to ARCH-ASM-08, and OQ-06 to ARCH-ASM-11. OQ-04 is resolved by the approved identity contract. Formal legal, source-coverage and launch sign-offs are not implied by architecture approval. Implementation evidence remains outstanding and is sequenced in section 13.

## 12. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Scrape date treated as session date | Incorrect recommendations or paper fills | Observed in the confirmed source code | Separate collection and session dates; use source evidence |
| Repeated file load produces duplicate history | Changes indicators and execution inputs | Load/archive sequence has a retry window in inspected helper | Stable run identity, staging and deduplicated publication |
| Inferred dividend fiscal year or incomplete company metadata | Incorrect annual aggregation or incomplete Long-Term context | Observed in production code / reference coverage | Preserve source evidence and explicitly complete the company adapter |
| Financial initialization and rating/dividend loader contracts do not match their callers/producers | Pipeline failure despite existing scripts | Observed in production code | Contract tests and aligned source-specific interfaces before deployment |
| Model re-extraction changes values or repeats chargeable calls | Historical results drift or costs increase | Possible with current extraction path | Persist extraction artifacts and bound retries and batch calls |
| Orders compete for the same cash or shares | Negative balances or overselling | Possible without transactional reservations | Atomic reservations and execution revalidation |
| Reset races with an execution job | Cleared positions reappear | Possible without generation checks | Transactional reset and generation fencing |
| Persistent storage, scans, extraction, or retries dominate a mostly idle pilot | Cost exceeds the indicative target | Unmeasured | Eliminate always-on application compute; benchmark batches and bound retries, scans, and retention |
| SQL/Python calculation placement changes indicator semantics | Inconsistent recommendations | Possible without common fixtures | Version definitions and test identical warm-up, missing-data, rounding, and correction behavior |
| Firestore publication or reset spans more data than one transaction | Partial visible state or stale writes | Possible without explicit publication/generation boundaries | Atomic active pointers and generation checks, immutable serving batches, and retryable cleanup |
| Required source coverage, legal review or recovery evidence remains incomplete | Unsafe or unusable pilot launch | Unverified | Explicit source, compliance and recovery release gates; unavailable outputs and blocked access where evidence is insufficient |

## 13. Notes for the Orchestrator

**Approved Growth coverage policy (2026-09-20):** Implement source verification and acquisition of obtainable inputs across sectors, including banks and insurers. Complete required inputs/history are necessary for full Growth scores; retain supported partial metrics for all other catalog companies without comparing partial totals with complete scores. Before launch, provide company/sector coverage and blocking-input evidence to the product owner for review of Long-Term usefulness. Insufficient coverage requires an explicit scope discussion, not silent score changes or removal of the Long-Term workflow. No numerical minimum has been agreed; this approval is not evidence of adequate production coverage.

**Ready for orchestration, not deployment.** The user approved the architecture and the finalization step. Infrastructure preservation is backlog work, not a prerequisite to creating the backlog. No Terraform edit, plan, apply, state operation, API enablement, paid extraction, data seed or schedule activation is authorized by this document.


Use the following as work packages, not atomic tickets. Split each into single-responsibility testable tasks (especially L packages), with architecture/requirement links, interfaces, acceptance tests, hard dependencies and overlapping-file exclusions. The earlier document-finalization step did not authorize dispatch. The stakeholder has now separately authorized sanitized baseline and backlog publication; agents remain unassigned. The orchestrator must read the full normative package and verify the target repository before publishing its tracking epic and tickets.

| ID | Work package | Hard prerequisites | Complexity / acceptance |
|----|--------------|--------------------|-------------------------|
| ORCH-01 | Generate typed API/data schemas, shared fixtures and CI contract gates | Approved API/data and financial contracts | M; exact-money, bounds, deferred scores, generation/recovery and error fixtures; generated TypeScript client |
| ORCH-02 | Preserve development Terraform ownership and explicit backend/project targeting | Recheck filtered ownership and current live metadata under infrastructure change set 0 | M; preserve verified existing ownership, schedules and access; no unapproved key rotation |
| ORCH-03 | Prepare and review development-only preservation plan | ORCH-02 | M; full plan has no unapproved destruction/replacement/IAM removal or production target; protect sensitive plan/state artifacts; no apply |
| ORCH-04 | Verify source semantics and implement MAP-01 through MAP-10 where in scope | Approved mapping and financial contract; ORCH-01 for shared typed outputs | L; fixture-backed semantics, explicit unavailable paths, provenance and company/sector coverage; no missing-year fabrication or five-year dividend acquisition |
| ORCH-05 | Adapt ingestion packaging, per-function settings and explicit workflows | ORCH-02/03 for infrastructure changes; ORCH-04 source-specific contracts | L; reuse financial PDF code; retry-safe snapshots/loads, isolated development endpoints, preserved existing resource addresses and new schedules paused |
| ORCH-06 | Add lowercase source-table and V1 platform configuration | ORCH-02/03 and verified relevant schemas/locations | L; preserve existing tables and application data, least-privilege new identities, static hosting/auth, scale-to-zero API/jobs, store/recovery register; reviewed plan and explicit approval before provisioning |
| ORCH-07 | Implement versioned Swing and Growth/dividend-research analysis and publication | ORCH-01; ORCH-04 for real inputs | L; independent domain modules, common numerical fixtures, atomic serving publication, no Dividend/Balanced scores or per-user history recomputation |
| ORCH-08 | Build static workspace shell and chart/table primitives | Approved frontend stack; ORCH-01 for typed API integration | M; fixture-driven work can start independently of cloud preparation; responsive and accessible complete flows |
| ORCH-09 | Implement authenticated backend, admission and transactional store | ORCH-01 | L; verified-email/current-allowlist enforcement, isolation, bounded reads and versioned transactions; local tests precede cloud integration |
| ORCH-10 | Implement calendar/execution publication and paper lifecycle including recovery | ORCH-01/09; source contracts from ORCH-04; analysis references from ORCH-07 for integration | L; manual orders, fees, deterministic fills/expiry, personalized advice, reset and recovery failure/race tests from integration matrix |
| ORCH-11 | Integrate Swing, Long-Term and paper workspaces | ORCH-07/08/09/10 contracts and delivered interfaces | L; equal first-class workflows, correct unavailable/freshness states, no optimistic fills, keyboard/screen-reader verification |
| ORCH-12 | Restore development delivery automation | ORCH-02/03/06; verified deployment identity trust | M; V1-to-development guard, isolated backend/credentials, immutable artifacts, reviewed plans, no automatic PR apply |
| ORCH-13 | Validate pilot and obtain release/activation approval | All required integrated packages | L; calculation and effectiveness reviews, NFR tests, isolation checks, restore drill, coverage/cost acceptance, legal review and named operator; separate approval for deployment, seeding and schedules |

ORCH IDs identify packages, not GitHub issues. Final ticket dependencies must be more granular: a shared schema/fixture interface must be delivered before its consumers; consumers may use fixtures without waiting for live data or cloud provisioning. Swing and Long-Term domain work may run in parallel after common contracts land. Infrastructure preservation does not block local UI/domain implementation. Serialize tasks touching `terraform/`, the same workflow files, shared schemas, or the same state/backend; reserve file ownership before dispatch. Do not schedule conflicting edits in parallel merely because their packages differ.

**Deployment gate:** Keep environment configuration, identities and state isolated. Verify current ownership using restricted operator evidence; preserve existing development resources. No production writes, state/secret/user cloning, unapproved deletion or automatic activation. Concrete plans, applies, data seeding and schedule activation each require separate approval.

**Release gate owners:** Delivery team supplies numerical/contract/concurrency/accessibility/load tests and cost evidence; ingestion implementer and financial reviewer supply source and company/sector coverage plus historical evaluation; technical operator supplies backup/restore and exception runbooks; product owner appoints operator/support and accepts coverage, measured costs, legal/privacy/disclaimer review and pilot launch. These are uncompleted acceptance gates, not new architecture questions. Escalate a failed gate that requires changing scope or contracts; never silently weaken the rules.

## 14. Machine-Readable Handoff

```yaml
status: READY_FOR_ORCHESTRATION
open_questions: 0
assumptions_count: 9
components:
  - name: Ingestion
    kind: reused
  - name: Analytical Data
    kind: reused
  - name: Pipeline Orchestration
    kind: reused
  - name: Analysis Engine
    kind: new
  - name: Investor Application
    kind: new
  - name: Paper Trading
    kind: new
  - name: Application Store
    kind: new
new_components: [Analysis Engine, Investor Application, Paper Trading, Application Store]
reused_components: [Ingestion, Analytical Data, Pipeline Orchestration]
blocking_risks: []
readiness_scope: Task decomposition only; deployment and release gates remain mandatory
implementation_and_release_checks:
  - Generate typed schemas and validate exact-money, boundary, concurrency, correction and recovery contracts
  - Verify historical calendar coverage, source date and volume semantics, issuer/category mapping, share basis and required financial inputs
  - Validate financial calculation fixtures and historical effectiveness; adopted thresholds are evaluation baselines, not proven performance
  - Report company and sector coverage for product-owner acceptance without silently weakening Long-Term scoring
  - Measure workload and whole-stack costs including backup, restore and external extraction
  - Pass restore and cross-store failure drills; verify exclusions, admission, recovery identifier and restored-order rejection before reopening
  - Name technical operator and support contact; obtain product-owner launch approval
  - Preserve development state-owned resources and review isolated development plans before any approved deployment
  - Complete legal/privacy/disclaimer review and confirm applicable retention obligations before release
```
