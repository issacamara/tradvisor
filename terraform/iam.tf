# Create a service account for the function
resource "google_service_account" "tradvisor_sa" {
  account_id   = "tradvisor-sa-${data.google_project.project.number}"
  depends_on   = [data.google_project.project]
  display_name = "Service Account for tradvisor application"

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

# Preserve the existing key. Key rotation requires a separate approved change.
resource "google_service_account_key" "tradvisor_sa_key" {
  count              = var.manage_legacy_service_account_credentials ? 1 : 0
  service_account_id = google_service_account.tradvisor_sa.name
  private_key_type   = "TYPE_GOOGLE_CREDENTIALS_FILE"

  # The legacy state records a timestamp keeper. Ignore it so its historical
  # value remains stable and cannot trigger an unapproved key replacement.
  lifecycle {
    ignore_changes  = [keepers]
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "tradvisor_sa_key_secret" {
  count     = var.manage_legacy_service_account_credentials ? 1 : 0
  secret_id = "tradvisor_sa_key"
  replication {
    auto {}
  }
  depends_on = [google_service_account.tradvisor_sa]

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "google_secret_manager_secret_version" "sa_key_secret_version" {
  count       = var.manage_legacy_service_account_credentials ? 1 : 0
  depends_on  = [google_service_account_key.tradvisor_sa_key, google_secret_manager_secret.tradvisor_sa_key_secret]
  secret      = google_secret_manager_secret.tradvisor_sa_key_secret[0].name
  secret_data = base64decode(google_service_account_key.tradvisor_sa_key[0].private_key)

  lifecycle {
    prevent_destroy = true
  }
}

# These legacy binding addresses remain intact for state compatibility. Ignoring
# membership changes prevents an authoritative binding from removing principals
# managed outside this configuration. A future additive-member migration needs
# verified state ownership and a separately approved preservation plan.
resource "google_project_iam_binding" "build_sa_roles" {
  depends_on = [google_service_account.tradvisor_sa]
  project    = var.project_id
  role       = "roles/cloudbuild.builds.builder"
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "function_invoker" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/cloudfunctions.invoker"
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "all_buckets_viewer" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/storage.objectViewer"
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    #   "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "log_writer" {
  project    = var.project_id
  depends_on = [google_service_account.tradvisor_sa]
  role       = "roles/logging.logWriter"
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
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

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "workflow_executor" {
  project    = var.project_id
  role       = "roles/workflows.invoker"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
    #     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}


resource "google_project_iam_binding" "sa_user" {
  project    = var.project_id
  role       = "roles/iam.serviceAccountUser"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "sms_accessor" {
  project    = var.project_id
  role       = "roles/secretmanager.secretAccessor"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
    #     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}


resource "google_project_iam_binding" "bq_viewer" {
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}",
    #     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "bq_data_editor" {
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
    #     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "bq_job_user" {
  project    = var.project_id
  role       = "roles/bigquery.jobUser"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
    #     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "run_admin" {
  project    = var.project_id
  role       = "roles/run.admin"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
    #     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}

resource "google_project_iam_binding" "storage_admin" {
  project    = var.project_id
  role       = "roles/storage.admin"
  depends_on = [google_service_account.tradvisor_sa]
  members = [
    "serviceAccount:${google_service_account.tradvisor_sa.email}"
    #     "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  ]

  lifecycle {
    ignore_changes = [members]
  }
}
