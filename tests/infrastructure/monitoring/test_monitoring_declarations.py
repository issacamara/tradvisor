from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TERRAFORM = ROOT / "terraform"
MONITORING_DOC = ROOT / "docs" / "operations" / "monitoring.md"


def test_monitoring_is_opt_in_and_bounded() -> None:
    variables = (TERRAFORM / "variables.tf").read_text(encoding="utf-8")
    monitoring = (TERRAFORM / "monitoring.tf").read_text(encoding="utf-8")
    assert 'variable "configure_v1_monitoring"' in variables
    assert "default     = false" in variables
    assert "retention_days = var.v1_log_retention_days" in monitoring
    assert "local.v1_monitoring_enabled" in monitoring
    assert 'duration        = "0s"' in monitoring
    assert "allUsers" not in monitoring


def test_publication_control_conditions_are_distinct_and_sanitized() -> None:
    monitoring = (TERRAFORM / "monitoring.tf").read_text(encoding="utf-8")
    assert 'resource "google_logging_metric" "publication_control_failures"' in monitoring
    assert 'resource "google_logging_metric" "publication_dispatch_missing"' in monitoring
    assert 'resource "google_logging_metric" "publication_duplicate_not_collapsed"' in monitoring
    assert 'resource "google_logging_metric" "publication_freshness_lag"' in monitoring
    assert "analytical_failed" in monitoring
    assert "retry_exhausted" in monitoring
    assert "missing_dispatch_outcome" in monitoring
    assert "duplicate_not_collapsed" in monitoring
    assert "source payload" not in monitoring.lower()
    assert "manual job execution is recovery-only" in monitoring
    assert "threshold_value = 900000" in monitoring


def test_scheduler_delivery_and_workflow_execution_failures_are_independent() -> None:
    monitoring = (TERRAFORM / "monitoring.tf").read_text(encoding="utf-8")

    assert 'resource "google_logging_metric" "scheduler_delivery_failures"' in monitoring
    assert 'resource "google_logging_metric" "workflow_execution_failures"' in monitoring
    assert 'resource "google_monitoring_alert_policy" "scheduler_delivery_failures"' in monitoring
    assert 'resource "google_monitoring_alert_policy" "workflow_execution_failures"' in monitoring
    assert 'log_id(\\"scheduler.googleapis.com%2Fexecutions\\")' in monitoring
    assert 'resource.type=\\"workflows.googleapis.com/Workflow\\"' in monitoring
    assert "jsonPayload.status >= 200" in monitoring
    assert 'jsonPayload.state = \\"FAILED\\"' in monitoring

    for source in ("shares", "dividends", "financials", "ratings"):
        assert source in monitoring

    assert "user data" not in monitoring.lower()
    assert "service_account_email" not in monitoring
    assert "password" not in monitoring.lower()


def test_monitoring_guidance_distinguishes_acceptance_from_completion() -> None:
    guidance = MONITORING_DOC.read_text(encoding="utf-8")

    assert "a 2xx response means execution accepted, not completed" in guidance
    assert "terminal `FAILED`" in guidance
    assert "Scheduler delivery acceptance" in guidance
    for source in ("shares", "dividends", "financials", "ratings"):
        assert f"`{source}`" in guidance
