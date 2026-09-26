locals {
  recovery_register_bucket_name = "${var.project_id}-v1-recovery-register"
}

resource "google_storage_bucket" "v1_recovery_register" {
  project                     = var.project_id
  name                        = local.recovery_register_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_iam_custom_role" "recovery_register_writer" {
  project     = var.project_id
  role_id     = "tradvisorRecoveryRegisterWriter"
  title       = "Tradvisor recovery register writer"
  description = "Read and append recovery decisions without deleting register history."
  permissions = [
    "storage.objects.create",
    "storage.objects.get",
    "storage.objects.list",
  ]
}

resource "google_project_iam_custom_role" "recovery_register_cleanup" {
  project     = var.project_id
  role_id     = "tradvisorRecoveryRegisterCleanup"
  title       = "Tradvisor recovery register cleanup"
  description = "Restricted cleanup role for evidence-qualified recovery register records."
  permissions = [
    "storage.objects.delete",
    "storage.objects.get",
    "storage.objects.list",
  ]
}

resource "google_storage_bucket_iam_member" "recovery_register_runtime_writer" {
  count  = local.v1_runtime_enabled ? 1 : 0
  bucket = google_storage_bucket.v1_recovery_register.name
  role   = google_project_iam_custom_role.recovery_register_writer.name
  member = "serviceAccount:${google_service_account.v1_runtime[0].email}"
}

resource "google_storage_bucket_iam_member" "recovery_register_cleanup" {
  for_each = var.recovery_register_cleanup_members
  bucket   = google_storage_bucket.v1_recovery_register.name
  role     = google_project_iam_custom_role.recovery_register_cleanup.name
  member   = each.value
}
