# Tradvisor

Tradvisor V1 is being refocused around the Business Requirements Document in
`tradvisor_brd.md`.

The repository currently contains the data-ingestion foundation for BRVM market
data:

- `scripts/`: scrapers and loaders for shares, bonds, dividends, indices, and
  capitalizations.
- `terraform/`: Google Cloud infrastructure for storage buckets, Cloud
  Functions, Workflows, Scheduler jobs, BigQuery, IAM, and supporting services.
- `tradvisor_brd.md`: V1 business requirements for Swing recommendations,
  Long-Term scoring, and manual paper trading.

The previous Streamlit webapp has been removed so the next architecture pass can
target the V1 BRD cleanly.

## Terraform State

Terraform is configured to use a GCS backend. Initialize it with the project's
state bucket and prefix:

```sh
terraform -chdir=terraform init \
  -backend-config="bucket=<terraform-state-bucket>" \
  -backend-config="prefix=tradvisor"
```

Local `*.tfstate` files are ignored and should not be committed.
