# Create a service account for the function
resource "google_service_account" "function_service_account" {
  account_id = "sa-${data.google_project.project.number}"
  #   account_id   = "function-sa"
  display_name = "Cloud Function Service Account"
}

resource "google_project_iam_binding" "build_sa_roles" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.builder"
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "function_invoker" {
  project = var.project_id
  role          = "roles/cloudfunctions.invoker"
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "all_buckets_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  members  = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"]
}

resource "google_project_iam_binding" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

# Grant the necessary roles to the service account
resource "google_project_iam_binding" "cloud_run_sa_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"

  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "workflow_executor" {
  project = var.project_id
  role    = "roles/workflows.invoker"

  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"

  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}
resource "google_project_iam_binding" "bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"

  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}
# resource "google_project_iam_binding" "bq_job_user" {
#   project = var.project_id
#   role    = "roles/bigquery.jobUser"
#
#   members = [
#     "serviceAccount:${google_service_account.function_service_account.email}",
#     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
#   ]
# }

resource "google_project_iam_binding" "bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"

  members = [
    "serviceAccount:${google_service_account.function_service_account.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]
}