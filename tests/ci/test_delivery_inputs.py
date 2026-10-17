from pathlib import Path

from scripts.ci.verify_delivery_inputs import validate


def test_delivery_inputs_are_pinned() -> None:
    validate(Path(__file__).parents[2])


def test_delivery_workflows_require_immutable_api_digests() -> None:
    root = Path(__file__).parents[2]
    for workflow in (
        root / ".github/workflows/v1-development-delivery.yml",
        root / ".github/workflows/v1-production-delivery.yml",
    ):
        contents = workflow.read_text()
        assert "/*@sha256:*)" in contents
        assert "must be an immutable digest" in contents
        assert "does not match the release manifest backend digest" in contents


def test_release_workflow_packages_and_uploads_manifest() -> None:
    contents = (Path(__file__).parents[2] / ".github/workflows/v1-release.yml").read_text()
    assert "package_artifact.py" in contents
    assert "manifest.py" in contents
    assert "actions/upload-artifact@v4" in contents


def test_delivery_workflows_require_exact_reviewed_terraform_plans() -> None:
    root = Path(__file__).parents[2]
    for environment in ("development", "production"):
        contents = (root / f".github/workflows/v1-{environment}-delivery.yml").read_text()
        assert "terraform_plan_run_id" in contents
        assert "terraform_plan_attestation.py verify" in contents
        assert "terraform_plan_attestation.py create" in contents
        assert "terraform apply -auto-approve ../reviewed-plan/tfplan" in contents
