locals {
  publication_control_enabled = local.v1_runtime_enabled
}

# This isolated bucket is the control plane's only durable state boundary.
resource "google_storage_bucket" "publication_control" {
  count                       = local.publication_control_enabled ? 1 : 0
  name                        = "${var.project_id}-publication-control"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account" "publication_control" {
  count        = local.publication_control_enabled ? 1 : 0
  account_id   = var.publication_control_service_account_id
  display_name = "Tradvisor publication control"
  project      = var.project_id

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_cloud_tasks_queue" "publication_control_dispatch" {
  count    = local.publication_control_enabled ? 1 : 0
  name     = "publication-control-dispatch"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 1
    max_dispatches_per_second = 1
  }

  retry_config {
    max_attempts = 1
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_iam_custom_role" "publication_control_state" {
  count       = local.publication_control_enabled ? 1 : 0
  project     = var.project_id
  role_id     = "publicationControlState"
  title       = "Tradvisor publication control state"
  description = "Read and conditionally update only publication-control state objects."
  permissions = [
    "storage.objects.create",
    "storage.objects.delete",
    "storage.objects.get",
    "storage.objects.update",
  ]
}

resource "google_storage_bucket_iam_member" "publication_control_state" {
  count  = local.publication_control_enabled ? 1 : 0
  bucket = google_storage_bucket.publication_control[0].name
  role   = google_project_iam_custom_role.publication_control_state[0].name
  member = "serviceAccount:${google_service_account.publication_control[0].email}"
}

resource "google_cloud_tasks_queue_iam_member" "publication_control_enqueuer" {
  count    = local.publication_control_enabled ? 1 : 0
  project  = var.project_id
  location = google_cloud_tasks_queue.publication_control_dispatch[0].location
  name     = google_cloud_tasks_queue.publication_control_dispatch[0].name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.publication_control[0].email}"
}

resource "google_service_account_iam_member" "publication_control_task_token_creator" {
  count              = local.publication_control_enabled ? 1 : 0
  service_account_id = google_service_account.publication_control[0].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.publication_control[0].email}"
}

# Scope job invocation to the one existing analytical job; no project-wide run role.
resource "google_cloud_run_v2_job_iam_member" "publication_control_batch_invoker" {
  count    = local.publication_control_enabled ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_job.v1_batch[0].location
  name     = google_cloud_run_v2_job.v1_batch[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.publication_control[0].email}"
}

resource "google_cloud_run_v2_job_iam_member" "publication_control_batch_viewer" {
  count    = local.publication_control_enabled ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_job.v1_batch[0].location
  name     = google_cloud_run_v2_job.v1_batch[0].name
  role     = "roles/run.viewer"
  member   = "serviceAccount:${google_service_account.publication_control[0].email}"
}
