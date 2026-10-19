from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TERRAFORM = ROOT / "terraform"


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
