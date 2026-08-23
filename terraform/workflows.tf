# =====================================================
# Workflows
# =====================================================

resource "google_workflows_workflow" "workflow_shares" {
  depends_on      = [google_cloudfunctions2_function.functions, google_project_service.apis]
  name            = "shares-wf"
  region          = var.region
  description     = "A workflow to scrape and insert shares data"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_shares:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions["scrape_shares"].url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions["scrape_shares"].url}
    - insert_shares:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions["insert_shares"].url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions["insert_shares"].url}
EOF
}

resource "google_workflows_workflow" "workflow_dividends" {
  depends_on      = [google_cloudfunctions2_function.functions, google_project_service.apis]
  name            = "dividends-wf"
  region          = var.region
  description     = "A workflow to scrape and insert dividends data"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_dividends:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions["scrape_dividends"].url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions["scrape_dividends"].url}
    - insert_dividends:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.functions["insert_dividends"].url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.functions["insert_dividends"].url}
EOF
}

resource "google_workflows_workflow" "workflow_financials" {
  depends_on      = [google_cloudfunctions2_function.scrape_financials, google_project_service.apis]
  name            = "financials-wf"
  region          = var.region
  description     = "A workflow to scrape and upsert financials to BigQuery"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_financials:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_financials.url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_financials.url}
EOF
}

resource "google_workflows_workflow" "workflow_ratings" {
  depends_on      = [google_cloudfunctions2_function.scrape_ratings, google_project_service.apis]
  name            = "ratings-wf"
  region          = var.region
  description     = "A workflow to scrape and upsert ratings to BigQuery"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_ratings:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_ratings.url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_ratings.url}
EOF
}

resource "google_workflows_workflow" "workflow_financials_init" {
  depends_on      = [google_cloudfunctions2_function.scrape_financials_init, google_project_service.apis]
  name            = "financials-init-wf"
  region          = var.region
  description     = "A workflow to initialize financials with 5 years of data"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_financials_init:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_financials_init.url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_financials_init.url}
EOF
}

resource "google_workflows_workflow" "workflow_ratings_init" {
  depends_on      = [google_cloudfunctions2_function.scrape_ratings_init, google_project_service.apis]
  name            = "ratings-init-wf"
  region          = var.region
  description     = "A workflow to initialize ratings with all available data"
  project         = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_ratings_init:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_ratings_init.url}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_ratings_init.url}
EOF
}

# =====================================================
# Cloud Scheduler Jobs
# =====================================================

resource "google_cloud_scheduler_job" "job_shares" {
  depends_on  = [google_workflows_workflow.workflow_shares, google_project_service.apis]
  name        = "shares-job"
  description = "Daily trigger for shares"
  schedule    = "0 20 * * 1-5"
  time_zone   = "Africa/Abidjan"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/shares-wf/executions"
    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
  }
}

resource "google_cloud_scheduler_job" "job_dividends" {
  depends_on  = [google_workflows_workflow.workflow_dividends, google_project_service.apis]
  name        = "dividends-job"
  description = "Monthly trigger for dividends"
  schedule    = "0 20 1 * *"
  time_zone   = "Africa/Abidjan"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/dividends-wf/executions"
    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
  }
}

resource "google_cloud_scheduler_job" "job_financials" {
  depends_on  = [google_workflows_workflow.workflow_financials, google_project_service.apis]
  name        = "financials-job"
  description = "Monthly trigger for financials"
  schedule    = "0 6 1 * *"
  time_zone   = "Africa/Abidjan"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/financials-wf/executions"
    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
  }
}

resource "google_cloud_scheduler_job" "job_ratings" {
  depends_on  = [google_workflows_workflow.workflow_ratings, google_project_service.apis]
  name        = "ratings-job"
  description = "Monthly trigger for ratings"
  schedule    = "0 6 5 * *"
  time_zone   = "Africa/Abidjan"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/ratings-wf/executions"
    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
  }
}

resource "google_cloud_scheduler_job" "job_financials_init" {
  depends_on  = [google_workflows_workflow.workflow_financials_init, google_project_service.apis]
  name        = "financials-init-job"
  description = "One-time initialization for financials (5 years). Disable after first run."
  schedule    = "0 6 1 1 *"
  time_zone   = "Africa/Abidjan"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/financials-init-wf/executions"
    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
  }
}

resource "google_cloud_scheduler_job" "job_ratings_init" {
  depends_on  = [google_workflows_workflow.workflow_ratings_init, google_project_service.apis]
  name        = "ratings-init-job"
  description = "One-time initialization for ratings. Disable after first run."
  schedule    = "0 6 2 1 *"
  time_zone   = "Africa/Abidjan"
  project     = var.project_id
  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/ratings-init-wf/executions"
    oauth_token {
      service_account_email = google_service_account.tradvisor_sa.email
    }
  }
}