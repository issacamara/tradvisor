locals {
  v1_runtime_enabled          = var.configure_v1_runtime
  v1_api_enabled              = var.configure_v1_api || var.configure_v1_runtime
  v1_runtime_identity_enabled = local.v1_api_enabled || local.v1_runtime_enabled
}

resource "google_service_account" "v1_runtime" {
  count        = local.v1_runtime_identity_enabled ? 1 : 0
  account_id   = var.v1_runtime_service_account_id
  display_name = "Tradvisor V1 runtime"
  project      = var.project_id

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [data.google_project.project]
}

resource "google_secret_manager_secret" "v1_cursor" {
  count     = local.v1_runtime_identity_enabled ? 1 : 0
  project   = var.project_id
  secret_id = var.v1_cursor_secret_id

  replication {
    auto {}
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_iam_member" "v1_runtime_firestore" {
  count   = local.v1_runtime_identity_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.v1_runtime[0].email}"
}

resource "google_project_iam_member" "terraform_deployer_cloudtasks_admin" {
  count   = var.manage_legacy_schedules && trimspace(var.terraform_deployer_service_account) != "" ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtasks.admin"
  member  = "serviceAccount:${var.terraform_deployer_service_account}"
}

resource "google_project_iam_member" "v1_runtime_bigquery_job_user" {
  count   = local.v1_runtime_identity_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.v1_runtime[0].email}"
}

resource "google_project_iam_member" "v1_runtime_bigquery_viewer" {
  count   = local.v1_runtime_identity_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.v1_runtime[0].email}"
}

resource "google_project_iam_member" "v1_runtime_bigquery_editor" {
  count   = local.v1_runtime_identity_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.v1_runtime[0].email}"
}

resource "google_project_iam_member" "v1_runtime_firebase_auth_viewer" {
  count   = local.v1_runtime_identity_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/firebaseauth.viewer"
  member  = "serviceAccount:${google_service_account.v1_runtime[0].email}"
}

resource "google_secret_manager_secret_iam_member" "v1_runtime_cursor" {
  count     = local.v1_runtime_identity_enabled ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.v1_cursor[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.v1_runtime[0].email}"
}

resource "google_cloud_run_v2_service" "v1_api" {
  count               = local.v1_api_enabled ? 1 : 0
  name                = var.v1_api_service_name
  location            = var.region
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account = google_service_account.v1_runtime[0].email
    timeout         = "${var.v1_api_timeout_seconds}s"

    scaling {
      min_instance_count = 0
      max_instance_count = var.v1_api_max_instance_count
    }

    max_instance_request_concurrency = var.v1_api_max_request_concurrency

    containers {
      image = var.v1_api_image
      ports {
        container_port = 8080
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "TRADVISOR_CORS_ORIGINS"
        value = var.v1_cors_origins
      }

      env {
        name = "FIRESTORE_CURSOR_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.v1_cursor[0].secret_id
            version = "1"
          }
        }
      }

      resources {
        cpu_idle = true
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = contains(["development", "production"], var.environment)
      error_message = "V1 runtime configuration requires a supported deployment environment."
    }

    precondition {
      condition     = length(trimspace(var.v1_api_image)) > 0
      error_message = "Set an approved API image before enabling the V1 runtime."
    }
  }

  depends_on = [
    google_project_iam_member.v1_runtime_firestore,
    google_secret_manager_secret_iam_member.v1_runtime_cursor,
  ]
}

# Firebase Hosting reaches the API over HTTPS; FastAPI remains the
# authentication and invitation-admission boundary for the development app.
resource "google_cloud_run_v2_service_iam_member" "v1_api_public_invoker" {
  count    = local.v1_api_enabled ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.v1_api[0].location
  name     = google_cloud_run_v2_service.v1_api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "workflow_dispatcher" {
  count               = var.manage_legacy_schedules ? 1 : 0
  name                = "${var.v1_api_service_name}-workflow-dispatcher"
  location            = var.region
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = true

  template {
    service_account = google_service_account.tradvisor_sa.email
    timeout         = "900s"

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    max_instance_request_concurrency = 1

    containers {
      image = var.v1_api_image
      ports {
        container_port = 8080
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "WORKFLOW_REGION"
        value = var.region
      }

      resources {
        cpu_idle = true
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = contains(["development", "production"], var.environment)
      error_message = "Workflow dispatcher configuration requires a supported deployment environment."
    }

    precondition {
      condition     = length(trimspace(var.v1_api_image)) > 0
      error_message = "Set an approved API image before enabling the workflow dispatcher."
    }
  }
}

resource "google_cloud_run_v2_job" "v1_batch" {
  count               = local.v1_runtime_enabled ? 1 : 0
  name                = var.v1_batch_job_name
  location            = var.region
  project             = var.project_id
  deletion_protection = true

  template {
    task_count = 1

    template {
      max_retries     = var.v1_batch_max_retries
      timeout         = "${var.v1_batch_timeout_seconds}s"
      service_account = google_service_account.v1_runtime[0].email

      containers {
        image   = var.v1_batch_image
        command = length(var.v1_batch_command) > 0 ? var.v1_batch_command : ["python", "-m", "backend.commands.daily_publication"]

        env {
          name  = "MARKET_DATA_TABLE"
          value = "${var.project_id}.stocks.shares"
        }

        env {
          name  = "FINANCIALS_TABLE"
          value = var.v1_financials_table
        }

        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }

        env {
          name = "FIRESTORE_CURSOR_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.v1_cursor[0].secret_id
              version = "1"
            }
          }
        }
      }
    }
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = contains(["development", "production"], var.environment)
      error_message = "V1 batch jobs require a supported deployment environment."
    }

    precondition {
      condition     = length(trimspace(var.v1_batch_image)) > 0 && length(var.v1_batch_command) > 0
      error_message = "Set an approved batch image and command before enabling V1 jobs."
    }

  }

  depends_on = [google_project_iam_member.v1_runtime_firestore]
}
