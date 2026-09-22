# Tradvisor

Tradvisor V1 is being refocused around the Business Requirements Document in
`tradvisor_brd.md`.

The repository currently contains the V1 requirements and the legacy
data-ingestion foundation for BRVM market data:

- `archive/legacy-ingestion/scripts/`: previous scrapers and loaders for shares,
  bonds, dividends, indices, and capitalizations. These are preserved as
  reference material while the V1 architecture is redesigned.
- `terraform/`: Google Cloud infrastructure for storage buckets, Cloud
  Functions, Workflows, Scheduler jobs, BigQuery, IAM, and supporting services.
- `tradvisor_brd.md`: V1 business requirements for Swing recommendations,
  Long-Term scoring, and manual paper trading.

The previous Streamlit webapp has been removed so the next architecture pass can
target the V1 BRD cleanly.

## Terraform Preservation

The checked-in Terraform declarations preserve the existing development
resources. They are not permission to discover, import, move, remove, plan,
apply, rotate keys, or activate schedules. The existing paused legacy schedule
must remain paused.

The development backend bucket and prefix are private operator evidence. Keep
them outside the repository and provide them only to an approved operator at
the separately authorized preservation-plan review. Do not place backend values
in `.tf` files, commits, issues, pull requests, logs, or command history.

When that review has been separately authorized, an operator can initialize
Terraform with their private backend values:

```sh
terraform -chdir=terraform init \
  -backend-config="bucket=<terraform-state-bucket>" \
  -backend-config="prefix=tradvisor"
```

Local `*.tfstate` files, backend configuration files, plans, and provider
caches are ignored and must not be committed. Before any future plan, the
operator must revalidate development ownership and state compatibility. The
legacy IAM bindings intentionally ignore membership drift to avoid removing
principals managed elsewhere; any migration to additive IAM-member resources
requires a state-aware, separately approved change.
