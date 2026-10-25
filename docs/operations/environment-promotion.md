# Environment Promotion

Tradvisor deployments use the same repository code with environment-specific
GitHub Environment configuration. Development delivery targets the protected
`development` branch; production delivery targets the protected `main` branch.

The environment-to-project mapping is:

- `development` -> `dev-tradvisor`
- `production` -> `prod-tradvisor`

The production delivery contract is:

- Branch: `main`
- Terraform state bucket: `prod-tradvisor-tfstate`
- Terraform state prefix: `state/prod`

## Required environment values

Each GitHub Environment must define these variables:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `TF_STATE_BUCKET`
- `TF_STATE_PREFIX`
- `TRADVISOR_API_URL`
- `TRADVISOR_CORS_ORIGINS`
- `ARTIFACT_REPOSITORY` (the repository name used in each project's registry)
- `APPROVED_API_IMAGE` (an environment-local image digest for Terraform PR plans)

Each environment must provide `WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`, and
`FIREBASE_API_KEY` as scoped secrets. The production environment also defines
`DEVELOPMENT_PROJECT_ID=dev-tradvisor`. Both Firebase Hosting deployments use
the same project ID as their GCP environment: `dev-tradvisor` or
`prod-tradvisor`. The production deployment identity needs read access to the
development Artifact Registry and write access to the production registry.
Terraform state,
service accounts, secrets, Firebase projects, and Artifact Registry repositories
must never be shared between development and production.

Protect both branches against direct pushes. Rename `V1` to `development`
only after these environment values and branch protections are configured.
Production requires environment reviewers and a wait timer. Configure WIF trust
for the intended branch and same-repository PR plan refs; never grant a fork PR
deployment credentials.

## Promotion rules

1. CI checks each PR. A push to `development` builds the backend image once,
   resolves its registry digest, and creates the commit-bound release manifest.
2. Dispatch development `plan` with the release ID, release run ID, and exact
   development image digest. Review the saved plan, then dispatch `apply` with
   its plan run ID. Apply verifies the manifest and saved-plan attestation,
   deploys Cloud Run through Terraform, then builds and deploys the static
   frontend to development Firebase Hosting. The workflow checks the API
   health endpoint and Hosting response, then records non-secret deployment
   evidence. Complete the authenticated Swing and Long-Term smoke review.
3. Merge the tested development tree into `main` with a merge commit. The
   production push checks the matching development commit, release manifest,
   and successful development deployment evidence, then copies that image
   digest to the production registry after production environment approval.
   Hotfixes must pass development first.
4. Dispatch production `plan` with the release and promoted production digest.
   Review the saved plan, then dispatch `apply` with its plan run ID. Apply
   verifies the exact plan, deploys Cloud Run through Terraform, and builds the
   environment-specific static frontend for production Firebase Hosting.
5. Run authentication, API health, Swing, and Long-Term smoke tests. Production
   promotion and apply require the production environment approval gate.

`terraform.yml` runs a target-state plan for same-repository PRs and merged
Terraform changes. It emits only action counts. It does not apply on merge:
the reviewed, exact-plan gate governs both environments. Delivery saves plan
bundles privately under each environment's existing GCS state bucket, keyed
by plan run ID; no Terraform plan or state file is uploaded as a public GitHub
artifact. Plan approval and any initial resource bootstrap remain operator
actions. No production state or credentials belong in the repository.
