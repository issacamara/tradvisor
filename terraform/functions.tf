resource "google_cloudfunctions2_function" "retained_functions" {
  depends_on = [
    google_project_service.apis,
    data.google_project.project,
  ]
  for_each = toset(var.functions)
  name     = "${each.key}_function"
  location = var.region
  build_config {
    #     runtime     = "python39"
    runtime     = var.function_runtimes[each.key]
    entry_point = "entry_point" # Set the entry point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.retained-new-function-src-code[each.key].name
      }
    }
  }
  service_config {
    max_instance_count               = each.key == "scrape_shares" ? var.shares_max_instance_count : 1
    max_instance_request_concurrency = each.key == "scrape_shares" ? var.shares_max_request_concurrency : null
    available_memory                 = "512Mi"
    timeout_seconds                  = 180
    service_account_email            = google_service_account.tradvisor_sa.email
    environment_variables = merge({
      TRADVISOR_RUNTIME_TARGET             = "ingestion"
      TRADVISOR_ENVIRONMENT                = var.environment
      GOOGLE_CLOUD_PROJECT                 = var.project_id
      TRADVISOR_TARGET_PROJECT_ID          = var.project_id
      TRADVISOR_ENVIRONMENT_PROJECT_ID     = var.v1_environment_project_id
      TRADVISOR_INGESTION_SERVICE_ACCOUNT  = google_service_account.tradvisor_sa.email
      TRADVISOR_INGESTION_DATA_BUCKET      = google_storage_bucket.data-brvm.name
      TRADVISOR_INGESTION_ARCHIVE_BUCKET   = google_storage_bucket.archive-brvm.name
      TRADVISOR_INGESTION_DATASET          = "stocks"
      TRADVISOR_INGESTION_COMPANIES_TABLE  = "${var.project_id}.stocks.brvm_companies"
      TRADVISOR_INGESTION_SHARES_TABLE     = "${var.project_id}.stocks.shares"
      TRADVISOR_INGESTION_DIVIDENDS_TABLE  = "${var.project_id}.stocks.dividends"
      TRADVISOR_INGESTION_FINANCIALS_TABLE = "${var.project_id}.stocks.financials"
      TRADVISOR_INGESTION_RATINGS_TABLE    = "${var.project_id}.stocks.ratings"
    }, var.v1_ingestion_source_urls)
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = contains(["development", "production"], var.environment) && trimspace(var.v1_environment_project_id) != "" && var.v1_environment_project_id == var.project_id
      error_message = "Ingestion functions require a supported environment and its separately configured project target."
    }
  }
}

resource "google_cloudfunctions2_function" "retained_initialization_functions" {
  depends_on = [google_project_service.apis, data.google_project.project]
  for_each   = var.initialization_functions
  name       = "${each.key}_function"
  location   = var.region

  build_config {
    runtime     = var.function_runtimes[each.key]
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.retained-initialization-src-code[each.key].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
    environment_variables = merge({
      TRADVISOR_RUNTIME_TARGET             = "ingestion"
      TRADVISOR_ENVIRONMENT                = var.environment
      GOOGLE_CLOUD_PROJECT                 = var.project_id
      TRADVISOR_TARGET_PROJECT_ID          = var.project_id
      TRADVISOR_ENVIRONMENT_PROJECT_ID     = var.v1_environment_project_id
      TRADVISOR_INGESTION_SERVICE_ACCOUNT  = google_service_account.tradvisor_sa.email
      TRADVISOR_INGESTION_DATA_BUCKET      = google_storage_bucket.data-brvm.name
      TRADVISOR_INGESTION_ARCHIVE_BUCKET   = google_storage_bucket.archive-brvm.name
      TRADVISOR_INGESTION_DATASET          = "stocks"
      TRADVISOR_INGESTION_COMPANIES_TABLE  = "${var.project_id}.stocks.brvm_companies"
      TRADVISOR_INGESTION_SHARES_TABLE     = "${var.project_id}.stocks.shares"
      TRADVISOR_INGESTION_DIVIDENDS_TABLE  = "${var.project_id}.stocks.dividends"
      TRADVISOR_INGESTION_FINANCIALS_TABLE = "${var.project_id}.stocks.financials"
      TRADVISOR_INGESTION_RATINGS_TABLE    = "${var.project_id}.stocks.ratings"
    }, var.v1_ingestion_source_urls)
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = contains(["development", "production"], var.environment) && trimspace(var.v1_environment_project_id) != "" && var.v1_environment_project_id == var.project_id
      error_message = "Ingestion functions require a supported environment and its separately configured project target."
    }
  }
}


