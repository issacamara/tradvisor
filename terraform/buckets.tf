
data "archive_file" "assets" {
  for_each    = toset(var.functions)
  type        = "zip"
  output_path = "${each.key}.zip"

  source {
    content  = file("../scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("../scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("../scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("../scripts/${each.key}.py")
    filename = "main.py"
  }
}

resource "google_storage_bucket" "data-brvm" {
  name                        = "data-brvm1"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket" "archive-brvm" {
  project                     = var.project_id
  name                        = "archive-brvm1"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket" "bucket" {
  name                        = "tmp-${var.project_id}"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
}
resource "google_storage_bucket_object" "src-code" {
  for_each   = toset(var.functions)
  depends_on = [data.archive_file.assets, google_storage_bucket.bucket]
  name       = "${each.key}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.assets[each.key].output_path
}

resource "null_resource" "delete_archive" {
  # Trigger this resource whenever the archive changes
  for_each = toset(var.functions)
  triggers = {
    archive_path = data.archive_file.assets[each.key].output_path
  }
  provisioner "local-exec" {
    command = "rm -f ${data.archive_file.assets[each.key].output_path}"
  }
  depends_on = [data.archive_file.assets, google_storage_bucket_object.src-code]
}