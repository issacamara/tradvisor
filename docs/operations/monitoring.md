# V1 Monitoring Contract

The application emits bounded operational events for ingestion, publication, API and worker outcomes. Events contain workflow names, result classes, durations, bounded counts and sanitized error codes only. Credentials, tokens, user identifiers, email addresses, request bodies and provider response payloads are excluded.

## Signals

| Signal | Stale/failed condition | Operator action |
| --- | --- | --- |
| Source ingestion | A scheduled source job fails or does not produce an expected sanitized outcome | Inspect the job error code and source freshness; keep the affected workflow unavailable |
| Publication | A daily publication is absent beyond the exchange-session freshness boundary | Check the latest completed batch and dependency outcome; do not substitute stale advice |
| Worker | A worker failure or retry budget exhaustion is recorded | Inspect bounded retry and recovery state; keep pending mutations fenced |
| Backup | Backup age exceeds the configured operational threshold or a health check fails | Use the isolated restore runbook; do not restore into the active target |
| Cost driver | Bounded query, extraction, retry or transfer counters exceed their declared budget | Pause the relevant development schedule and obtain owner approval before increasing limits |

Application logs are retained for thirty days. Alert evaluation is finite and scheduled; this contract does not keep a service warm, activate schedules, or promise a fixed monthly bill.
