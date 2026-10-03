locals {
  v1_monitoring_enabled = var.configure_v1_monitoring && contains(["development", "production"], var.environment)
}

resource "google_logging_project_bucket_config" "v1_application" {
  count          = local.v1_monitoring_enabled ? 1 : 0
  project        = var.project_id
  location       = "global"
  bucket_id      = "tradvisor-v1-application"
  retention_days = var.v1_log_retention_days
  description    = "Bounded sanitized Tradvisor V1 application events"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_logging_metric" "v1_failures" {
  count  = local.v1_monitoring_enabled ? 1 : 0
  name   = "tradvisor_v1_operational_failures"
  filter = "jsonPayload.tradvisor.event != \"\" AND jsonPayload.tradvisor.outcome = \"failure\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_alert_policy" "v1_failures" {
  count        = local.v1_monitoring_enabled ? 1 : 0
  display_name = "Tradvisor V1 operational failures"
  combiner     = "OR"

  conditions {
    display_name = "Sanitized operational failures"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/tradvisor_v1_operational_failures\" resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "${var.v1_monitoring_check_interval_seconds}s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  documentation {
    content   = "Inspect sanitized event codes and freshness evidence. Do not include credentials or personal data."
    mime_type = "text/markdown"
  }
}
