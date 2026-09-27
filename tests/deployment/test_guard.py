from pathlib import Path


def test_development_delivery_is_manual_and_guarded() -> None:
    workflow = Path(".github/workflows/v1-development-delivery.yml").read_text()
    guard = Path("scripts/deployment/guard.sh").read_text()
    assert "workflow_dispatch" in workflow
    assert "terraform apply -auto-approve" in workflow
    assert "environment:" in workflow
    assert "google-github-actions/auth@v2" in workflow
    assert "DEV_WORKLOAD_IDENTITY_PROVIDER" in workflow
    assert "DEV_SERVICE_ACCOUNT" in workflow
    assert "github.ref_name == 'V1'" in workflow
    assert "dev-tradvisor" in guard
    assert "dev-tradvisor-tfstate" in guard
    assert "state/dev" in guard
