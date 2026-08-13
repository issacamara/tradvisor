# Original functions from var.functions
data "archive_file" "assets" {
  for_each    = toset(var.functions)
  type        = "zip"
  output_path = "${path.module}/.build/${each.key}.zip"

  source {
    content  = file("${path.module}/../scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("${path.module}/../scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("${path.module}/../scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../scripts/${each.key}.py")
    filename = "main.py"
  }
}

# Additional functions (financials and ratings)
data "archive_file" "assets_extra" {
  for_each    = toset(["scrape_financials", "insert_financials", "scrape_ratings", "insert_ratings"])
  type        = "zip"
  output_path = "${path.module}/.build/${each.key}.zip"

  source {
    content  = file("${path.module}/../scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("${path.module}/../scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("${path.module}/../scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../scripts/${each.key}.py")
    filename = "main.py"
  }
  source {
    content  = file("${path.module}/../scripts/scrape_financials_init.py")
    filename = "scrape_financials_init.py"
  }
  source {
    content  = file("${path.module}/../scripts/scrape_ratings_init.py")
    filename = "scrape_ratings_init.py"
  }
}

# Initialization functions
data "archive_file" "assets_init" {
  for_each    = toset(["scrape_financials_init", "scrape_ratings_init"])
  type        = "zip"
  output_path = "${path.module}/.build/${each.key}.zip"

  source {
    content  = file("${path.module}/../scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("${path.module}/../scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("${path.module}/../scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../scripts/${each.key}.py")
    filename = "main.py"
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
  name       = "src/${each.key}-${data.archive_file.assets[each.key].output_sha256}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.assets[each.key].output_path
}

resource "google_storage_bucket_object" "src-code-extra" {
  for_each   = toset(["scrape_financials", "insert_financials", "scrape_ratings", "insert_ratings"])
  depends_on = [data.archive_file.assets_extra, google_storage_bucket.bucket]
  name       = "src/${each.key}-${data.archive_file.assets_extra[each.key].output_sha256}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.assets_extra[each.key].output_path
}

resource "google_storage_bucket_object" "src-code-init" {
  for_each   = toset(["scrape_financials_init", "scrape_ratings_init"])
  depends_on = [data.archive_file.assets_init, google_storage_bucket.bucket]
  name       = "src/${each.key}-${data.archive_file.assets_init[each.key].output_sha256}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.assets_init[each.key].output_path
}