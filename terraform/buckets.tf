resource "google_storage_bucket" "data-brvm" {
  name                        = "data-brvm"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy = true
}

resource "google_storage_bucket" "archive-brvm" {
  name                        = "archive-brvm"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy = true
}

resource "google_storage_bucket" "bucket" {
  name                        = "${var.project_id}-bucket"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
}
resource "google_storage_bucket_object" "scrape_shares" {
  name   = "scrape_shares.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.scrape_shares.output_path
}
resource "google_storage_bucket_object" "insert_shares" {
  name   = "insert_shares.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.insert_shares.output_path
}