locals {
  workflow_stages = [
    { source = "shares", functions = ["scrape_shares", "insert_shares"], targets = ["stocks.shares"], writer_key = "stocks.shares" },
    { source = "dividends", functions = ["scrape_dividends", "insert_dividends"], targets = ["stocks.dividends"], writer_key = "stocks.dividends" },
    { source = "ratings", functions = ["scrape_ratings", "insert_ratings"], targets = ["stocks.ratings"], writer_key = "stocks.ratings" },
  ]
  workflow_by_source   = { for stage in local.workflow_stages : stage.source => stage }
  paused_schedule_keys = toset([])
}

resource "google_workflows_workflow" "retained_workflows" {
  depends_on      = [google_cloudfunctions2_function.retained_functions, google_project_service.apis]
  for_each        = var.manage_legacy_workflows ? { for stage in local.workflow_stages : stage.source => stage } : {}
  name            = "${each.value.source}-wf"
  region          = var.region
  description     = "Ordered ${each.value.source} ingestion and persistence stages"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
%{for function_name in each.value.functions}
    - ${function_name}:
%{if function_name == "scrape_shares"}
        try:
          call: http.get
          args:
            url: ${google_cloudfunctions2_function.retained_functions[function_name].service_config[0].uri}
            auth:
              type: OIDC
              audience: ${google_cloudfunctions2_function.retained_functions[function_name].service_config[0].uri}
          result: ${function_name}_response
        retry:
          predicate: $${retry_transient_http}
          max_retries: ${var.shares_workflow_max_retries}
          backoff:
            initial_delay: ${var.shares_workflow_retry_initial_delay_seconds}
            max_delay: ${var.shares_workflow_retry_max_delay_seconds}
            multiplier: 2
%{else}
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.retained_functions[function_name].service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.retained_functions[function_name].service_config[0].uri}
        result: ${function_name}_response
%{endif}
%{endfor}
%{if trimspace(var.publication_control_service_url) != "" && each.value.source == "shares"}
    - publication_completion:
        call: http.post
        args:
          url: ${google_cloud_run_v2_service.publication_control[0].uri}/internal/publication-control/completion
          auth:
            type: OIDC
            audience: ${google_cloud_run_v2_service.publication_control[0].uri}
%{if each.value.source == "shares"}
          body: $${insert_shares_response.body}
%{endif}
%{endif}
retry_transient_http:
  params: [e]
  steps:
    - classify:
        switch:
          - condition: $${e.code == 429 or e.code == 500 or e.code == 502 or e.code == 503 or e.code == 504}
            return: true
    - do_not_retry:
        return: false
EOF

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_cloud_scheduler_job" "retained_jobs" {
  depends_on  = [google_workflows_workflow.retained_workflows, google_project_service.apis]
  for_each    = var.manage_legacy_schedules ? var.jobs : {}
  name        = "${each.value.name}-job"
  description = contains(["financials", "ratings"], each.value.name) ? "Monthly trigger for ${each.value.name}" : "Daily trigger for ${each.value.name}"
  schedule    = each.value.schedule
  time_zone   = "Africa/Bamako"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${each.value.name}-wf/executions"
    headers     = { "Content-Type" = "application/json" }
    body = base64encode(jsonencode({
      # Workflows Executions API expects the execution argument as a JSON
      # string. An empty object keeps the existing workflow input contract.
      argument = jsonencode({})
    }))

    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
  }

  paused = contains(local.paused_schedule_keys, each.key)

  lifecycle {
    prevent_destroy = true
  }
}

# Move each retained nonfinancial instance to the retained resource address.
moved {
  from = google_storage_bucket_object.src-code["scrape_shares"]
  to   = google_storage_bucket_object.retained-src-code["scrape_shares"]
}

moved {
  from = google_storage_bucket_object.src-code["insert_shares"]
  to   = google_storage_bucket_object.retained-src-code["insert_shares"]
}

moved {
  from = google_storage_bucket_object.src-code["scrape_dividends"]
  to   = google_storage_bucket_object.retained-src-code["scrape_dividends"]
}

moved {
  from = google_storage_bucket_object.src-code["insert_dividends"]
  to   = google_storage_bucket_object.retained-src-code["insert_dividends"]
}

