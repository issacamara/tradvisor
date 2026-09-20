<!-- Public derivative: operational identifiers and private inventory excluded. Normative behavior unchanged. -->

# Tradvisor V1 - Integration Design Review

**Status:** APPROVED - integration design baseline; not implemented
**Version:** 1.0
**Date:** 2026-09-20
**References:** Architecture v1.0 (companion baseline document), API/data contract v0.13 (companion baseline document), Source mapping v0.5 (companion baseline document)

## 1. Review Boundary

This approved design closes three integration-design gaps without changing the seven component boundaries, financial formulas, manual paper trading or low-cost direction. Approved by the stakeholder on 2026-09-20 and incorporated by reference into the architecture and API/data contract. The filename is retained for link stability. No production access, deployment or application changes are authorized by this document.

Approved foundations: next-session execution, one following-session missing-price grace, immutable price availability, rejection on material calendar corrections, no automatic repricing, independent reset/access protection, rejection of restored pending orders, recovery identifiers and explicit reconfirmation. The stakeholder approved the mechanisms below on 2026-09-20; approval is not evidence of implementation or passing tests.

## 2. Session Completion And Deadlines

### Recommended Convention

Use `Africa/Abidjan` for exchange session dates and UTC for persisted instants. Store a versioned calendar entry per date with session status, scheduled officialization time, timing tolerance, source references, verification status and any date-specific exception.

