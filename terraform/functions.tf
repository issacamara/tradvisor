resource "google_cloudfunctions2_function" "functions" {
  depends_on = [
    google_project_service.apis,
    data.google_project.project,
    google_secret_manager_secret_iam_member.financials_openrouter,
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
        object = google_storage_bucket_object.new-function-src-code[each.key].name
      }
    }
  }
  service_config {
    max_instance_count               = each.key == "scrape_shares" ? var.shares_max_instance_count : 1
    max_instance_request_concurrency = each.key == "scrape_shares" ? var.shares_max_request_concurrency : null
    available_memory                 = "512Mi"
    timeout_seconds                  = 180
    service_account_email            = contains(["scrape_financials", "insert_financials"], each.key) ? google_service_account.financials_runtime.email : google_service_account.tradvisor_sa.email
    environment_variables = merge({
      TRADVISOR_RUNTIME_TARGET             = "ingestion"
      TRADVISOR_ENVIRONMENT                = var.environment
      GOOGLE_CLOUD_PROJECT                 = var.project_id
      TRADVISOR_TARGET_PROJECT_ID          = var.project_id
      TRADVISOR_ENVIRONMENT_PROJECT_ID     = var.v1_environment_project_id
      TRADVISOR_INGESTION_SERVICE_ACCOUNT  = contains(["scrape_financials", "insert_financials"], each.key) ? google_service_account.financials_runtime.email : google_service_account.tradvisor_sa.email
      TRADVISOR_INGESTION_DATA_BUCKET      = google_storage_bucket.data-brvm.name
      TRADVISOR_INGESTION_ARCHIVE_BUCKET   = google_storage_bucket.archive-brvm.name
      TRADVISOR_INGESTION_DATASET          = "stocks"
      TRADVISOR_INGESTION_COMPANIES_TABLE  = "${var.project_id}.stocks.brvm_companies"
      TRADVISOR_INGESTION_SHARES_TABLE     = "${var.project_id}.stocks.shares"
      TRADVISOR_INGESTION_DIVIDENDS_TABLE  = "${var.project_id}.stocks.dividends"
      TRADVISOR_INGESTION_FINANCIALS_TABLE = "${var.project_id}.stocks.financials"
      TRADVISOR_INGESTION_RATINGS_TABLE    = "${var.project_id}.stocks.ratings"
    }, var.v1_ingestion_source_urls)
    dynamic "secret_environment_variables" {
      for_each = contains(["scrape_financials", "insert_financials"], each.key) ? [1] : []
      content {
        key        = "OPENROUTER_API_KEY"
        project_id = var.project_id
        secret     = google_secret_manager_secret.openrouter.secret_id
        version    = "latest"
      }
    }
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = contains(["development", "production"], var.environment) && trimspace(var.v1_environment_project_id) != "" && var.v1_environment_project_id == var.project_id
      error_message = "Ingestion functions require a supported environment and its separately configured project target."
    }
  }
}

resource "google_cloudfunctions2_function" "initialization_functions" {
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
        object = google_storage_bucket_object.initialization-src-code[each.key].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = each.key == "scrape_financials_init" ? "4Gi" : "512Mi"
    available_cpu         = each.key == "scrape_financials_init" ? "1" : null
    timeout_seconds       = each.key == "scrape_financials_init" ? 600 : 180
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
    { source = "financials", functions = ["scrape_financials"], targets = ["stocks.financials"], writer_key = "stocks.financials" },
    { source = "ratings", functions = ["scrape_ratings", "insert_ratings"], targets = ["stocks.ratings"], writer_key = "stocks.ratings" },
  ]
  workflow_by_source   = { for stage in local.workflow_stages : stage.source => stage }
  paused_schedule_keys = toset([])
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
%{for function_name in local.workflow_stages[count.index].functions}
    - ${function_name}:
%{if function_name == "scrape_shares"}
        try:
          call: http.get
          args:
            url: ${google_cloudfunctions2_function.functions[function_name].service_config[0].uri}
            auth:
              type: OIDC
              audience: ${google_cloudfunctions2_function.functions[function_name].service_config[0].uri}
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
          url: ${google_cloudfunctions2_function.functions[function_name].service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions[function_name].service_config[0].uri}
        result: ${function_name}_response
%{endif}
%{endfor}
%{if trimspace(var.publication_control_service_url) != "" && (local.workflow_stages[count.index].source == "shares" || local.workflow_stages[count.index].source == "financials")}
    - publication_completion:
        call: http.post
        args:
          url: ${google_cloud_run_v2_service.publication_control[0].uri}/internal/publication-control/completion
          auth:
            type: OIDC
            audience: ${google_cloud_run_v2_service.publication_control[0].uri}
%{if local.workflow_stages[count.index].source == "shares"}
          body: $${insert_shares_response.body}
%{else}
          body: $${scrape_financials_response.body}
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

# Initialization is an explicit storage-first operation. It is intentionally
# separate from the recurring financials workflow so regular runs do not
# extract the same reports twice.
resource "google_workflows_workflow" "financials_initialization" {
  depends_on      = [google_cloudfunctions2_function.functions, google_cloudfunctions2_function.initialization_functions, google_project_service.apis]
  count           = var.manage_legacy_workflows ? 1 : 0
  name            = "financials-init-wf"
  region          = var.region
  description     = "Download financial PDFs to Cloud Storage, then process them"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_financials_init:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.initialization_functions["scrape_financials_init"].service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.initialization_functions["scrape_financials_init"].service_config[0].uri}
    - insert_financials:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions["insert_financials"].service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions["insert_financials"].service_config[0].uri}
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
