resource "google_cloudfunctions2_function" "functions" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code,
                data.google_project.project]
  for_each   = toset(var.functions)
  name       = "${each.key}_function"
  location   = var.region
  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
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
    service_account_email = google_service_account.tradvisor_sa.email
  }
  
  # Force recreation when source code changes
  lifecycle {
    replace_triggered_by = [
      google_storage_bucket_object.src-code[each.key].md5hash
    ]
  }
}

# Separate resource for scrape_financials (needs OpenRouter API key)
resource "google_cloudfunctions2_function" "scrape_financials" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code-extra,
                data.google_project.project, google_secret_manager_secret.openrouter_api_key]
  name       = "scrape_financials_function"
  location   = var.region
  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src-code-extra["scrape_financials"].name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 540  # Increased for PDF processing
    service_account_email = google_service_account.tradvisor_sa.email
    environment_variables = {
      "OPENROUTER_API_KEY" = var.openrouter_api_key
    }
  }
  
  # Force recreation when source code changes
  lifecycle {
    replace_triggered_by = [
      google_storage_bucket_object.src-code-extra["scrape_financials"].md5hash
    ]
  }
}


# Additional Cloud Functions for financials and ratings
resource "google_cloudfunctions2_function" "insert_financials" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code-extra,
                data.google_project.project]
  name       = "insert_financials_function"
  location   = var.region
  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src-code-extra["insert_financials"].name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
  
  # Force recreation when source code changes
  lifecycle {
    replace_triggered_by = [
      google_storage_bucket_object.src-code-extra["insert_financials"].md5hash
    ]
  }
}

resource "google_cloudfunctions2_function" "scrape_ratings" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code-extra,
                data.google_project.project]
  name       = "scrape_ratings_function"
  location   = var.region
  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src-code-extra["scrape_ratings"].name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
  
  # Force recreation when source code changes
  lifecycle {
    replace_triggered_by = [
      google_storage_bucket_object.src-code-extra["scrape_ratings"].md5hash
    ]
  }
}

resource "google_cloudfunctions2_function" "insert_ratings" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code-extra,
                data.google_project.project]
  name       = "insert_ratings_function"
  location   = var.region
  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src-code-extra["insert_ratings"].name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
  
  # Force recreation when source code changes
  lifecycle {
    replace_triggered_by = [
      google_storage_bucket_object.src-code-extra["insert_ratings"].md5hash
    ]
  }
}

# Initialization function for financials (collects 5 years)
resource "google_cloudfunctions2_function" "scrape_financials_init" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code-init,
                data.google_project.project, google_secret_manager_secret.openrouter_api_key]
  name       = "scrape_financials_init_function"
  location   = var.region
  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src-code-init["scrape_financials_init"].name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 540  # Increased for PDF processing
    service_account_email = google_service_account.tradvisor_sa.email
    environment_variables = {
      "OPENROUTER_API_KEY" = var.openrouter_api_key
    }
  }
  
  # Force recreation when source code changes
  lifecycle {
    replace_triggered_by = [
      google_storage_bucket_object.src-code-init["scrape_financials_init"].md5hash
    ]
  }
}

# Initialization function for ratings (collects all available)
resource "google_cloudfunctions2_function" "scrape_ratings_init" {
  depends_on = [google_project_service.apis, google_storage_bucket_object.src-code-init,
                data.google_project.project]
  name       = "scrape_ratings_init_function"
  location   = var.region
  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src-code-init["scrape_ratings_init"].name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
  
  # Force recreation when source code changes
  lifecycle {
    replace_triggered_by = [
      google_storage_bucket_object.src-code-init["scrape_ratings_init"].md5hash
    ]
  }
}

# Workflow for financials
# Note: insert_financials step removed - scrape_financials already upserts to BigQuery
resource "google_workflows_workflow" "workflow_financials" {
  depends_on  = [google_cloudfunctions2_function.scrape_financials, google_project_service.apis]
  name        = "financials-wf"
  region      = var.region
  description = "A workflow to scrape and upsert financials to BigQuery"
  project     = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_financials:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_financials.service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_financials.service_config[0].uri}
EOF
}

# Workflow for ratings
# Note: insert_ratings step removed - scrape_ratings already upserts to BigQuery
resource "google_workflows_workflow" "workflow_ratings" {
  depends_on  = [google_cloudfunctions2_function.scrape_ratings, google_project_service.apis]
  name        = "ratings-wf"
  region      = var.region
  description = "A workflow to scrape and upsert ratings to BigQuery"
  project     = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_ratings:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_ratings.service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_ratings.service_config[0].uri}
EOF
}

# Workflow for financials initialization (5 years)
# Note: insert_financials step removed - scrape_financials_init already upserts to BigQuery
resource "google_workflows_workflow" "workflow_financials_init" {
  depends_on  = [google_cloudfunctions2_function.scrape_financials_init, google_project_service.apis]
  name        = "financials-init-wf"
  region      = var.region
  description = "A workflow to initialize financials with 5 years of data"
  project     = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_financials_init:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_financials_init.service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_financials_init.service_config[0].uri}
EOF
}

# Workflow for ratings initialization (all available years)
# Note: insert_ratings step removed - scrape_ratings_init already upserts to BigQuery
resource "google_workflows_workflow" "workflow_ratings_init" {
  depends_on  = [google_cloudfunctions2_function.scrape_ratings_init, google_project_service.apis]
  name        = "ratings-init-wf"
  region      = var.region
  description = "A workflow to initialize ratings with all available data"
  project     = var.project_id
  service_account = google_service_account.tradvisor_sa.email
  source_contents = <<EOF
main:
  steps:
    - scrape_ratings_init:
        call: http.get
        args:
          url: ${google_cloudfunctions2_function.scrape_ratings_init.service_config[0].uri}
          auth:
            type: OIDC
            audience: ${google_cloudfunctions2_function.scrape_ratings_init.service_config[0].uri}
EOF
}


# Note: Generic scheduler jobs removed - no workflows exist for shares/dividends/capitalizations
# Separate job for financials
resource "google_cloud_scheduler_job" "job_financials" {
  depends_on = [google_workflows_workflow.workflow_financials, google_project_service.apis]
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

# Separate job for ratings
resource "google_cloud_scheduler_job" "job_ratings" {
  depends_on = [google_workflows_workflow.workflow_ratings, google_project_service.apis]
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

# Job for financials initialization (one-time - run manually or disable after)
resource "google_cloud_scheduler_job" "job_financials_init" {
  depends_on = [google_workflows_workflow.workflow_financials_init, google_project_service.apis]
  name        = "financials-init-job"
  description = "One-time initialization for financials (5 years). Disable after first run."
  schedule    = "0 6 1 1 *"  # January 1st - run once manually
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

# Job for ratings initialization (one-time - run manually or disable after)
resource "google_cloud_scheduler_job" "job_ratings_init" {
  depends_on = [google_workflows_workflow.workflow_ratings_init, google_project_service.apis]
  name        = "ratings-init-job"
  description = "One-time initialization for ratings. Disable after first run."
  schedule    = "0 6 2 1 *"  # January 2nd - run once manually
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