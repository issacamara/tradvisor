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

resource "google_secret_manager_secret" "openrouter_api_key" {
  secret_id = "openrouter_api_key"
  replication {
    auto {}
  }
  depends_on = [google_service_account.tradvisor_sa]
}

# Placeholder secret version for OpenRouter API key (needs actual key)
resource "google_secret_manager_secret_version" "openrouter_api_key_version" {
  depends_on = [google_secret_manager_secret.openrouter_api_key]
  secret      = google_secret_manager_secret.openrouter_api_key.name
  secret_data = var.openrouter_api_key  # Set this in terraform.tfvars
}

resource "google_secret_manager_secret_version" "sa_key_secret_version" {
  depends_on = [google_service_account_key.tradvisor_sa_key, google_secret_manager_secret.tradvisor_sa_key_secret]
  secret      = google_secret_manager_secret.tradvisor_sa_key_secret.name
  secret_data = base64decode(google_service_account_key.tradvisor_sa_key.private_key)
}

# Placeholder secret version for gmail account (needs actual credentials)
resource "google_secret_manager_secret_version" "gmail_acc_secret_version" {
  depends_on = [google_secret_manager_secret.tradvisor_gmail_acc]
  secret      = google_secret_manager_secret.tradvisor_gmail_acc.name
  secret_data = jsonencode(var.tradvisor_gmail_acc)
}

# Create a service account for the Cloud Run service
resource "google_service_account" "brvm_dashboard_sa" {
  account_id   = "brvm-dashboard-sa"
  display_name = "BRVM Dashboard Service Account"
  depends_on   = [google_project_service.apis[7] ]
}

# =====================================================
# IAM Members - using google_project_iam_member to avoid override issues
# =====================================================

# CloudBuild roles
resource "google_project_iam_member" "build_sa_roles_tradvisor" {
  depends_on = [google_service_account.tradvisor_sa]
  project    = var.project_id
  role       = "roles/cloudbuild.builds.builder"
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

resource "google_project_iam_member" "build_sa_roles_compute" {
  depends_on = [google_service_account.tradvisor_sa]
  project    = var.project_id
  role       = "roles/cloudbuild.builds.builder"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "build_sa_roles_cloudbuild" {
  depends_on = [google_service_account.tradvisor_sa]
  project    = var.project_id
  role       = "roles/cloudbuild.builds.builder"
  member     = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
}

# Cloud Functions invoker
resource "google_project_iam_member" "function_invoker_tradvisor" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

resource "google_project_iam_member" "function_invoker_compute" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Storage object viewer
resource "google_project_iam_member" "all_buckets_viewer" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/storage.objectViewer"
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Logging log writer
resource "google_project_iam_member" "log_writer_tradvisor" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/logging.logWriter"
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

resource "google_project_iam_member" "log_writer_compute" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/logging.logWriter"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Cloud Run invoker
resource "google_project_iam_member" "cloud_run_sa_invoker" {
  project    = var.project_id
  role       = "roles/run.invoker"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Workflows invoker
resource "google_project_iam_member" "workflow_executor" {
  project    = var.project_id
  role       = "roles/workflows.invoker"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Service Account User
resource "google_project_iam_member" "sa_user_tradvisor" {
  project    = var.project_id
  role       = "roles/iam.serviceAccountUser"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

resource "google_project_iam_member" "sa_user_compute" {
  project    = var.project_id
  role       = "roles/iam.serviceAccountUser"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Secret Manager accessor
resource "google_project_iam_member" "sms_accessor" {
  project    = var.project_id
  role       = "roles/secretmanager.secretAccessor"
  depends_on = [google_service_account.brvm_dashboard_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Grant secret accessor at secret level for SA key
resource "google_secret_manager_secret_iam_member" "sa_key_secret_accessor" {
  project    = var.project_id
  secret_id  = "tradvisor_sa_key"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Grant secret accessor at secret level for gmail account
resource "google_secret_manager_secret_iam_member" "gmail_secret_accessor" {
  project    = var.project_id
  secret_id  = "tradvisor_gmail_acc"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Grant secret accessor for OpenRouter API key
resource "google_secret_manager_secret_iam_member" "openrouter_api_key_accessor" {
  project    = var.project_id
  secret_id  = "openrouter_api_key"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
  depends_on = [google_secret_manager_secret.openrouter_api_key, google_secret_manager_secret_version.openrouter_api_key_version]
}

# BigQuery roles
resource "google_project_iam_member" "bq_viewer" {
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

resource "google_project_iam_member" "bq_data_editor" {
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

resource "google_project_iam_member" "bq_job_user" {
  project    = var.project_id
  role       = "roles/bigquery.jobUser"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Cloud Run admin
resource "google_project_iam_member" "run_admin" {
  project    = var.project_id
  role       = "roles/run.admin"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Storage admin
resource "google_project_iam_member" "storage_admin" {
  project    = var.project_id
  role       = "roles/storage.admin"
  depends_on = [google_service_account.tradvisor_sa]
  member     = "serviceAccount:${google_service_account.tradvisor_sa.email}"
}

# Make the Cloud Run service publicly accessible
resource "google_cloud_run_v2_service_iam_member" "noauth" {
  project  = google_cloud_run_v2_service.tradvisor_service.project
  location = google_cloud_run_v2_service.tradvisor_service.location
  name     = google_cloud_run_v2_service.tradvisor_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