Use `completion_cutoff = verified scheduled officialization + 60 seconds`. For a normal session this is 15:01 UTC; for a source-confirmed noon exceptional closure it is 12:01 UTC. These are conservative application cutoffs, not observed exchange timestamps. The official schedule distinguishes closing fixing from officialization, includes a +/-60-second variation and requires notice-backed exceptional schedules. [BRVM trading hours](https://www.brvm.org/fr/horaires-de-cotation)

- At or after the cutoff, treat a verified scheduled session as completed for recommendation freshness. Do not wait for ingestion to declare the session completed: missing new data must make advice stale rather than extend yesterday's freshness.
- Persist an order's intended session and the following verified session's completion cutoff as its deadline. Eligibility remains inclusive: `validated_available_at <= deadline`.
- This operationalizes the approved official-close deadline using the conservative upper timing bound. The approved convention can add one minute versus the nominal published time.
- Unresolved provisional holidays, missing required dates or known unresolved closure/delay notices block affected new orders. Do not infer completion merely from a scraper timestamp.
- Retain calendar versions. A verified change affecting an accepted order's session or deadline follows the approved rejection rule, not silent rescheduling. Completed trades remain unchanged.
- The operator records source-backed closures/extensions. The application cannot promise detection of an unpublished or unseen notice; monitor source retrieval failures and retain evidence.

### Runtime Consistency

Keep the active calendar version in a small application control document. Acceptance and execution transactions read that version plus the relevant immutable entries. Publishing a correction updates the control document; overlapping transactions must retry and re-evaluate. Reject affected pending orders on the next worker pass, and always repeat the check inside the fill transaction. This closes the interval between calendar publication and background rejection.

## 3. Price Publication And Execution Consistency

### One Execution Authority

Retain canonical analytical history in BigQuery. Introduce compact execution-price records in the existing Application Store, not a new service. Paper workers use these records exclusively; they do not join live BigQuery results during a financial mutation.

Proposed logical records:

| Record | Purpose |
|--------|---------|
| Immutable price revision | Symbol, session, exact raw genuine close, source/hash, revision sequence and server-assigned `validated_available_at` |
| Symbol/session control | Publication version and current revision; all correction/invalidation changes update this record |
| Revision validity event | Append-only invalidation/supersession evidence, linked to the original immutable revision |
| Runtime control | Active recovery identifier and maintenance state |

### Publication Protocol

1. Validate source session, genuine-trade status, exact price and source evidence. Persist the canonical source revision before making it execution-eligible.
2. In one Firestore transaction, create the immutable revision with a server timestamp, assign its sequence and update the symbol/session control. Identical retries locate the same revision and preserve its timestamp. Never use the timestamp of an earlier BigQuery write as platform execution availability.
3. The first successful application-store commit is the execution-availability boundary. Read the resolved server timestamp after commit; a lost response is reconciled by revision ID, not a new timestamp. Data staged only in BigQuery remains ineligible.
4. Publish analysis batches independently through the existing complete-batch pointer. A later analytical publication must not rewrite price availability. Record both source revision and batch references so the two histories remain distinguishable.

Transactions provide atomic updates and may retry on concurrent changes; external writes must stay outside their callback. This design deliberately does not claim a distributed transaction between BigQuery and Firestore. [Firestore transactions](https://firebase.google.com/docs/firestore/manage-data/transactions)

### Fill Protocol

The worker identifies a candidate revision from a bounded, paginated revision history, then transactionally reads the symbol/session control, candidate evidence/validity, active calendar, runtime control, order, portfolio and affected position/reservations. Verify the candidate against the observed publication version; if it changed since selection, reselect and retry.

Select the latest revision already available at the decision point whose server timestamp is no later than the deadline and which remains valid. Revision ordering uses the publisher's sequence, not a timestamp tie-break guessed by the worker. A later invalidation disqualifies an earlier invalid price even when the replacement arrived too late. Never fall back to an invalid superseded revision.

The same transaction checks generation, recovery identifier, calendar correction, resources and order state, then writes execution, cash/position changes and reservation release. Correction/invalidation writers must update the control record read by fills, so a concurrent change forces re-evaluation. Never make source calls inside this transaction.

An otherwise eligible fill need not wait until grace ends. Once committed, later corrections create review evidence rather than reprice it. Without an eligible revision, wait only while grace remains, then expire. Preserve deterministic per-portfolio order processing.

## 4. Recovery Register Ordering And Completeness

### Durable Intent Before Irreversible Change

Use the approved private Cloud Storage register. Persist minimal immutable intent records by stable operation ID, plus a generation-preconditioned per-subject head pointing to an ordered decision chain. A subject is a portfolio or admission identity; recovery-wide identifiers use a separate runtime subject. Normal users have no register access.

Each record carries operation ID, subject, predecessor/sequence, operation type, affected generation where applicable, authorizing operator/service identity, timestamp and payload hash. No trades, balances, passwords or tokens. Retries with the same ID must match the payload; a mismatch is an error, not an overwrite.

Create immutable objects with create-only preconditions; advance a head only if its observed object generation still matches. A conflict requires rereading and revalidating the predecessor. Do not apply last-write-wins ordering to access decisions. [Cloud Storage request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions)

**Approved strengthening of the previous sequence (2026-09-20):** write a restrictive intent before the live fence/denial, then confirm the ordered register decision before final database completion. This extra first step protects an interrupted operation that would otherwise exist only in the lost database. It is not a cross-store transaction; this approved sequence supersedes the earlier fence-first description.

| Operation | Ordered behavior |
|-----------|------------------|
| Reset | Validate request; persist reset intent for expected generation; transactionally revalidate and fence that generation; advance the register decision; finalize replacement generation and receipt. Return success only after durable exclusion and final database completion. |
| Access removal | Persist deny intent; immediately deny in live admission; finalize ordered deny decision. No success response before both are confirmed. If live denial fails, surface failure and keep the intent restrictive for recovery. |
| Re-admission | Resolve prior pending operations; authorize a decision explicitly referencing the current deny head; persist/advance that decision before enabling live admission. A stale predecessor must not enable access. |
| Recovery | Stop admission/mutations/workers; persist a new recovery operation and identifier; install it in the isolated restored database; reconcile; reopen only after checks succeed. |

Concurrent reset attempts revalidate the generation/version under the existing transaction fence. An intent that cannot be completed is not silently deleted: reconcile it with evidence. A restrictive unresolved intent blocks the affected subject during recovery, even if it never became the head. An incomplete grant never overrides a deny. This favors temporary unavailability over restoring removed access or cleared history.

Do not claim an access removal took effect until live denial is confirmed. A failed administrative removal must be conspicuous and retried under the same operation ID. Grants/removals for one identity are serialized through the subject's head; ordinary admission checks continue to use current backend-controlled live state on every protected request.

### Recovery Scan And Failure Scope

With writers stopped, inventory all intent objects and heads, traverse referenced chains and reconcile unlinked intents. Cloud Storage documents strong object-read and listing consistency; this supports the scan, but is not proof against administrator deletion or missing application writes. [Cloud Storage consistency](https://docs.cloud.google.com/storage/docs/consistency)

- Missing referenced records, hash mismatches, unresolved forks or restrictive orphan intents block their affected subjects.
- Failed/incomplete listing, unknown inventory scope or unavailable runtime recovery head blocks reopening globally. Do not interpret an unreadable register as an empty register.
- Routine writers cannot delete register history. Separate privileged cleanup verifies that no retained backup, restored database or other recoverable copy can resurrect excluded state. Inability to prove that means retaining the minimal exclusion.
- A newer authorized grant supersedes a deny only through a complete, validated chain. Database timestamps or an old allowlist are not ordering evidence.
- Stop and revoke access to the old database before reopening the new one; a recovery identifier in the new database alone cannot stop a worker still attached to the old database. Restart all API/worker instances against the restored target and test routing/IAM isolation.
- Apply exclusions and admission decisions, reconcile surviving ledger state, reject restored pending orders, release surviving reservations once, and validate the new recovery identifier. Inconsistent accounts remain blocked. Report actual backup time and potential loss.

Register protection requires restricted operator permissions and audited cleanup. This design does not promise survival of deliberate privileged destruction of both register and recovery evidence; inability to establish protection prevents reopening.

## 5. Verification And Ownership

| Check | Expected result |
|-------|-----------------|
| Session boundary at cutoff +/-1 microsecond | Freshness and deadline comparison follow one documented inclusive boundary |
| Provisional holiday or delayed-session notice | Affected commands block until verified; correction never silently moves accepted orders |
| Lost price-publication response and identical retry | One immutable revision and original availability timestamp |
| Publication/invalidation racing a fill | Transaction observes a consistent version or retries; no known-invalid fill |
| Timely revision and late worker; late replacement | Timely valid evidence can execute; late replacement cannot inherit eligibility |
| Crash at every reset/access protocol boundary | No false success; restrictive incomplete operations remain recoverably blocked |
| Concurrent removal/re-admission | Stale grant cannot supersede a newer deny |
| Partial register scan or missing chain link | Global or affected-subject closure according to scope above |
| Restore with old requests and active old worker | Old identifier rejected; old database isolated; pending orders rejected once |
| Register cleanup with a surviving restored copy | Exclusion retained regardless of ordinary backup expiry |

Delivery engineers implement these tests and the protocol. The nominated technical operator validates runbooks and exception handling. The product owner accepts the cutoff convention and conservative failure behavior. These are required checks, not results of tests already run.

## 6. Review Decision And Next Handoff

All three designs were approved together on 2026-09-20. The user-visible trade-offs are the conservative one-minute cutoff, possible temporary blocking after interrupted restrictive operations, and unchanged reconfirmation requirements following recovery/corrections. No new continuously running service is proposed; small transactional records and register operations add usage that must be included in the cost estimate.

These choices are incorporated into architecture v1.0 and API/data contract v0.13; their design blockers are closed. Final architecture readiness follows the package consistency review, not the existence of this document alone. Subsequent stakeholder decisions approve company-reference enrichment direction and WCAG 2.2 AA (architecture section 11). Actual provenance remains verification. Financial-report processing reuses `scrape_financials.py` and `scrape_financials_init.py`, including the existing downstream insertion path. No new extraction implementation, standalone benchmark or allowance decision is an architecture prerequisite; integration, extracted-field contracts and actual costs remain delivery checks. Actual source coverage, tests, measured cost, operator appointment and restore drills remain implementation/release gates rather than evidence supplied by this draft.
