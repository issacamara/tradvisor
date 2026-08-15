variable "service_name" {
  description = "Name of the Cloud Run service"
  type        = string
  default     = "prod-tradvisor"
}

# Deploy the Cloud Run service
resource "google_cloud_run_v2_service" "tradvisor_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret.tradvisor_gmail_acc,
    google_secret_manager_secret_version.gmail_acc_secret_version,
    google_artifact_registry_repository.tradvisor
  ]
  client              = "terraform"
  deletion_protection = false

  template {
    timeout = "300s"

    service_account = google_service_account.tradvisor_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      #image = var.docker_image
      ports { container_port = 8501 }
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.tradvisor.repository_id}/${var.service_name}:latest"
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
        name = "TRADVISOR_GMAIL_ACC_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.tradvisor_gmail_acc.id
            version = "latest"
          }
        }
      }

      resources {
        cpu_idle = true
        limits = {
          memory = "1Gi"
          cpu    = "1"
        }
      }

      startup_probe {
        http_get {
          path = "/_stcore/health"
          port = 8501
        }
        initial_delay_seconds = 15
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 3
      }
    }
  }
}

# Secret Manager resource
resource "google_secret_manager_secret" "bigquery_creds" {
  secret_id = "brvm-dashboard-bigquery-creds"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
  depends_on = [google_project_service.apis]
}