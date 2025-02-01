# Create a service account for the function
resource "google_service_account" "function_service_account" {
  account_id = "sa-${data.google_project.project.number}"
  depends_on = [data.google_project.project]
  #   account_id   = "function-sa"
  display_name = "Cloud Function Service Account"
}

resource "google_project_iam_binding" "build_sa_roles" {
  depends_on = [google_service_account.function_service_account]
  project    = var.project_id
  role       = "roles/cloudbuild.builds.builder"
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "function_invoker" {
  project    = var.project_id
  depends_on = [google_service_account.function_service_account]
  role       = "roles/cloudfunctions.invoker"
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "all_buckets_viewer" {
  project    = var.project_id
  depends_on = [google_service_account.function_service_account]
  role       = "roles/storage.objectViewer"
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
  "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"]
}

resource "google_project_iam_binding" "log_writer" {
  project    = var.project_id
  depends_on = [google_service_account.function_service_account]
  role       = "roles/logging.logWriter"
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

# Grant the necessary roles to the service account
resource "google_project_iam_binding" "cloud_run_sa_invoker" {
  project    = var.project_id
  role       = "roles/run.invoker"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "workflow_executor" {
  project    = var.project_id
  role       = "roles/workflows.invoker"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "cloudscheduler_service_agent" {
  project    = var.project_id
  role       = "roles/cloudscheduler.serviceAgent"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}
resource "google_project_iam_binding" "cloudscheduler_admin" {
  project    = var.project_id
  role       = "roles/cloudscheduler.admin"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}


resource "google_project_iam_binding" "sa_user" {
  project    = var.project_id
  role       = "roles/iam.serviceAccountUser"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}
resource "google_project_iam_binding" "bq_viewer" {
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "bq_data_editor" {
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "bq_job_user" {
  project    = var.project_id
  role       = "roles/bigquery.jobUser"
  depends_on = [google_service_account.function_service_account]
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}