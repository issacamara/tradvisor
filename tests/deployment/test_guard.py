from pathlib import Path


def test_development_apply_is_manual_and_guarded() -> None:
    workflow = Path(".github/workflows/cd-development.yml").read_text()
    guard = Path("scripts/deployment/guard.sh").read_text()
    assert "workflow_dispatch" in workflow
    assert "branches: [development]" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "github.event_name == 'push' && 'apply'" not in workflow
    assert "github.event_name == 'push' && env.DELIVERY_ACTION == 'apply'" not in workflow
    assert "Select reviewed development plan" in workflow
    assert "Decide whether to deliver" in workflow
    assert 'echo "proceed=true"' in workflow
    assert "terraform plan -out=tfplan" in workflow
    assert "terraform apply -auto-approve \"$plan_path\"" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "terraform apply -auto-approve" in workflow
    assert "terraform-apply-diagnostic.txt" in workflow
    assert "Sanitized diagnostics:" in workflow
    assert "tail -80 terraform-apply-diagnostic.txt" in workflow
    assert "cp terraform-plan-diagnostic.txt" in workflow
    assert "cp terraform-plan.log" not in workflow
    assert "sanitize_terraform_diagnostics.py" in workflow
    assert "if: failure() && steps.delivery-gate.outputs.proceed == 'true' && env.DELIVERY_ACTION == 'apply'" in workflow
    assert "environment:" in workflow
    assert "google-github-actions/auth@v2" in workflow
    assert "DEV_WORKLOAD_IDENTITY_PROVIDER" in workflow
    assert "DEV_SERVICE_ACCOUNT" in workflow
    assert "openrouter_secret_id" in workflow
    assert "Verify OpenRouter secret has an enabled version" in workflow
    assert "verify_openrouter_secret_version.py" in workflow
    assert "github.ref_name == 'development'" in workflow
    assert "EXPECTED_PROJECT_ID" in guard
    assert "EXPECTED_STATE_BUCKET" in guard
    assert "EXPECTED_STATE_PREFIX" in guard
    assert '[[ "${TF_VAR_project_id}" == "${EXPECTED_PROJECT_ID}" ]]' in guard
    assert '[[ "${TF_STATE_BUCKET}" == "${EXPECTED_STATE_BUCKET}" ]]' in guard
    assert '[[ "${TF_STATE_PREFIX}" == "${EXPECTED_STATE_PREFIX}" ]]' in guard
    assert "dev-tradvisor" in workflow
    assert "dev-tradvisor-tfstate" in workflow
    assert "state/dev" in workflow
    assert "ALLOWED_BRANCH: development" in workflow


def test_terraform_plan_uses_configured_development_environment_for_dev_prs() -> None:
    workflow = Path(".github/workflows/terraform.yml").read_text()
    assert "github.base_ref == 'main' && 'production-plan'" in workflow
    assert "github.ref_name == 'main' && 'production'" in workflow
    assert "'development' }}" in workflow
    assert "development-plan" not in workflow
