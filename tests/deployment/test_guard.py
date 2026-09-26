from pathlib import Path


def test_development_delivery_is_manual_and_guarded() -> None:
    workflow = Path(".github/workflows/deploy.yml").read_text()
    guard = Path("scripts/deployment/guard.sh").read_text()
    assert "workflow_dispatch" in workflow
    assert "terraform apply -auto-approve" in workflow
    assert "environment:" in workflow
    assert "github.ref_name == 'V1'" in workflow
    assert "dev-tradvisor" in guard
    assert "dev-tradvisor-tfstate" in guard
    assert "state/dev" in guard
