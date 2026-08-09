
variable "service_name" {
  description = "Name of the Cloud Run service"
  type        = string
  default     = "tradvisor"
}

# Deploy the Cloud Run service
resource "google_cloud_run_v2_service" "tradvisor_service" {
  name     = var.service_name
  location = var.region
  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret.tradvisor_gmail_acc,
    google_secret_manager_secret_version.gmail_acc_secret_version
  ]
  client   = "terraform"
  deletion_protection=false
  template {
    timeout = "300s"

    # Service account to use
    service_account = google_service_account.tradvisor_sa.email
    scaling {
      # Scale to zero when no requests
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = var.docker_image
      ports { container_port = 8501 }
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "AUTH_DISABLED"
        value = var.auth_disabled
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "BASE_URL"
        value = "https://${var.service_name}-${var.project_id}.${var.region}.run.app"
      }

      # Note: GOOGLE_APPLICATION_CREDENTIALS is not needed in Cloud Run
      # The service account attached to the container is used automatically

      env {
        name = "TRADVISOR_GMAIL_ACC_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.tradvisor_gmail_acc.id
            version = "latest"
          }
        }
      }

      # Resource limits
      resources {
        cpu_idle = true
        limits = {
          memory = "1Gi"
          cpu    = "1"
        }
      }
      startup_probe {
        http_get {
          path = "/"
          port = 8501
        }
        initial_delay_seconds = 10
        timeout_seconds = 3
        period_seconds = 5
        failure_threshold = 3
      }
    }
  }

}
data "google_iam_policy" "noauth" {
  binding {
    role = "roles/run.invoker"
    members = [
      "allUsers",
    ]
  }
}
# Create a secret for BigQuery credentials
resource "google_secret_manager_secret" "bigquery_creds" {
  secret_id = "brvm-dashboard-bigquery-creds"

  replication {
    user_managed {
      replicas {
        location = "europe-central2"
      }
    }
  }
  depends_on = [google_project_service.apis]
}
#
# # Enable Secret Manager API
# resource "google_project_service" "secretmanager_api" {
#   service            = "secretmanager.googleapis.com"
#   disable_on_destroy = false
# }
#
# Make the Cloud Run service publicly accessible

