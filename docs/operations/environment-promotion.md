# Environment Promotion

Tradvisor deployments use the same repository code with environment-specific
GitHub Environment configuration. The current delivery workflow targets
`development` from branch `V1`; production delivery must use a protected
production environment and a separately approved production branch or tag.

The environment-to-project mapping is:

- `development` -> `dev-tradvisor`
- `production` -> `prod-tradvisor`

## Required environment values

Each GitHub Environment must define these variables:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `TF_STATE_BUCKET`
- `TF_STATE_PREFIX`
- `TRADVISOR_API_URL`
- `TRADVISOR_CORS_ORIGINS`

Each environment must also provide its own workload identity provider,
deployment service account, and Firebase API key as secrets. Terraform state,
service accounts, secrets, Firebase projects, and Artifact Registry repositories
must never be shared between development and production.

## Promotion rules

1. Build and test the commit on `V1`.
2. Deploy and smoke-test development.
3. Promote the same immutable API image digest to production.
4. Run a production Terraform plan using the production state backend.
5. Require production environment approval before apply.
6. Run authentication, API health, Swing, Long-Term, and Paper Trading smoke tests.

The development workflow has safe defaults for the existing `dev-tradvisor`
configuration. Production values must be configured in GitHub before a
production workflow is enabled; no production state or credentials belong in
the repository.
