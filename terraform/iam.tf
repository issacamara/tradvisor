# Create a service account for the function
resource "google_service_account" "tradvisor_sa" {
  account_id = "tradvisor-sa-${data.google_project.project.number}"
  depends_on = [data.google_project.project]
  display_name = "Service Account for tradvisor application"
}

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

# resource "google_cloud_run_service_iam_policy" "noauth" {
#   location    = google_cloud_run_v2_service.tradvisor_service.location
#   project     = google_cloud_run_v2_service.tradvisor_service.project
#   service     = google_cloud_run_v2_service.tradvisor_service.name
#
#   policy_data = data.google_iam_policy.noauth.policy_data
# }
