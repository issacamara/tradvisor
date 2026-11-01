from pathlib import Path
import re


ROOT = Path(__file__).parents[3]
FUNCTIONS = (ROOT / "terraform/functions.tf").read_text()
FI1 = (ROOT / "terraform/fi1_financial.tf").read_text()
IAM = (ROOT / "terraform/iam.tf").read_text()
VARIABLES = (ROOT / "terraform/variables.tf").read_text()
DELIVERY = (ROOT / ".github/workflows/cd-development.yml").read_text()
PRODUCTION = (ROOT / ".github/workflows/cd-production.yml").read_text()
SECRET_DOC = (ROOT / "docs/operations/openrouter-secret.md").read_text()
OPENROUTER_TOKEN = re.compile(r"sk-or-v1-[A-Za-z0-9_-]{24,}")


def _block(source: str, declaration: str, name: str) -> str:
    match = re.search(
        rf'{re.escape(declaration)}\s+"{re.escape(name)}"\s*\{{',
        source,
    )
    assert match, f"missing {declaration}.{name}"
    start = match.end()
    depth = 1
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError(f"unclosed {declaration}.{name}")


def _resource(source: str, resource_type: str, name: str) -> str:
    return _block(source, f'resource "{resource_type}"', name)


def test_openrouter_secret_input_and_metadata_are_nonsecret_and_protected() -> None:
    variable = _block(VARIABLES, "variable", "openrouter_secret_id")
    secret = _resource(IAM, "google_secret_manager_secret", "openrouter")

    assert "type        = string" in variable
    assert "validation {" in variable
    assert "secret_id = var.openrouter_secret_id" in secret
    assert "project   = var.project_id" in secret
    assert "prevent_destroy = true" in secret
    assert 'var.v1_environment_project_id == var.project_id' in secret
    assert 'resource "google_secret_manager_secret_version" "openrouter"' not in IAM
    assert "secret_data" not in secret


def test_secret_accessor_is_bound_only_to_the_declared_secret_and_fi1_identity() -> None:
    binding = _resource(IAM, "google_secret_manager_secret_iam_member", "fi1_financial_openrouter")

    assert "google_secret_manager_secret.openrouter.project" in binding
    assert "google_secret_manager_secret.openrouter.secret_id" in binding
    assert 'role      = "roles/secretmanager.secretAccessor"' in binding
    assert 'member    = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"' in binding
    assert 'resource "google_project_iam_binding" "sms_accessor"' in IAM
    assert "fi1_financial_runtime" not in _resource(IAM, "google_project_iam_binding", "sms_accessor")


def test_only_fi1_job_receives_the_secret_environment_variable() -> None:
    job = _resource(FI1, "google_cloud_run_v2_job", "fi1_financials")
    assert 'name = "OPENROUTER_API_KEY"' in job
    assert "value_source" in job and "secret_key_ref" in job
    assert "google_secret_manager_secret.openrouter.secret_id" in job
    assert 'version = "latest"' in job
    assert "OPENROUTER_API_KEY" not in FUNCTIONS


def test_secret_project_follows_the_explicit_environment_project_binding() -> None:
    secret = _resource(IAM, "google_secret_manager_secret", "openrouter")
    job = _resource(FI1, "google_cloud_run_v2_job", "fi1_financials")

    assert "project   = var.project_id" in secret
    assert 'var.v1_environment_project_id == var.project_id' in job
    assert "development" in job and "production" in job


def test_delivery_and_operator_docs_exclude_payloads_and_require_enabled_version() -> None:
    assert "openrouter_secret_id" in DELIVERY
    assert "TF_VAR_openrouter_secret_id: ${{ inputs.openrouter_secret_id || 'openrouter-api-key' }}" in DELIVERY
    assert "Verify OpenRouter secret has an enabled version" in DELIVERY
    assert "verify_openrouter_secret_version.py" in DELIVERY
    assert "OPENROUTER_API_KEY" not in DELIVERY
    assert "authorized operator provisions the key" in SECRET_DOC.lower()
    assert "enabled version" in SECRET_DOC.lower()
    assert "rotation" in SECRET_DOC.lower()
    assert "payload" in SECRET_DOC.lower()
    assert "TF_VAR_project_id: ${{ vars.GCP_PROJECT_ID || 'prod-tradvisor' }}" in PRODUCTION
    assert "TF_VAR_v1_environment_project_id: ${{ vars.GCP_PROJECT_ID || 'prod-tradvisor' }}" in PRODUCTION


def test_secret_payload_wiring_is_absent_from_terraform_and_workflows() -> None:
    assert 'key = "OPENROUTER_API_KEY"' not in FUNCTIONS
    for source in (FUNCTIONS, IAM, FI1, DELIVERY, PRODUCTION):
        assert "OPENROUTER_API_KEY =" not in source
        assert "OPENROUTER_API_KEY=" not in source


def test_no_credential_looking_openrouter_value_is_committed_in_code_or_ci_fixtures() -> None:
    protected_roots = (
        ROOT / "terraform",
        ROOT / ".github/workflows",
        ROOT / "tests/deployment",
        ROOT / "functions/financials",
        ROOT / "backend",
    )
    for protected_root in protected_roots:
        if not protected_root.exists():
            continue
        for path in protected_root.rglob("*"):
            if path.is_file() and path.suffix in {".tf", ".yml", ".yaml", ".py"}:
                assert not OPENROUTER_TOKEN.search(path.read_text()), path.relative_to(ROOT)
