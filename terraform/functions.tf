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
  name       = "scrape-financials"  # Renamed to force recreation with higher memory
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
    available_memory      = "512Mi"  # Increased for PDF processing
    timeout_seconds       = 300  # Increased for PDF processing
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
  name       = "scrape-financials-init"  # Renamed to force recreation with higher memory
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
    available_cpu         = "1"
    available_memory      = "2Gi"  # Increased for PDF processing
    timeout_seconds       = 300  # Increased for PDF processing
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