moved {
  from = google_storage_bucket_object.src-code["scrape_ratings"]
  to   = google_storage_bucket_object.retained-src-code["scrape_ratings"]
}

moved {
  from = google_storage_bucket_object.src-code["insert_ratings"]
  to   = google_storage_bucket_object.retained-src-code["insert_ratings"]
}

moved {
  from = google_storage_bucket_object.new-function-src-code["scrape_shares"]
  to   = google_storage_bucket_object.retained-new-function-src-code["scrape_shares"]
}

moved {
  from = google_storage_bucket_object.new-function-src-code["insert_shares"]
  to   = google_storage_bucket_object.retained-new-function-src-code["insert_shares"]
}

moved {
  from = google_storage_bucket_object.new-function-src-code["scrape_dividends"]
  to   = google_storage_bucket_object.retained-new-function-src-code["scrape_dividends"]
}

moved {
  from = google_storage_bucket_object.new-function-src-code["insert_dividends"]
  to   = google_storage_bucket_object.retained-new-function-src-code["insert_dividends"]
}

moved {
  from = google_storage_bucket_object.new-function-src-code["scrape_ratings"]
  to   = google_storage_bucket_object.retained-new-function-src-code["scrape_ratings"]
}

moved {
  from = google_storage_bucket_object.new-function-src-code["insert_ratings"]
  to   = google_storage_bucket_object.retained-new-function-src-code["insert_ratings"]
}

moved {
  from = google_storage_bucket_object.initialization-src-code["scrape_ratings_init"]
  to   = google_storage_bucket_object.retained-initialization-src-code["scrape_ratings_init"]
}

moved {
  from = google_cloudfunctions2_function.functions["scrape_shares"]
  to   = google_cloudfunctions2_function.retained_functions["scrape_shares"]
}

moved {
  from = google_cloudfunctions2_function.functions["insert_shares"]
  to   = google_cloudfunctions2_function.retained_functions["insert_shares"]
}

moved {
  from = google_cloudfunctions2_function.functions["scrape_dividends"]
  to   = google_cloudfunctions2_function.retained_functions["scrape_dividends"]
}

moved {
  from = google_cloudfunctions2_function.functions["insert_dividends"]
  to   = google_cloudfunctions2_function.retained_functions["insert_dividends"]
}

moved {
  from = google_cloudfunctions2_function.functions["scrape_ratings"]
  to   = google_cloudfunctions2_function.retained_functions["scrape_ratings"]
}

moved {
  from = google_cloudfunctions2_function.functions["insert_ratings"]
  to   = google_cloudfunctions2_function.retained_functions["insert_ratings"]
}

moved {
  from = google_cloudfunctions2_function.initialization_functions["scrape_ratings_init"]
  to   = google_cloudfunctions2_function.retained_initialization_functions["scrape_ratings_init"]
}

moved {
  from = google_workflows_workflow.workflows[0]
  to   = google_workflows_workflow.retained_workflows["shares"]
}

moved {
  from = google_workflows_workflow.workflows[1]
  to   = google_workflows_workflow.retained_workflows["dividends"]
}

moved {
  from = google_workflows_workflow.workflows[3]
  to   = google_workflows_workflow.retained_workflows["ratings"]
}

moved {
  from = google_cloud_scheduler_job.jobs["job1"]
  to   = google_cloud_scheduler_job.retained_jobs["job1"]
}

moved {
  from = google_cloud_scheduler_job.jobs["job3"]
  to   = google_cloud_scheduler_job.retained_jobs["job3"]
}

moved {
  from = google_cloud_scheduler_job.jobs["job6"]
  to   = google_cloud_scheduler_job.retained_jobs["job6"]
}

removed {
  from = google_cloudfunctions2_function.functions
  lifecycle { destroy = true }
}

removed {
  from = google_cloudfunctions2_function.initialization_functions
  lifecycle { destroy = true }
}

removed {
  from = google_workflows_workflow.workflows
  lifecycle { destroy = true }
}

removed {
  from = google_workflows_workflow.financials_initialization
  lifecycle { destroy = true }
}

removed {
  from = google_cloud_scheduler_job.jobs
  lifecycle { destroy = true }
}

removed {
  from = google_storage_bucket_object.src-code
  lifecycle { destroy = false }
}

removed {
  from = google_storage_bucket_object.new-function-src-code
  lifecycle { destroy = false }
}

removed {
  from = google_storage_bucket_object.initialization-src-code
  lifecycle { destroy = false }
}
