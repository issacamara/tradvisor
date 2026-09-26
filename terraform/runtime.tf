resource "google_service_account" "v1_runtime" {
  project      = var.project_id
  account_id   = "tradvisor-v1-runtime"
  display_name = "Tradvisor V1 development runtime"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_iam_member" "v1_runtime_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.v1_runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "v1_runtime_cursor_secret" {
  count     = var.v1_cursor_secret_id == "" ? 0 : 1
  project   = var.project_id
  secret_id = var.v1_cursor_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.v1_runtime.email}"
}

resource "google_cloud_run_v2_service" "v1_api" {
  count    = var.v1_api_image == "" ? 0 : 1
  name     = "tradvisor-v1-api"
  location = var.region
  project  = var.project_id

  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = true

  scaling {
    min_instance_count = 0
  }

  template {
    service_account                  = google_service_account.v1_runtime.email
    timeout                          = "60s"
    max_instance_request_concurrency = 40

    scaling {
      max_instance_count = 3
    }

    containers {
      image = var.v1_api_image

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENVIRONMENT"
        value = "development"
      }

      dynamic "env" {
        for_each = var.v1_cursor_secret_id == "" ? [] : [var.v1_cursor_secret_id]
        content {
          name = "FIRESTORE_CURSOR_SECRET"
          value_source {
            secret_key_ref {
              secret  = env.value
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
      condition     = var.project_id == "dev-tradvisor"
      error_message = "The V1 API runtime is restricted to the configured development project."
    }
  }
}

resource "google_cloud_run_v2_job" "v1_bounded_job" {
  count    = var.v1_job_image == "" ? 0 : 1
  name     = "tradvisor-v1-bounded-job"
  location = var.region
  project  = var.project_id

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.v1_runtime.email
      max_retries     = 1
      timeout         = "900s"

      containers {
        image = var.v1_job_image
      }
    }
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.project_id == "dev-tradvisor"
      error_message = "The V1 bounded job is restricted to the configured development project."
    }
  }
}
