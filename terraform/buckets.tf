
# Original functions from var.functions
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
  
  # Force recreation when source files change
  lifecycle {
    create_before_destroy = true
  }
}

# Additional functions (financials and ratings)
data "archive_file" "assets_extra" {
  for_each    = toset(["scrape_financials", "insert_financials", "scrape_ratings", "insert_ratings"])
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
  # Include init scripts for scrape functions (needed for auto-initialization)
  source {
    content  = file("../scripts/scrape_financials_init.py")
    filename = "scrape_financials_init.py"
  }
  source {
    content  = file("../scripts/scrape_ratings_init.py")
    filename = "scrape_ratings_init.py"
  }
  
  # Force recreation when source files change
  lifecycle {
    create_before_destroy = true
  }
}

# Initialization functions
data "archive_file" "assets_init" {
  for_each    = toset(["scrape_financials_init", "scrape_ratings_init"])
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
  
  # Force recreation when source files change
  lifecycle {
    create_before_destroy = true
  }
}

resource "google_storage_bucket" "data-brvm" {
  name                        = "data-${data.google_project.project.number}"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket" "archive-brvm" {
  project                     = var.project_id
  name                        = "archive-${data.google_project.project.number}"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket" "bucket" {
  name                        = "tmp-${data.google_project.project.number}"
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

resource "google_storage_bucket_object" "src-code-extra" {
  for_each   = toset(["scrape_financials", "insert_financials", "scrape_ratings", "insert_ratings"])
  depends_on = [data.archive_file.assets_extra, google_storage_bucket.bucket]
  name       = "${each.key}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.assets_extra[each.key].output_path
}

resource "google_storage_bucket_object" "src-code-init" {
  for_each   = toset(["scrape_financials_init", "scrape_ratings_init"])
  depends_on = [data.archive_file.assets_init, google_storage_bucket.bucket]
  name       = "${each.key}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.assets_init[each.key].output_path
}

resource "null_resource" "delete_archive" {
  # Trigger this resource whenever the archive changes
  for_each = toset(var.functions)
  triggers = {
    archive_path = data.archive_file.assets[each.key].output_path
  }
  provisioner "local-exec" {
    command = "rm -f ${data.archive_file.assets[each.key].output_path}"
    interpreter = ["bash", "-c"]
  }
  # Run after apply completes
  provisioner "local-exec" {
    when    = destroy
    command = "rm -f ${each.key}.zip"
    interpreter = ["bash", "-c"]
  }
  depends_on = [data.archive_file.assets, google_storage_bucket_object.src-code]
}

resource "null_resource" "delete_archive_extra" {
  # Trigger this resource whenever the archive changes
  for_each = toset(["scrape_financials", "insert_financials", "scrape_ratings", "insert_ratings"])
  triggers = {
    archive_path = data.archive_file.assets_extra[each.key].output_path
  }
  provisioner "local-exec" {
    command = "rm -f ${data.archive_file.assets_extra[each.key].output_path}"
    interpreter = ["bash", "-c"]
  }
  # Run after apply completes
  provisioner "local-exec" {
    when    = destroy
    command = "rm -f ${each.key}.zip"
    interpreter = ["bash", "-c"]
  }
  depends_on = [data.archive_file.assets_extra, google_storage_bucket_object.src-code-extra]
}

resource "null_resource" "delete_archive_init" {
  for_each = toset(["scrape_financials_init", "scrape_ratings_init"])
  triggers = {
    archive_path = data.archive_file.assets_init[each.key].output_path
  }
  provisioner "local-exec" {
    command = "rm -f ${data.archive_file.assets_init[each.key].output_path}"
    interpreter = ["bash", "-c"]
  }
  provisioner "local-exec" {
    when    = destroy
    command = "rm -f ${each.key}.zip"
    interpreter = ["bash", "-c"]
  }
  depends_on = [data.archive_file.assets_init, google_storage_bucket_object.src-code-init]
}