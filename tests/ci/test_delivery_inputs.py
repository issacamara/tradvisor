from pathlib import Path

from scripts.ci.verify_delivery_inputs import validate


def test_delivery_inputs_are_pinned() -> None:
    validate(Path(__file__).parents[2])


def test_delivery_workflows_require_immutable_api_digests() -> None:
    root = Path(__file__).parents[2]
    for workflow in (
        root / ".github/workflows/cd-development.yml",
        root / ".github/workflows/cd-production.yml",
    ):
        contents = workflow.read_text()
        assert "/*@sha256:*)" in contents
        assert "must be an immutable digest" in contents
        assert "does not match the release manifest backend digest" in contents


def test_release_workflow_packages_and_uploads_manifest() -> None:
    contents = (Path(__file__).parents[2] / ".github/workflows/release.yml").read_text()
    assert "package_artifact.py" in contents
    assert "manifest.py" in contents
    assert "actions/upload-artifact@v4" in contents


def test_delivery_workflows_require_exact_reviewed_terraform_plans() -> None:
    root = Path(__file__).parents[2]
    for environment in ("development", "production"):
        contents = (root / f".github/workflows/cd-{environment}.yml").read_text()
        assert "terraform_plan_run_id" in contents
        assert "terraform_plan_attestation.py verify" in contents
        assert "terraform_plan_attestation.py create" in contents
        assert "terraform apply -auto-approve ../reviewed-plan/tfplan" in contents
        assert "gcloud storage cp --no-clobber reviewed-plan.tar.gz" in contents
        assert "actions/upload-artifact@v4" not in contents


def test_push_prepares_release_without_unreviewed_apply() -> None:
    root = Path(__file__).parents[2] / ".github/workflows"
    development = (root / "cd-development.yml").read_text()
    production = (root / "cd-production.yml").read_text()
    release = (root / "release.yml").read_text()
    assert "branches: [development]" in development
    assert "uses: ./.github/workflows/release.yml" in development
    assert "github.event_name == 'workflow_dispatch'" in development
    assert "branches: [main]" in production
    assert "github.event_name == 'workflow_dispatch'" in production
    assert "git rev-parse \"$GITHUB_SHA^{tree}\"" in production
    assert '["backend"]["digest"]' in production
    assert "workflow_call:" in release
    assert 'grep -Eq \'^sha256:[0-9a-f]{64}$\'' in release
