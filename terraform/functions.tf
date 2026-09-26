resource "google_cloudfunctions2_function" "functions" {
  depends_on = [google_project_service.apis, data.google_project.project]
  for_each   = toset(var.functions)
  name       = "${each.key}_function"
  location   = var.region
  build_config {
    #     runtime     = "python39"
    runtime     = var.function_runtimes[each.key]
    entry_point = "entry_point" # Set the entry point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = "${each.key}.zip"
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }

  lifecycle {
    # Existing Gen 2 functions retain their deployed source until a separately
    # approved deployment migration takes ownership of source artifacts.
    prevent_destroy = true
    ignore_changes  = all
  }
}


locals {
  workflow_stages = [
    { source = "shares", functions = ["scrape_shares", "insert_shares"], targets = ["stocks.shares"], writer_key = "stocks.shares" },
    { source = "bonds", functions = ["scrape_bonds", "insert_bonds"], targets = ["stocks.bonds"], writer_key = "stocks.bonds" },
    { source = "dividends", functions = ["scrape_dividends", "insert_dividends"], targets = ["stocks.dividends"], writer_key = "stocks.dividends" },
    { source = "capitalizations", functions = ["scrape_capitalizations", "insert_capitalizations"], targets = ["stocks.capitalizations"], writer_key = "stocks.capitalizations" },
    { source = "financials", functions = ["scrape_financials", "insert_financials"], targets = ["stocks.financials"], writer_key = "stocks.financials" },
    { source = "ratings", functions = ["scrape_ratings", "insert_ratings"], targets = ["stocks.ratings"], writer_key = "stocks.ratings" },
  ]
  workflow_writer_keys = { for stage in local.workflow_stages : stage.writer_key => stage.source }
  workflow_by_source   = { for stage in local.workflow_stages : stage.source => stage }
  paused_schedule_keys = toset(["job5", "job6"])
}

resource "google_workflows_workflow" "workflows" {
  depends_on      = [google_cloudfunctions2_function.functions, google_project_service.apis]
  count           = var.manage_legacy_workflows ? length(var.functions) / 2 : 0
  name            = "${local.workflow_stages[count.index].source}-wf"
  region          = var.region
  description     = "Ordered ${local.workflow_stages[count.index].source} ingestion and persistence stages"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
%{for function_name in local.workflow_stages[count.index].functions~}
    - ${function_name}:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions[function_name].service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions[function_name].service_config[0].uri}
%{endfor~}
EOF

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "google_cloud_tasks_queue" "workflow_writers" {
  for_each = var.manage_legacy_schedules ? local.workflow_writer_keys : {}

  name     = "${each.value}-writer"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 1
    max_dispatches_per_second = 1
  }

  retry_config {
    max_attempts = 1
  }

  lifecycle {
    prevent_destroy = true
  }
}


resource "google_cloud_scheduler_job" "jobs" {
  depends_on = [google_cloud_tasks_queue.workflow_writers, google_workflows_workflow.workflows, google_project_service.apis]
  #   for_each = { for wf in google_workflows_workflow.workflows : wf.name => wf }
  for_each    = var.manage_legacy_schedules ? var.jobs : {}
  name        = "${each.value.name}-job"
  description = "Daily trigger for ${each.value.name}"
  schedule    = each.value.schedule
  time_zone   = "Africa/Bamako"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://cloudtasks.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/queues/${each.value.name}-writer/tasks"
    headers     = { "Content-Type" = "application/json" }
    body = base64encode(jsonencode({
      task = {
        http_request = {
          http_method = "POST"
          uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${each.value.name}-wf/executions"
          oauth_token = { service_account_email = google_service_account.tradvisor_sa.email }
        }
      }
    }))

    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
    #     oidc_token {
    #       service_account_email = google_service_account.tradvisor_sa.email
    #       audience = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${each.value.name}-wf/executions"
    #     }
  }

  paused = contains(local.paused_schedule_keys, each.key)

  # Existing jobs, including paused jobs, are preserved. Activation or
  # replacement requires its own approved change.
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [description, schedule, time_zone, http_target, paused]
  }
}
