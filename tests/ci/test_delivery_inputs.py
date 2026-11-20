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


def test_fi1_job_image_is_built_pinned_and_promoted_by_digest() -> None:
    root = Path(__file__).parents[2]
    release = (root / ".github/workflows/release.yml").read_text()
    development = (root / ".github/workflows/cd-development.yml").read_text()
    production = (root / ".github/workflows/cd-production.yml").read_text()
    dockerfile = (root / "functions/financials/Dockerfile").read_text()
    entrypoint = (root / "functions/financials/scrape_financials_job.py").read_text()

    assert "requirements.lock" in dockerfile
    assert "--require-hashes" in dockerfile
    assert 'ENTRYPOINT ["scrape_financials"]' in dockerfile
    assert "from .fi1_job import main" in entrypoint
    assert "--fi1-job-digest" in release
    assert '["fi1_job"]["digest"]' in development
    assert "promoted_fi1_digest" in production


def test_development_manages_fi1_job_without_activating_schedule() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/cd-development.yml").read_text()

    for step_name in ("Plan development changes", "Apply reviewed development plan"):
        step = workflow.split(f"      - name: {step_name}", 1)[1].split("      - name:", 1)[0]
        environment = step.split("        env:\n", 1)[1].split("        run:\n", 1)[0]
        assert 'TF_VAR_manage_fi1_financial_job: "true"' in environment
        assert "TF_VAR_activate_fi1_financial_schedule" not in environment


def test_terraform_pr_plan_resolves_development_fi1_from_deployment_evidence() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/terraform.yml").read_text()
    assert "TF_VAR_manage_fi1_financial_job:" in workflow
    assert "actions: read" in workflow
    assert "tradvisor-development-deployed-" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "ARTIFACT_REPOSITORY: ${{ vars.ARTIFACT_REPOSITORY }}" in workflow
    assert "development\\tpush\\tsuccess" in workflow
    assert "development\\tworkflow_dispatch\\tsuccess" in workflow
    assert 'evidence["fi1_job_digest"]' in workflow
    assert 'sha256:[0-9a-f]{64}' in workflow
    assert "vars.APPROVED_FI1_JOB_IMAGE" not in workflow
    assert 'TF_VAR_environment" = development' in workflow
    assert "TF_VAR_fi1_financial_job_image" in workflow


def test_terraform_plan_runs_private_fi1_staging_preservation_guard() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/terraform.yml").read_text()
    step = workflow.split("      - name: Plan without publishing state or plan contents", 1)[1]
    assert 'if [ "$FI1_STAGING_TRANSITION" = true ]; then' in step
    assert "Detect FI-1 staging transition" in workflow
    assert "github.event.pull_request.base.sha || github.event.before" in workflow
    assert 'enabled=$transition' in workflow
    assert 'FI1_STAGING_TRANSITION: ${{ steps.fi1-staging-transition.outputs.enabled }}' in workflow
    assert "classify_fi1_baseline_plan.py" in step
    assert step.index("classify_fi1_baseline_plan.py") < step.index("verify_fi1_staging_plan.py")
    assert "terraform show -json tfplan | python3 ../scripts/deployment/verify_fi1_staging_plan.py" in step
    assert "FI-1 staging transition base is unavailable." in workflow
    assert "if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository" in workflow


