from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS = (ROOT / "terraform" / "functions.tf").read_text()
IAM = (ROOT / "terraform" / "iam.tf").read_text()
RUNTIME = (ROOT / "terraform" / "runtime.tf").read_text()
VARIABLES = (ROOT / "terraform" / "variables.tf").read_text()
EVIDENCE = (ROOT / "docs" / "architecture" / "direct-scheduled-ingestion-inventory.md").read_text()


def test_inventory_covers_all_scheduled_workflows_and_callers() -> None:
    for source in ("shares", "dividends", "financials", "ratings"):
        assert f'writer_key = "stocks.{source}"' in FUNCTIONS
        assert f'`{source}-writer`' in EVIDENCE
        assert f'`{source}-job`' in EVIDENCE
        assert f'`{source}-wf`' in EVIDENCE

    assert 'resource "google_cloud_scheduler_job" "jobs"' in FUNCTIONS
    assert 'https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${each.value.name}-wf/executions' in FUNCTIONS
    scheduler = FUNCTIONS.split('resource "google_cloud_scheduler_job" "jobs"', 1)[1]
    assert 'cloudtasks.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/queues/${each.value.name}-writer/tasks' not in scheduler
    assert 'google_cloud_run_v2_service.workflow_dispatcher[0].uri}/internal/workflows/${each.value.name}-wf/dispatch' not in scheduler


def test_inventory_records_duration_retry_and_overlap_contracts() -> None:
    assert FUNCTIONS.count("timeout_seconds       = 180") == 1
    assert 'resource "google_cloud_scheduler_job" "jobs"' in FUNCTIONS
    assert "oauth_token {" in FUNCTIONS
    assert 'timeout         = "900s"' in RUNTIME
    assert "idempotency" in EVIDENCE
    assert "24 hours" in EVIDENCE
    assert "28 days" in EVIDENCE


def test_publication_control_is_outside_scheduled_retirement_boundary() -> None:
    assert "publication-control queue" in EVIDENCE
    assert "its IAM" in EVIDENCE
    assert "Cloud Tasks\nAPI enablement" in EVIDENCE
    assert "not\nscheduled ingestion" in EVIDENCE
    assert 'manage_legacy_schedules ? var.jobs : {}' in FUNCTIONS
    assert 'resource "google_cloud_tasks_queue" "workflow_writers"' not in FUNCTIONS
    assert 'resource "google_cloud_tasks_queue_iam_member" "workflow_queue_enqueuer"' not in IAM
    assert 'resource "google_project_iam_member" "terraform_deployer_cloudtasks_admin"' not in RUNTIME
    assert 'role     = "roles/run.invoker"' in IAM


def test_schedule_inventory_matches_declared_legacy_jobs() -> None:
    assert 'job1 = { name = "shares", schedule = "0 20 * * 1-5" }' in VARIABLES
    assert 'job3 = { name = "dividends", schedule = "0 20 1 * *" }' in VARIABLES
    assert 'job5 = { name = "financials", schedule = "0 20 1 * *" }' in VARIABLES
    assert 'job6 = { name = "ratings", schedule = "0 20 1 * *" }' in VARIABLES
    assert 'time_zone   = "Africa/Bamako"' in FUNCTIONS
