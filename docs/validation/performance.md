# V1 Performance and Placement Evidence

Wave 14 provides an offline, deterministic benchmark harness at `benchmarks/placement.py`. It compares the same exact decimal calculation in the Python and SQL-reference paths. It does not run paid BigQuery jobs, query production, seed data, or infer cloud cost from a local timer.

The placement decision remains: calculate daily analytical indicators in the batch layer when inputs are ready, serve immutable results through bounded reads, and keep request-time paper mutations transactional and small. A live 25-user/five-concurrent load test and measured cloud cost require separately approved development execution.

## Acceptance Rules

- The two engines must agree within the declared exact-decimal tolerance and agree on action labels.
- p95 read latency and batch duration are recorded only from an approved representative environment; cold start and network time are reported separately.
- A missing live measurement is evidence unavailable, never a reason to claim the target passed.

Run the offline check with:

```text
python3 -m pytest tests/benchmarks/test_placement.py
```