def test_development_pr_plan_uses_pinned_base_and_ephemeral_comparison_only() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/terraform.yml").read_text()
    deployed_images = workflow.split("      - name: Resolve deployed API and FI-1 images", 1)[1].split("\n      - name:", 1)[0]
    baseline = workflow.split("      - name: Prepare development baseline checkout", 1)[1].split("\n      - name:", 1)[0]
    plan = workflow.split("      - name: Plan without publishing state or plan contents", 1)[1]
    assert "github.event.pull_request.base.sha || github.event.before" in workflow
    assert "steps.fi1-staging-transition.outputs.base_sha" in baseline
    assert 'git worktree add --detach "$baseline_root" "$BASE_SHA"' in baseline
    assert "retired-workflow-dispatcher.tf" in baseline
    assert 'git show "$BASE_SHA:.github/workflows/terraform.yml"' in baseline
    assert "extract_dispatcher_step" in baseline
    assert "proposed-dispatcher-step.txt" in baseline
    assert "baseline-dispatcher-step.txt" in baseline
    assert 'evidence["backend_digest"]' in deployed_images
    assert 'evidence["fi1_job_digest"]' in deployed_images
    assert "/api:" in deployed_images and "backend_digest" in deployed_images
    assert "api:{evidence['release_id']}@{backend_digest}" in deployed_images
    assert "financial-ingestion:{evidence['release_id']}@{fi1_digest}" in deployed_images
    assert "::add-mask::{api_image}" in deployed_images
    assert "::add-mask::{fi1_image}" in deployed_images
    assert deployed_images.index("::add-mask::{api_image}") < deployed_images.index(
        "api_image={api_image}"
    )
    assert deployed_images.index("::add-mask::{fi1_image}") < deployed_images.index(
        "fi1_image={fi1_image}"
    )
    assert "api_image={api_image}" in deployed_images
    assert "fi1_image={fi1_image}" in deployed_images
    assert "steps.deployed-images.outputs.api_image" in workflow
    assert "steps.deployed-images.outputs.fi1_image" in workflow
    assert "vars.APPROVED_API_IMAGE" in workflow
    assert workflow.count(
        "env.TF_VAR_environment == 'development' && "
        "steps.deployed-images.outputs.api_image || vars.APPROVED_API_IMAGE"
    ) == 4
    assert '[[ "$TF_VAR_v1_batch_image" =~' in workflow
    assert 'cmp -s .terraform.lock.hcl "$baseline_root/terraform/.terraform.lock.hcl"' in plan
    assert '--state-bucket "$TF_STATE_BUCKET"' in plan
    assert '--state-prefix "$TF_STATE_PREFIX"' in plan
    assert '--gcp-project "$GCP_PROJECT_ID"' in plan
    assert "google-github-actions/setup-gcloud@v2" in workflow
    assert 'bucket=$TF_STATE_BUCKET' in plan
    assert 'prefix=$TF_STATE_PREFIX' in plan
    assert '"$RUNNER_TEMP/development-baseline.tfplan"' in plan
    assert '"$TF_STATE_BUCKET"' in plan
    assert '"$TF_STATE_PREFIX"' in plan
    assert 'trap cleanup_private_plans EXIT' in plan
    assert 'rm -f tfplan "$RUNNER_TEMP/development-baseline.tfplan"' in plan
    assert "actions/upload-artifact@v4" not in plan
    comparator = (Path(__file__).parents[2] / "scripts/deployment/classify_fi1_baseline_plan.py").read_text()
    assert '["workspace", "show"]' in comparator
    assert 'workspace.strip() != "default"' in comparator
    assert '}/default.tfstate"' in comparator
    assert '"storage",' in comparator and '"objects",' in comparator
    assert '"describe"' in comparator
    assert '"--format=value(generation)"' in comparator
    assert '"--quiet"' in comparator
    assert "baseline_generation_before" in comparator
    assert "baseline_generation_after" in comparator
    assert "proposed_generation_before" in comparator
    assert "proposed_generation_after" in comparator
    assert "state pull" not in comparator
    assert "capture_output=True" in comparator


def test_terraform_pr_plan_preserves_publication_control_service_url() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/terraform.yml").read_text()
    step = workflow.split("      - name: Plan without publishing state or plan contents", 1)[1]
    environment = step.split("        env:\n", 1)[1].split("        run:\n", 1)[0]
    assert (
        "TF_VAR_publication_control_service_url: "
        "${{ vars.TRADVISOR_PUBLICATION_CONTROL_SERVICE_URL }}"
    ) in environment


def test_terraform_pr_plan_stages_development_dispatcher_prepare_phase() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/terraform.yml").read_text()
    step = workflow.split("      - name: Stage development dispatcher prepare phase", 1)[1].split("      -", 1)[0]
    assert "if: env.TF_VAR_environment == 'development'" in step
    assert 'resource "google_cloud_run_v2_service" "workflow_dispatcher"' in step
    assert 'deletion_protection = false' in step
    assert 'prevent_destroy = false' in step


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
    assert "inputs.automatic == true" in development
    assert "github.event_name == 'workflow_dispatch'" in development
    assert "inputs.automatic == true && env.DELIVERY_ACTION == 'apply'" in development
    assert "terraform apply -auto-approve \"$plan_path\"" in development
    assert "Verify manually supplied development Terraform plan" in development
    assert "Verify automatically generated development Terraform plan" in development
    assert "inputs.automatic == true && env.DELIVERY_ACTION == 'apply'" in development
    assert "openrouter_secret_id" in development
    assert "verify_openrouter_secret_version.py" in development
    assert "gcloud storage ls \"gs://$TF_STATE_BUCKET/reviewed-plans/development" not in development
    assert "steps.release-image.outputs.api_image" in development
    assert "github.event_name == 'push' && github.ref_name == 'development'" in ci
    assert "uses: ./.github/workflows/release.yml" in ci
    assert "needs: [validate, frontend]" in ci
    assert "needs: release" in ci
    assert "uses: ./.github/workflows/cd-development.yml" in ci
    assert "openrouter_secret_id: openrouter-api-key" in ci
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

