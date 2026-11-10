resource "google_cloud_run_v2_job" "fi1_financials" {
  count               = var.manage_fi1_financial_job ? 1 : 0
  project             = var.project_id
  name                = var.fi1_financial_job_name
  location            = var.region
  deletion_protection = true

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.fi1_financial_runtime[0].email
      timeout         = "${var.fi1_financial_job_timeout_seconds}s"
      max_retries     = 0

      containers {
        image = var.fi1_financial_job_image

        resources {
          limits = {
            cpu    = "1"
            memory = "2Gi"
          }
        }

        env {
          name  = "TRADVISOR_RUNTIME_TARGET"
          value = "financial_ingestion_job"
        }
        env {
          name  = "TRADVISOR_ENVIRONMENT"
          value = var.environment
        }
        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
        env {
          name  = "TRADVISOR_TARGET_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "TRADVISOR_ENVIRONMENT_PROJECT_ID"
          value = var.v1_environment_project_id
        }
        env {
          name  = "TRADVISOR_INGESTION_DATASET"
          value = "stocks"
        }
        env {
          name  = "TRADVISOR_INGESTION_COMPANIES_TABLE"
          value = "${var.project_id}.stocks.brvm_companies"
        }
        env {
          name  = "TRADVISOR_INGESTION_FINANCIALS_TABLE"
          value = "${var.project_id}.stocks.financials"
        }
        env {
          name  = "TRADVISOR_INGESTION_FINANCIALS_STAGING_TABLE"
          value = "${var.project_id}.stocks.financials_staging"
        }
        env {
          name  = "TRADVISOR_FINANCIALS_MODEL_PRIMARY"
          value = "gemma-4-31b-it"
        }
        env {
          name  = "TRADVISOR_FINANCIALS_MODEL_FALLBACKS"
          value = "nvidia/nemotron-3.5-lightning:free,openai/gpt-4o-mini"
        }
        env {
          name  = "TRADVISOR_FINANCIALS_MAX_CONCURRENT_REQUESTS"
          value = tostring(var.fi1_financial_job_max_concurrent_requests)
        }
        env {
          name  = "TRADVISOR_FINANCIALS_MAX_REPORTS_PER_SYMBOL"
          value = tostring(var.fi1_financial_job_max_reports_per_symbol)
        }
        env {
          name  = "TRADVISOR_FINANCIALS_SELECTION_MODE"
          value = "previous_year"
        }
        env {
          name  = "TRADVISOR_FINANCIALS_MAX_ATTEMPTS_PER_MODEL"
          value = "1"
        }

        env {
          name = "OPENROUTER_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.openrouter.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(trimspace(var.fi1_financial_job_image)) > 0
      error_message = "FI-1 requires an immutable image digest supplied by the release integration."
    }
    precondition {
      condition     = contains(["development", "production"], var.environment) && trimspace(var.v1_environment_project_id) != "" && var.v1_environment_project_id == var.project_id
      error_message = "FI-1 must target the explicitly configured project for its environment."
    }
    precondition {
      condition     = !var.activate_fi1_financial_schedule || var.manage_legacy_schedules
      error_message = "FI-1 schedule activation requires Terraform ownership of the remaining legacy schedules."
    }
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.fi1_financial_bigquery_job_user,
    google_bigquery_dataset_iam_member.fi1_stocks_editor,
    google_project_iam_member.fi1_financial_firestore,
    google_bigquery_table_iam_member.fi1_companies_reader,
    google_bigquery_table_iam_member.fi1_financials_editor,
    google_bigquery_table_iam_member.fi1_financials_staging_editor,
    google_secret_manager_secret_iam_member.fi1_financial_openrouter,
  ]
}

resource "google_cloud_scheduler_job" "fi1_financials" {
  count       = var.manage_fi1_financial_job ? 1 : 0
  project     = var.project_id
  region      = var.region
  name        = "${var.fi1_financial_job_name}-monthly"
  description = "Monthly trigger for the private FI-1 financial ingestion Job"
  schedule    = var.fi1_financial_job_schedule
  time_zone   = "Africa/Bamako"
  paused      = !var.activate_fi1_financial_schedule

  attempt_deadline = "300s"

  retry_config {
    retry_count = 0
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.fi1_financials[0].name}:run"

    oauth_token {
      service_account_email = google_service_account.fi1_financial_scheduler[0].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_run_v2_job_iam_member.fi1_financial_scheduler_invoker,
  ]
}
