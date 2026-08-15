# Standard Cloud Functions
resource "google_cloudfunctions2_function" "functions" {
  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.src_code,
    data.google_project.project
  ]
  for_each = toset(var.functions)

  name     = "${each.key}_function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src_code[each.key].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
}

# Scrape Financials Function (PDF Processing)
resource "google_cloudfunctions2_function" "scrape_financials" {
  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.src_code_extra,
    data.google_project.project,
    google_secret_manager_secret.openrouter_api_key
  ]
  name     = "scrape-financials"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src_code_extra["scrape_financials"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 300
    service_account_email = google_service_account.tradvisor_sa.email
    environment_variables = {
      "OPENROUTER_API_KEY" = var.openrouter_api_key
    }
  }
}

# Insert Financials Function
resource "google_cloudfunctions2_function" "insert_financials" {
  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.src_code_extra,
    data.google_project.project
  ]
  name     = "insert_financials_function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src_code_extra["insert_financials"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
}

# Scrape Ratings Function
resource "google_cloudfunctions2_function" "scrape_ratings" {
  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.src_code_extra,
    data.google_project.project
  ]
  name     = "scrape_ratings_function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src_code_extra["scrape_ratings"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
}

# Insert Ratings Function
resource "google_cloudfunctions2_function" "insert_ratings" {
  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.src_code_extra,
    data.google_project.project
  ]
  name     = "insert_ratings_function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src_code_extra["insert_ratings"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
}

# Scrape Financials Init Function
resource "google_cloudfunctions2_function" "scrape_financials_init" {
  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.src_code_init,
    data.google_project.project,
    google_secret_manager_secret.openrouter_api_key
  ]
  name     = "scrape-financials-init"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src_code_init["scrape_financials_init"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_cpu         = "1"
    available_memory      = "4Gi"
    timeout_seconds       = 300
    service_account_email = google_service_account.tradvisor_sa.email
    environment_variables = {
      "OPENROUTER_API_KEY" = var.openrouter_api_key
    }
  }
}

# Scrape Ratings Init Function
resource "google_cloudfunctions2_function" "scrape_ratings_init" {
  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.src_code_init,
    data.google_project.project
  ]
  name     = "scrape_ratings_init_function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "entry_point"
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.src_code_init["scrape_ratings_init"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512Mi"
    timeout_seconds       = 180
    service_account_email = google_service_account.tradvisor_sa.email
  }
}