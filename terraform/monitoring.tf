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

# Publication-control events are deliberately bounded in backend.observability.events.
resource "google_logging_metric" "publication_control_failures" {
  count  = local.v1_monitoring_enabled ? 1 : 0
  name   = "tradvisor_v1_publication_control_failures"
  filter = "jsonPayload.tradvisor.event = \"publication.control\" AND (jsonPayload.tradvisor.control_outcome = \"analytical_failed\" OR jsonPayload.tradvisor.control_outcome = \"retry_exhausted\")"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "publication_dispatch_missing" {
  count  = local.v1_monitoring_enabled ? 1 : 0
  name   = "tradvisor_v1_publication_dispatch_missing"
  filter = "jsonPayload.tradvisor.event = \"publication.control\" AND jsonPayload.tradvisor.control_outcome = \"missing_dispatch_outcome\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "publication_duplicate_not_collapsed" {
  count  = local.v1_monitoring_enabled ? 1 : 0
  name   = "tradvisor_v1_publication_duplicate_not_collapsed"
  filter = "jsonPayload.tradvisor.event = \"publication.control\" AND jsonPayload.tradvisor.control_outcome = \"duplicate_not_collapsed\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "publication_freshness_lag" {
  count           = local.v1_monitoring_enabled ? 1 : 0
  name            = "tradvisor_v1_publication_freshness_lag_ms"
  filter          = "jsonPayload.tradvisor.event = \"publication.control\" AND jsonPayload.tradvisor.control_outcome = \"published\""
  value_extractor = "EXTRACT(jsonPayload.tradvisor.duration_ms)"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "ms"
  }
}

resource "google_monitoring_alert_policy" "publication_control" {
  count        = local.v1_monitoring_enabled ? 1 : 0
  display_name = "Tradvisor V1 publication control failures"
  combiner     = "OR"

  dynamic "conditions" {
    for_each = {
      failed    = "logging.googleapis.com/user/tradvisor_v1_publication_control_failures"
      missing   = "logging.googleapis.com/user/tradvisor_v1_publication_dispatch_missing"
      duplicate = "logging.googleapis.com/user/tradvisor_v1_publication_duplicate_not_collapsed"
    }
    content {
      display_name = "Publication control ${conditions.key}"
      condition_threshold {
        filter          = "metric.type=\"${conditions.value}\" resource.type=\"global\""
        comparison      = "COMPARISON_GT"
        threshold_value = 0
        duration        = "0s"
        aggregations {
          alignment_period   = "${var.v1_monitoring_check_interval_seconds}s"
          per_series_aligner = "ALIGN_SUM"
        }
      }
    }
  }

  documentation {
    content   = "Inspect only sanitized completion/control events. Preserve the previous complete batch; manual job execution is recovery-only and needs separate owner approval."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "publication_freshness" {
  count        = local.v1_monitoring_enabled ? 1 : 0
  display_name = "Tradvisor V1 publication freshness exceeds 15 minutes"
  combiner     = "OR"

  conditions {
    display_name = "Managed write to active publication lag"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/tradvisor_v1_publication_freshness_lag_ms\" resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 900000
      duration        = "0s"
      aggregations {
        alignment_period   = "${var.v1_monitoring_check_interval_seconds}s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  documentation {
    content   = "A successful shares or financials managed write has exceeded the ready-input target before confirmed active publication. Preserve the previous complete batch; manual recovery needs separate owner approval."
    mime_type = "text/markdown"
  }
}
