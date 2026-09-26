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
