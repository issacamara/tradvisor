# V1 Monitoring Contract

The application emits bounded operational events for ingestion, publication, API and worker outcomes. Events contain workflow names, result classes, durations, bounded counts and sanitized error codes only. Credentials, tokens, user identifiers, email addresses, request bodies and provider response payloads are excluded.

## Signals

| Signal | Stale/failed condition | Operator action |
| --- | --- | --- |
| Source ingestion | A scheduled source job fails or does not produce an expected sanitized outcome | Inspect the job error code and source freshness; keep the affected workflow unavailable |
| Publication dispatch | An eligible completion has no bounded coalescing, no-op, invocation, or terminal control event after its debounce window | Inspect only the sanitized control outcome and preserve the last complete batch; do not manually run the job without separate owner approval |
| Publication freshness | A successful daily shares completion, or a financial correction completion, has not reached the active publication within 15 minutes | Check the active batch's sanitized input identity and the control outcome. Surface stale/unavailable state; never substitute interactive BigQuery reads |
| Duplicate control | A duplicate request was not collapsed | Retain the previous complete batch, inspect the bounded duplicate-control event, and escalate before retrying any recovery action |
| Worker | A worker failure or retry budget exhaustion is recorded | Inspect bounded retry and recovery state; keep pending mutations fenced |
| Backup | Backup age exceeds the configured operational threshold or a health check fails | Use the isolated restore runbook; do not restore into the active target |
| Cost driver | Bounded query, extraction, retry or transfer counters exceed their declared budget | Pause the relevant development schedule and obtain owner approval before increasing limits |

Application logs are retained for thirty days. Alert evaluation is finite and scheduled; this contract does not keep a service warm, activate schedules, or promise a fixed monthly bill.
