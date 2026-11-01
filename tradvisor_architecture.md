# Tradvisor V1 Architecture

**Status:** Active V1 architecture

The operational V1 boundary is summarized in
[`docs/operations/v1-scope.md`](docs/operations/v1-scope.md). It is a
companion to this architecture, not a separate product specification.
**Engineering amendment:** TF-1, approved 2026-10-12 and incorporated 2026-10-14. R1–R7 define the target design; implementation and compliance verification remain pending.
**Financial-ingestion amendment:** FI-1, approved 2026-11-01 and incorporated
2026-11-01. It replaces the financial Cloud Function chain with one monthly
Cloud Run Job and makes BigQuery the only retained financial-ingestion record.
Its orchestration-ready Gate 2 handoff, contracts, retirement scope, and wave
plan are in [`docs/architecture/financial-ingestion-fi-1.md`](docs/architecture/financial-ingestion-fi-1.md).

## Scope

Tradvisor V1 is a read-only BRVM research application with two equal workflows:

- **Swing:** daily technical entry research for the listed equity universe.
- **Long-Term:** Growth ranking, company evidence, and dividend facts where the source coverage supports them.

The product publishes research, explanations, and evidence. It does not maintain portfolios, accept orders, execute transactions, track cash or positions, or connect to a broker.

## System Design

```mermaid
flowchart LR
  Sources[BRVM and RichBourse sources] --> Ingestion[Ingestion workloads]
  Ingestion --> BQ[BigQuery stocks dataset]
  Ingestion --> Trigger[Completion-driven publication control]
  Trigger --> Analysis[Existing analytical publication job]
  BQ --> Analysis
  Analysis --> Serving[Firestore published batches]
  Serving --> API[Cloud Run FastAPI]
  API --> Web[Firebase Hosting static Next.js app]
  Auth[Firebase Authentication and allowlist] --> API
```

## Approved Direct Scheduler-to-Workflow Amendment

The owner approved direct Cloud Scheduler invocation of Cloud Workflows on
2026-10-20. Each managed Scheduler job creates an execution of its named
ingestion workflow through the Workflows Executions API using the existing
least-privilege service identity. Scheduler acceptance confirms that an
execution was created; Workflow execution state remains the authoritative
completion and failure signal.

This is the target architecture amendment, not a claim about the currently
deployed state. The deployed state remains unchanged until the reviewed
implementation, CI, Terraform plan, development proof, and separate
operational approvals are complete.

```mermaid
flowchart LR
  Scheduler[Cloud Scheduler] -->|OAuth: executions.create| Workflow[Cloud Workflow]
  Workflow --> Functions[Ordered ingestion Cloud Functions]
  Functions --> GCS[GCS evidence and archives]
  Functions --> BQ[BigQuery stocks dataset]
```

Cloud Tasks queues and the internal Cloud Run workflow-dispatcher are not part
of the target scheduled-ingestion path. Their retirement is an implementation
task, subject to dependency verification and the normal reviewed Terraform
delivery process. Existing ingestion workflow definitions, schedules, GCS and
BigQuery contracts, and completion-driven publication control remain unchanged.

FI-1 is the financials-specific exception to this shared path. Its monthly
Scheduler job invokes the financial-ingestion Cloud Run Job directly; it does
not create a financials Workflow execution or invoke the retired
`scrape_financials`, `scrape_financials_init`, or `insert_financials` Cloud
Functions. Other ingestion sources retain the Scheduler-to-Workflow design.

Operational monitoring must distinguish a Scheduler delivery failure from a
Workflow execution failure. Before retiring queue-based serialization, the
implementation must verify that each workflow's maximum execution duration is
within its next scheduled interval and that existing ingestion idempotency
handles any permitted retry or overlap.

The static Next.js application uses authenticated client requests to the Cloud Run API. The API verifies Firebase identity, verified email, and the current allowlist before returning published analytical data. The browser never accesses BigQuery or writes Firestore directly.

## Data Flow

### Cloud-only ingestion amendment

