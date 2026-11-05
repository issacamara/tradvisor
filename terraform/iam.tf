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

# The key payload is provisioned by an authorized operator. Terraform owns
# only the environment-local secret metadata and this resource-level grant.
resource "google_secret_manager_secret" "openrouter" {
  project   = var.project_id
  secret_id = var.openrouter_secret_id

  replication {
    auto {}
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = contains(["development", "production"], var.environment) && trimspace(var.v1_environment_project_id) != "" && var.v1_environment_project_id == var.project_id
      error_message = "OpenRouter secret metadata must target the project explicitly bound to its environment."
    }
  }

  depends_on = [data.google_project.project]
}

# The dataset-level Data Editor grant allows table creation and covers every
# table in stocks; company reads and financials input/staging access stay
# table-scoped. FI-1's own identity avoids inheriting legacy object-storage
# permissions.
resource "google_service_account" "fi1_financial_runtime" {
  count        = var.manage_fi1_financial_job ? 1 : 0
  project      = var.project_id
  account_id   = var.fi1_financial_runtime_service_account_id
  display_name = "Tradvisor FI-1 financial ingestion runtime"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_iam_member" "fi1_financial_bigquery_job_user" {
  count   = var.manage_fi1_financial_job ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"
}

resource "google_bigquery_dataset_iam_member" "fi1_stocks_editor" {
  count      = var.manage_fi1_financial_job ? 1 : 0
  project    = var.project_id
  dataset_id = "stocks"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"
}

# Reuse the existing V1 Firestore transactional control path for the FI-1
# runtime lease. This grants no new datastore resource; #362 owns the lease
# protocol and uses the existing Firestore control document.
resource "google_project_iam_member" "fi1_financial_firestore" {
  count   = var.manage_fi1_financial_job ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"
}

resource "google_bigquery_table_iam_member" "fi1_companies_reader" {
  count      = var.manage_fi1_financial_job ? 1 : 0
  project    = var.project_id
  dataset_id = google_bigquery_table.brvm_companies.dataset_id
  table_id   = google_bigquery_table.brvm_companies.table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"
}

resource "google_bigquery_table_iam_member" "fi1_financials_editor" {
  count      = var.manage_fi1_financial_job ? 1 : 0
  project    = var.project_id
  dataset_id = google_bigquery_table.financials.dataset_id
  table_id   = google_bigquery_table.financials.table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"
}

resource "google_bigquery_table_iam_member" "fi1_financials_staging_editor" {
  count      = var.manage_fi1_financial_job ? 1 : 0
  project    = var.project_id
  dataset_id = google_bigquery_table.financials_staging.dataset_id
  table_id   = google_bigquery_table.financials_staging.table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"
}

resource "google_secret_manager_secret_iam_member" "fi1_financial_openrouter" {
  count     = var.manage_fi1_financial_job ? 1 : 0
  project   = google_secret_manager_secret.openrouter.project
  secret_id = google_secret_manager_secret.openrouter.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.fi1_financial_runtime[0].email}"
}

resource "google_service_account" "fi1_financial_scheduler" {
  count        = var.manage_fi1_financial_job ? 1 : 0
  project      = var.project_id
  account_id   = var.fi1_financial_scheduler_service_account_id
  display_name = "Tradvisor FI-1 Scheduler caller"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_cloud_run_v2_job_iam_member" "fi1_financial_scheduler_invoker" {
  count    = var.manage_fi1_financial_job ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_job.fi1_financials[0].location
  name     = google_cloud_run_v2_job.fi1_financials[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.fi1_financial_scheduler[0].email}"
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
