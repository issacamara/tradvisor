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


def test_development_delivery_reconstructs_published_api_image() -> None:
    root = Path(__file__).parents[2]
    release = (root / ".github/workflows/release.yml").read_text()
    development = (root / ".github/workflows/cd-development.yml").read_text()
    image_path = "$GCP_REGION-docker.pkg.dev/$GCP_PROJECT_ID/$ARTIFACT_REPOSITORY/api"
    assert f'API_IMAGE="{image_path}:$GITHUB_SHA"' in release
    assert f'api_image="{image_path}:$RELEASE_ID@$digest"' in development
    assert "tradvisor-backend:$RELEASE_ID@$digest" not in development


def test_delivery_workflows_keep_plan_attestation_checks() -> None:
    root = Path(__file__).parents[2] / ".github/workflows"
    for environment in ("development", "production"):
        contents = (root / f"cd-{environment}.yml").read_text()
        assert "terraform_plan_attestation.py verify" in contents
        assert "terraform_plan_attestation.py create" in contents
        assert "path: terraform-plan-artifact/" not in contents
    production = root / "cd-production.yml"
    production = production.read_text()
    assert "terraform_plan_run_id" in production
    assert "terraform apply -auto-approve ../reviewed-plan/tfplan" in production
    assert "gcloud storage cp --no-clobber reviewed-plan.tar.gz" in production


def test_development_delivery_consumes_successful_ci_release() -> None:
    root = Path(__file__).parents[2] / ".github/workflows"
    development = (root / "cd-development.yml").read_text()
    ci = (root / "ci.yml").read_text()
    production = (root / "cd-production.yml").read_text()
    release = (root / "release.yml").read_text()
    assert "workflow_call:" in development
    assert "github.event_name == 'workflow_call'" in development
    assert "github.event_name == 'workflow_dispatch'" in development
    assert "github.event_name == 'workflow_call' && env.DELIVERY_ACTION == 'apply'" in development
    assert "terraform apply -auto-approve \"$plan_path\"" in development
    assert "Verify manually supplied development Terraform plan" in development
    assert "Verify automatically generated development Terraform plan" in development
    assert "github.event_name == 'workflow_call' && env.DELIVERY_ACTION == 'apply'" in development
    assert "openrouter_secret_id" in development
    assert "verify_openrouter_secret_version.py" in development
    assert "gcloud storage ls \"gs://$TF_STATE_BUCKET/reviewed-plans/development" not in development
    assert "steps.release-image.outputs.api_image" in development
    assert "github.event_name == 'push' && github.ref_name == 'development'" in ci
    assert "uses: ./.github/workflows/release.yml" in ci
    assert "needs: [validate, frontend]" in ci
    assert "needs: release" in ci
    assert "uses: ./.github/workflows/cd-development.yml" in ci
    assert "workflow_dispatch:" in development
    assert "branches: [main]" in production
    assert "github.event_name == 'workflow_dispatch'" in production
    assert "git rev-parse \"$GITHUB_SHA^{tree}\"" in production
    assert '["backend"]["digest"]' in production
    assert "tradvisor-development-deployed-" in development
    assert "Require successful development deployment" in production
    assert "workflow_call:" in release
    assert 'grep -Eq \'^sha256:[0-9a-f]{64}$\'' in release


def test_development_imports_complete_before_reviewed_plan_generation() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/cd-development.yml").read_text()
    import_step = workflow.split("      - name: Import existing development shares table", 1)[1].split("      - name:", 1)[0]
    assert "env.DELIVERY_ACTION == 'import'" in import_step
    assert "env.DELIVERY_ACTION == 'apply'" not in import_step
    assert workflow.index("Import existing development shares table") < workflow.index("Plan development changes")
    assert "terraform import \"$address\" \"$resource_id\"" in import_step

