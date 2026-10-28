from pathlib import Path


def test_development_delivery_is_automatic_and_guarded() -> None:
    workflow = Path(".github/workflows/cd-development.yml").read_text()
    guard = Path("scripts/deployment/guard.sh").read_text()
    assert "workflow_dispatch" in workflow
    assert "branches: [development]" in workflow
    assert "Select reviewed development plan" in workflow
    assert "Decide whether to deliver" in workflow
    assert 'echo "proceed=true"' in workflow
    assert "terraform plan -out=tfplan" in workflow
    assert "terraform apply -auto-approve \"$plan_path\"" in workflow
    assert "terraform apply -auto-approve" in workflow
    assert "terraform-apply-diagnostic.txt" in workflow
    assert "Sanitized diagnostics:" in workflow
    assert "tail -80 terraform-apply.log" in workflow
    assert "if: failure() && steps.delivery-gate.outputs.proceed == 'true' && env.DELIVERY_ACTION == 'apply'" in workflow
    assert "environment:" in workflow
    assert "google-github-actions/auth@v2" in workflow
    assert "DEV_WORKLOAD_IDENTITY_PROVIDER" in workflow
    assert "DEV_SERVICE_ACCOUNT" in workflow
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