The approved [v1.1 cloud-only ingestion amendment](https://github.com/issacamara/tradvisor/issues/1#issuecomment-6110931290) supersedes future V1 requirements for a separate share-price revision store and point-in-time share-correction replay. Completed #14 and #42 remain historical delivery records; this amendment does not delete or reclassify their delivered work.

1. Existing non-financial ingestion functions retain incoming files and raw source evidence in GCS, then load company, share, dividend, and rating data into the configured environment's Terraform-managed `stocks` dataset. FI-1 instead downloads each selected financial PDF into job memory, discards the PDF and provider responses after validation, and retains only the resulting row in `stocks.financials`. Canonical `shares` observations are keyed by symbol and date; corrections may update that row while retaining the history needed for charts and indicator warm-up. V1 does not persist a separate share-price revision store or provide point-in-time replay of share corrections.
2. A successful import emits a sanitized completion outcome only after its managed BigQuery write has finished. The reused ingestion workflow/control plane coalesces eligible outcomes and then starts the existing analytical Cloud Run Job. It is completion-driven, not a second fixed-time analytical schedule.
3. `shares` is the daily publication dependency and starts a refresh after a successful daily import. `financials` starts a refresh after a successful import because it changes Long-Term inputs. `ratings` is retained as an ingestion dataset but neither gates nor starts publication in V1 because the current analytical reader does not consume it. Adding ratings later requires an approved analytical-contract amendment.
4. The control plane serializes publication requests and uses a bounded, release-configured debounce window. Multiple eligible completions in that window produce at most one job execution. Before starting a run, it compares the source-input identity with the active publication; an unchanged input set is recorded as a no-op rather than producing a duplicate publication.
5. The existing analytical job reads only the necessary partitioned BigQuery history, calculates indicators and Long-Term inputs, and writes an immutable publication batch.
6. The job validates the candidate batch and atomically updates `publication_state/current` only after all required serving documents are present.
7. Firestore serves compact, read-optimized publication documents. BigQuery remains the analytical source of truth and is never queried by an interactive request.
8. The API reads the active publication, returns typed availability states for missing or warming inputs, and exposes chart observations for the selected symbol.

## Components

| Component | Responsibility |
|---|---|
| Ingestion | Reuse the BRVM/RichBourse adapters and managed BigQuery writer patterns. Non-financial sources retain incoming/raw evidence in GCS. Financials use the FI-1 monthly Cloud Run Job and retain only validated rows in BigQuery. |
| Publication control | Extend the existing ingestion Workflow/dispatcher and serialized task-control pattern to accept successful input-completion outcomes, coalesce them, reject duplicate source snapshots, and invoke the existing analytical job. It does not calculate analytics or serve user requests. |
| BigQuery | Store canonical source tables, including dated `shares` rows keyed by symbol/date, and partitioned analytical inputs. |
| Analysis job | The single existing Cloud Run Job calculates EMA20/EMA50, RSI14, ATR14, traded-value liquidity, Swing entry state/strength, and Long-Term Growth research after an eligible input completion. |
| Firestore | Store immutable analytical batches and one active-publication pointer only. |
| Cloud Run API | Authenticate requests and expose read-only analytical resources. |
| Firebase Hosting | Deliver the static frontend. |
| Firebase Authentication | Authenticate users; the API additionally enforces verified-email and allowlist admission. |

## Analytical Rules

Swing uses EMA 20/50, Wilder RSI 14, and Wilder ATR 14. A Buy requires an unrounded strength of at least 70. Liquidity, current-trade, and structural guards are published as explanatory evidence and do not veto a qualifying score. A result that cannot be established is explicitly `insufficient_data`; it is never inferred as Buy or Sell.

Long-Term V1 publishes Growth scores when required financial inputs are available. Dividend payments and conditional historical yield remain research facts; Dividend and Balanced composite scores are deferred. Every result identifies its batch, effective date, rule version, calculation status, and evidence references.

## Firestore Serving Model

| Document path | Responsibility |
|---|---|
| `analysis_batches/{batch_id}` | Batch manifest, source snapshot, rule version, session date, and publication timestamp. |
| `analysis_batches/{batch_id}/swing/{symbol}` | Swing entry state, strength, eligibility guards, and indicator evidence. |
| `analysis_batches/{batch_id}/long_term/{symbol}` | Growth score, advisory state, factor contributions, and evidence. |
| `analysis_batches/{batch_id}/charts/{symbol}` | Bounded dated close-price observations used by the frontend chart. |
| `publication_state/current` | Active complete batch identifier and publication metadata. |
| Publication-control state | Sanitized source-input identity, coalescing/request state, and last outcome needed to serialize a retry-safe dispatch. It contains no user data or source payloads. |

These documents are rebuildable analytical serving copies. No user financial state is stored in Firestore.

## API Contract

The read-only API surface is:

| Endpoint | Purpose |
|---|---|
| `GET /v1/me` | Current admitted identity. |
| `GET /v1/swing/recommendations` | Published Swing screening results. |
| `GET /v1/long-term/rankings` | Published Long-Term Growth research. |
| `GET /v1/stocks/{symbol}` | Company and published analytical detail. |
| `GET /v1/stocks/{symbol}/chart` | Bounded close-price observations for a selected stock. |

Responses use the standard `data` and `meta` envelope and include explicit unavailable states. There are no mutation endpoints in V1.

## Deployment and Cost Controls

- Firebase Hosting serves the static frontend.
- Cloud Run API uses zero minimum instances and request-based billing.
- Heavy calculations run once per daily batch, preferably in BigQuery, not on interactive API requests.
- The existing analytical Cloud Run Job remains the only recurring analytical compute. FI-1 adds one monthly ingestion job; it does not calculate or publish recommendations. Import-completion events may request the analytical job, but coalescing and input-snapshot deduplication ensure that one ready input set produces at most one analytical execution.
- BigQuery source and analytical tables use partitioning and only select the necessary symbols, dates, and columns.
- Terraform declares development resources in `dev-tradvisor`; production remains isolated and read-only unless separately approved.
- Deploy through the repository GitHub Actions workflow after a committed, pushed change and passing CI.

## Security and Operations

- Firebase Authentication handles password, verification, and reset flows.
- The API fails closed if identity or allowlist admission cannot be verified.
- The frontend has no service-account credentials and no direct Firestore write capability.
- Published batches are immutable. A failed daily run leaves the most recent complete batch active and visible with its original date.
- A successful daily shares import must have an active publication based on that input within the existing 15-minute publication target; source-to-publication lag is monitored. A failed or stale publication is surfaced as stale/unavailable, never hidden by an interactive BigQuery fallback.
- The completion trigger identity may invoke only the existing analytical job. It has no Firestore read/write privilege beyond the minimal publication-control state and no authority to change schedules, analytical rules, source tables, or user-serving data.
- Logs contain operational metadata only and never carry user secrets or credentials.

### OA-1 OpenRouter financials credential amendment

The approved financials credential amendment keeps the real OpenRouter
credential payload out of Terraform, GitHub, source, tests, logs, and artifacts. Terraform manages
environment-local Secret Manager metadata and a resource-level accessor grant
for the dedicated financials identity. Under FI-1, only the financial-ingestion
Cloud Run Job receives `OPENROUTER_API_KEY` through secret environment
configuration; the retired financial Cloud Functions no longer receive it.
An authorized operator provisions and enables a secret version
before requesting reviewed function wiring; development and production use
separate project-local secrets and payloads. This records the target contract,
not a claim that payload provisioning or cloud deployment has occurred.

## Approved Financial-Ingestion Job Amendment

The owner approved FI-1 on 2026-11-01 to simplify the monthly collection of the
latest five available annual financial statements per RichBourse-listed
company. This section supersedes the financials-specific Cloud Function,
Workflow, GCS archive, extraction-artifact and initialization paths. It does
not change financial formulas, Long-Term availability rules, source-table
ownership, or completion-driven analytical publication.

### FI-1 requirements and decisions

| Req ID | Requirement | Architecture decision |
|---|---|---|
| FI-01 | Collect the latest five available annual financial years for each company exposed by the RichBourse company selector. | One monthly Cloud Run Job fetches the selector once, requests the symbol-filtered page for each listed company with bounded concurrency, rejects quarterly and half-year activity reports, and retains the newest five annual fiscal years actually available. |
| FI-02 | Avoid repeated extraction of already stored statements. | The job reads existing `(symbol, fiscal_year, document_link)` state from `stocks.financials` once, skips unchanged rows, and reprocesses an existing year only when RichBourse exposes a different document link. |
| FI-03 | Extract `fiscal_year`, `revenue`, `net_income`, `total_debt`, `cash_and_cash_equivalents`, and `total_equity` as numbers or null. | The job requires the exact JSON shape, checks finite numeric/null values and verifies the fiscal year against source metadata before writing. Missing values remain null; they are never synthesized as zero. |
| FI-04 | Use an ordered OpenRouter fallback chain. | Runtime configuration defines `gemma-4-31b-it` as the primary business-selected model, then `nvidia/nemotron-3.5-lightning:free`, then `openai/gpt-4o-mini`. The next model is called only after provider failure, invalid JSON/schema, fiscal-year conflict, or a result with no usable financial value. The deployable OpenRouter identifier for the primary alias must be verified before release. |
| FI-05 | Retain no PDF archive or extraction evidence. | PDFs, extracted text and provider responses exist only in job memory and are discarded after validation. `stocks.financials` is the sole retained ingestion record. Logs contain bounded operational metadata only. |
| FI-06 | Run once per month with minimal platform machinery. | Cloud Scheduler invokes one private Cloud Run Job directly. No financials Workflow, Cloud Function chain, Pub/Sub topic, Cloud Tasks queue, or GCS bucket is required. |
| FI-07 | Preserve Terraform ownership and safe publication. | Terraform declares the job, schedule, IAM, secret binding and BigQuery tables. The job uses the managed staging/MERGE writer and emits successful financial-import completion only after the BigQuery write commits. |

```mermaid
flowchart LR
  Scheduler[Monthly Cloud Scheduler] -->|OAuth run permission| Job[Financial ingestion Cloud Run Job]
  Job -->|company pages and transient PDFs| RichBourse[RichBourse]
  Job -->|ordered extraction requests| OpenRouter[OpenRouter]
  Job -->|staged validated merge| Financials[BigQuery stocks.financials]
  Job -->|sanitized completion| Publication[Publication control]
```

The job is stateless and performs one bounded batch. It reads the configured
BigQuery state once, keeps PDFs and provider responses only in memory, and
writes validated rows through the existing Terraform-managed staging/MERGE
pattern. A report that fails all three models remains absent or unchanged and
is retried on the next run. Successfully committed rows are not repeated.

The primary model identifier, request limits, concurrency and retry allowance
are runtime configuration because OpenRouter availability and quotas are
external. The implementation must verify the exact primary Gemma identifier
before deployment. A free secondary model is opportunistic: unavailability or
rate limiting falls through to the paid tertiary model within the configured
attempt budget. Monitoring must report candidate, skipped, inserted, updated,
failed and per-model-attempt counts without recording document text or model
responses.

The provisional operating target is one active execution at a time, at most
four concurrent RichBourse requests, no more than one attempt per configured
model for one report, and completion within 60 minutes for the current
48-company selector. The implementation must measure this in development and
adjust the concurrency or timeout through reviewed runtime configuration rather
than adding another service. One BigQuery state query and one staged MERGE per
successful run are the database-efficiency targets.

Choosing BigQuery-only retention accepts that an extraction cannot be replayed
or audited from retained source material and that an in-place replacement at
the same RichBourse URL is not detectable. A changed document URL is treated
as a replacement and may update the current `(symbol, fiscal_year)` row. The
existing historical financial revision assets, if present, are left untouched;
their removal or migration requires a separate data-retention decision.

FI-1 is a target architecture amendment, not evidence of deployment. Delivery
requires an isolated wave, focused parser/model-fallback/writer tests,
current-head CI and review, a trusted post-merge image built from the
`development` commit, development deployment by immutable digest, and
development verification. Production promotion must use the same digest and a
human-approved gate. Terraform plan/apply, paid provider calls, paid BigQuery
queries, schedule activation and production operations remain separately
approved actions.

## Approved Publication-Orchestration Amendment

The owner approved completion-driven publication on 2026-10-18 to prevent the
published Firestore batch from lagging successful source imports. This
amendment extends existing ingestion orchestration and the existing analytical
Cloud Run Job. FI-1 subsequently introduces one monthly financial-ingestion
batch job but no second analytical job, request-time BigQuery fallback, new
analytical input, or new user-facing workflow.

This section describes target architecture and does not assert that it is
deployed. Deployment, schedule activation, development proof, and operational
changes remain separately approved delivery steps.

| Decision | Target architecture |
|---|---|
| Trigger | Successful completion of an eligible managed import is the publication trigger; a fixed-time analytical schedule is not the normal path. |
| Dependencies | Shares are required for daily Swing/chart freshness. Financials trigger a Long-Term correction publication when they change. Ratings are not currently a publication dependency. |
| Coalescing | A serialized control-plane extension applies a bounded configurable debounce and source-snapshot deduplication before invoking the job. |
| Failure and retry | Import failure produces no publication request. Job failure preserves the active complete batch, uses the job's finite retry policy, and leaves a bounded sanitized outcome for alerting and recovery. |
| Freshness | Monitor eligible source completion to active-publication lag against the existing 15-minute ready-input target. The UI must distinguish a chart-specific unavailable state from publication-wide unavailability. |
| Recovery | A manual job execution is recovery-only and requires separate owner approval; it does not replace the automated completion trigger. |

Implementation must use Terraform-managed control-plane resources and least-
privilege service identities. Schedule activation, Terraform apply, batch
execution, and any paid query remain separately approved operational actions.

## Retired V1 Surface

The former simulated-trading workflow, its API routes, frontend page, backend modules, Firestore documents, tests, and backlog artefacts are removed from V1. Future product work would require a new approved architecture and contract rather than reusing retired data or code.

## Approved Twelve-Factor Engineering Amendment

The owner approved R1–R7 on 2026-10-12, including complete DuckDB removal. The normative engineering detail, architecture impacts, requirement traceability, acceptance criteria, risks and sequencing are in [Gate 2 engineering amendment TF-1](docs/architecture/twelve-factor-amendment.md). It extends existing components without adding platform services or changing financial rules, API scope or V1 workflows.

| Decision | Approved target architecture |
|---|---|
| R1 — Dependencies | Lock complete Python dependency resolutions for backend and ingestion, retain npm locks, explicitly declare imported dependencies, and pin build/deployment tools and container digests. |
| R2 — Configuration | Share validated configuration contracts across API, jobs, ingestion and administration; require explicit environment and backing-service targets; provide secret-free `.env.example` documentation. Keep versioned financial rules distinct from deployment settings. |
| R3 — Backing services | Serve every interactive analytical read, including charts, only from the published Firestore batch; use typed unavailable states instead of BigQuery fallbacks. Terraform owns and protects all application/batch tables, including staging; retain retry identifiers and serialized writers without runtime table creation/replacement. |
| R4 — Build, release, run | Separate artifact build, release preparation and execution. Promote the verified backend image digest, bind artifacts/configuration/rules to a release manifest, and apply the exact approved saved Terraform plan. Build environment-specific static frontend artifacts from the same approved source and locks. |
| R5 — Processes | Remove DuckDB completely: dependencies, imports, local database configuration, persistence paths and DuckDB-specific tests. Use GCS/BigQuery/Firestore for durable state and disposable scratch only; credential-free tests use fixtures/test doubles. No replacement share-revision store or local-revision migration. |
| R6 — Logs | Extend `OperationalEvent` with consistent JSON stdout formatting across entry points, bounded sanitized attributes and safe failure handling; exclude raw provider payloads, credentials and user identifiers. Platform-managed retention remains 30 days. |
| R7 — Admin processes | Wrap existing admission, recovery and maintenance modules with thin commands using the approved backend image/configuration, explicit targets, operation-specific permissions, stable retry identifiers and conspicuous failures. Schema changes remain Terraform-owned. |

These are approved design requirements, not claims that the codebase is now compliant. Implementation must preserve existing resources and non-financial source evidence; FI-1 intentionally retains no financial PDF or extraction evidence. Delivery must pass focused checks and current-head review/CI and obtain separate authorization for cloud plans/applies, migrations, paid queries, seeding, schedule activation or production changes.

Only the engineering amendment is synchronized with `planning/public/architecture.md`. The pre-existing Swing guard/eligibility wording difference is preserved and requires separate owner reconciliation before any financial-rule change; TF-1 does not choose between those formulations.
