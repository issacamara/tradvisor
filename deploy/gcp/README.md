# GCP deployment target

Tradvisor deploys to Google Cloud for development (`dev-tradvisor`) and production (`prod-tradvisor`). This file only points to the existing sources; it does not replace them.

- Infrastructure: `terraform/` (Terraform-managed tables and resources).
- Delivery: `.github/workflows/cd-development.yml`, `cd-production.yml`, `terraform.yml`, `release.yml`.
- Operations and promotion: `docs/operations/` (see `environment-promotion.md`).

Cloud plans, applies, migrations, paid queries, seeding and schedule activation need the separate owner approval stated in `AGENTS.md`.
