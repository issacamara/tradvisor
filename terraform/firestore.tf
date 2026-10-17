resource "google_firestore_database" "v1" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_firestore_backup_schedule" "v1_daily" {
  project   = var.project_id
  database  = google_firestore_database.v1.name
  retention = "604800s"
  daily_recurrence {}

  lifecycle {
    prevent_destroy = true
  }
}
