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


resource "google_workflows_workflow" "workflows" {
  depends_on      = [google_cloudfunctions2_function.functions, google_project_service.apis]
  count           = var.manage_legacy_workflows ? length(var.functions) / 2 : 0
  name            = "${split("_", var.functions[count.index])[1]}-wf"
  region          = var.region
  description     = "A workflow to run ${var.functions[count.index]} and ${var.functions[count.index + 4]} sequentially"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - ${var.functions[count.index]}:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions[var.functions[count.index]].service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions[var.functions[count.index]].service_config[0].uri}
    - ${var.functions[count.index + 4]}:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions[var.functions[count.index + 4]].service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions[var.functions[count.index + 4]].service_config[0].uri}
EOF

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}


resource "google_cloud_scheduler_job" "jobs" {
  depends_on = [google_workflows_workflow.workflows, google_project_service.apis]
  #   for_each = { for wf in google_workflows_workflow.workflows : wf.name => wf }
  for_each    = var.manage_legacy_schedules ? var.jobs : {}
  name        = "${each.value.name}-job"
  description = "Daily trigger for ${each.value.name}"
  schedule    = each.value.schedule
  time_zone   = "Africa/Bamako"
  project     = var.project_id
  http_target {
    http_method = "POST"
    #     uri = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${google_workflows_workflow.share-workflow.name}/executions"
    uri = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${each.value.name}-wf/executions"

    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
    #     oidc_token {
    #       service_account_email = google_service_account.tradvisor_sa.email
    #       audience = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${each.value.name}-wf/executions"
    #     }
  }

  # Existing jobs, including paused jobs, are preserved. Activation or
  # replacement requires its own approved change.
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [description, schedule, time_zone, http_target]
  }
}
