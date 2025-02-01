resource "google_cloudfunctions2_function" "functions" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code,
  data.google_project.project]
  for_each = toset(var.functions)
  name     = "${each.key}_function"
  location = var.region
  #   description = "This function scrapes shares from BRVM"
  build_config {
    runtime     = "python39"
    entry_point = "entry_point" # Set the entry point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src-code[each.key].name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  }
}


resource "google_workflows_workflow" "workflows" {
  depends_on  = [google_cloudfunctions2_function.functions, google_project_service.apis]
  count       = length(var.functions) / 2
  name        = "${split("_", var.functions[count.index])[1]}-wf"
  region      = var.region
  description = "A workflow to run two cloud functions sequentially"
  project     = var.project_id
  #   source_contents = file("../scripts/workflow.yml")

  service_account = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  #   service_account = "projects/${data.google_project.project.number}/serviceAccounts/${data.google_project.project.number}-compute@developer.gserviceaccount.com"

  #   source_contents = templatefile("/Users/issacamara/Developer/tradvisor/scripts/workflow.yaml.tpl", {
  #     function_urls = [for f in google_cloudfunctions2_function.functions: f.url], functions = var.functions
  #   })
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
}


resource "google_cloud_scheduler_job" "jobs" {
  depends_on = [google_workflows_workflow.workflows, google_project_service.apis]
  #   for_each = { for wf in google_workflows_workflow.workflows : wf.name => wf }
  for_each    = var.jobs
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
      service_account_email = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
    }
  }
}