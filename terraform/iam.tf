# Create a service account for the function
resource "google_service_account" "tradvisor_sa" {
  account_id = "tradvisor-sa-${data.google_project.project.number}"
  depends_on = [data.google_project.project]
  display_name = "Service Account for tradvisor application"
}

# Create a key for the service account
resource "google_service_account_key" "tradvisor_sa_key" {
  service_account_id = google_service_account.tradvisor_sa.name
  keepers = {
    # Helps to rotate the key by triggering recreation when value changes
    created_at = timestamp()
  }
  private_key_type = "TYPE_GOOGLE_CREDENTIALS_FILE"
}

resource "google_secret_manager_secret" "tradvisor_sa_key_secret" {
  secret_id = "tradvisor_sa_key"
  replication {
    auto {}
  }
  depends_on = [google_service_account.tradvisor_sa]
}

resource "google_secret_manager_secret" "tradvisor_gmail_acc" {
  secret_id = "tradvisor_gmail_acc"
  replication {
    auto {}
  }
  depends_on = [google_service_account.tradvisor_sa]
}

resource "google_secret_manager_secret_version" "sa_key_secret_version" {
  depends_on = [google_service_account_key.tradvisor_sa_key, google_secret_manager_secret.tradvisor_sa_key_secret]
  secret      = google_secret_manager_secret.tradvisor_sa_key_secret.name
  secret_data = base64decode(google_service_account_key.tradvisor_sa_key.private_key)
}

# resource "null_resource" "sa_key_file" {
# #   content  = google_service_account_key.tradvisor_sa_key.private_key
# #   filename = "../webapp/.streamlit/tradvisor-sa-key.json"
# #   file_permission = "0600"
#   triggers = {
#     private_key = google_service_account_key.tradvisor_sa_key.private_key
#   }
#   provisioner "local-exec" {
#     command = <<EOT
#       echo "${google_service_account_key.tradvisor_sa_key.private_key}" | base64 --decode > ../webapp/.streamlit/tradvisor-sa-key.json
#     EOT
#     interpreter = ["/bin/bash", "-c"]
#   }
# }

# Create a service account for the Cloud Run service
resource "google_service_account" "brvm_dashboard_sa" {
  account_id   = "brvm-dashboard-sa"
  display_name = "BRVM Dashboard Service Account"
  depends_on   = [google_project_service.apis[7] ]
}


resource "google_project_iam_binding" "build_sa_roles" {
  depends_on = [google_service_account.tradvisor_sa]
  project    = var.project_id
  role       = "roles/cloudbuild.builds.builder"
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "function_invoker" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/cloudfunctions.invoker"
  members = [
      "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "all_buckets_viewer" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/storage.objectViewer"
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
#   "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "log_writer" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/logging.logWriter"
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

# Grant the necessary roles to the service account
resource "google_project_iam_binding" "cloud_run_sa_invoker" {
  project    = var.project_id
  role       = "roles/run.invoker"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "workflow_executor" {
  project    = var.project_id
  role       = "roles/workflows.invoker"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}


resource "google_project_iam_binding" "sa_user" {
  project    = var.project_id
  role       = "roles/iam.serviceAccountUser"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "sms_accessor" {
  project    = var.project_id
  role       = "roles/secretmanager.secretAccessor"
  depends_on = [google_service_account.brvm_dashboard_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}


resource "google_project_iam_binding" "bq_viewer" {
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "bq_data_editor" {
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "bq_job_user" {
  project    = var.project_id
  role       = "roles/bigquery.jobUser"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "run_admin" {
  project    = var.project_id
  role       = "roles/run.admin"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "storage_admin" {
  project    = var.project_id
  role       = "roles/storage.admin"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_cloud_run_service_iam_policy" "noauth" {
  location    = google_cloud_run_v2_service.tradvisor_service.location
  project     = google_cloud_run_v2_service.tradvisor_service.project
  service     = google_cloud_run_v2_service.tradvisor_service.name

  policy_data = data.google_iam_policy.noauth.policy_data
}
