
locals {
  function_entrypoint_roots = {
    scrape_shares          = "../functions/shares"
    insert_shares          = "../functions/shares"
    scrape_dividends       = "../functions/dividends"
    insert_dividends       = "../functions/dividends"
    scrape_financials      = "../functions/financials"
    insert_financials      = "../functions/financials"
    scrape_financials_init = "../archive/legacy-ingestion/scripts"
    scrape_ratings         = "../functions/ratings"
    insert_ratings         = "../functions/ratings"
    scrape_ratings_init    = "../functions/ratings"
  }
  function_dependency_roots = {
    insert_shares          = "../functions/shares"
    scrape_financials      = "../functions/financials"
    insert_financials      = "../functions/financials"
    scrape_financials_init = "../functions/financials"
    scrape_ratings_init    = "../functions/ratings"
  }
  legacy_function_root = "../archive/legacy-ingestion/scripts"
}

data "archive_file" "assets" {
  for_each    = var.manage_legacy_source_objects ? toset(var.functions) : toset([])
  type        = "zip"
  output_path = "${each.key}.zip"

  source {
    content  = file("${local.legacy_function_root}/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("${local.legacy_function_root}/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("${local.legacy_function_root}/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${lookup(local.function_entrypoint_roots, each.key, local.legacy_function_root)}/${each.key}.py")
    filename = "main.py"
  }

  dynamic "source" {
    for_each = lookup(var.function_local_files, each.key, [])
    content {
      content  = file("${lookup(local.function_dependency_roots, each.key, local.legacy_function_root)}/${source.value}")
      filename = source.value
    }
  }

  dynamic "source" {
    for_each = contains(["scrape_financials", "insert_financials", "scrape_ratings", "insert_ratings"], each.key) ? [1] : []
    content {
      content  = file("../archive/legacy-ingestion/scripts/mapping.csv")
      filename = "mapping.csv"
    }
  }

  dynamic "source" {
    for_each = contains(["scrape_financials", "insert_financials"], each.key) ? [1] : []
    content {
      content  = file("../archive/legacy-ingestion/scripts/scrape_financials_init.py")
      filename = "scrape_financials_init.py"
    }
  }

  dynamic "source" {
    for_each = contains(["scrape_ratings"], each.key) ? [1] : []
    content {
      content  = file("../archive/legacy-ingestion/scripts/scrape_ratings_init.py")
      filename = "scrape_ratings_init.py"
    }
  }
}

data "archive_file" "new_function_assets" {
  for_each    = var.manage_new_function_sources ? var.managed_function_sources : toset([])
  type        = "zip"
  output_path = "${each.key}.zip"

  source {
    content  = file("../archive/legacy-ingestion/scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("../archive/legacy-ingestion/scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("../archive/legacy-ingestion/scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("../archive/legacy-ingestion/scripts/mapping.csv")
    filename = "mapping.csv"
  }
  source {
    content  = file("${lookup(local.function_entrypoint_roots, each.key, local.legacy_function_root)}/${each.key}.py")
    filename = "main.py"
  }
  dynamic "source" {
    for_each = each.key == "scrape_financials" || each.key == "insert_financials" ? [1] : []
    content {
      content  = file("../functions/financials/scrape_financials_init.py")
      filename = "scrape_financials_init.py"
    }
  }
  dynamic "source" {
    for_each = each.key == "scrape_ratings" ? [1] : []
    content {
      content  = file("../functions/ratings/scrape_ratings_init.py")
      filename = "scrape_ratings_init.py"
    }
  }
}

data "archive_file" "initialization_assets" {
  for_each    = var.manage_new_function_sources ? var.initialization_functions : toset([])
  type        = "zip"
  output_path = "${each.key}.zip"

  source {
    content  = file("../archive/legacy-ingestion/scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("../archive/legacy-ingestion/scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("../archive/legacy-ingestion/scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("../archive/legacy-ingestion/scripts/mapping.csv")
    filename = "mapping.csv"
  }
  source {
    content  = file("${lookup(local.function_entrypoint_roots, each.key, local.legacy_function_root)}/${each.key}.py")
    filename = "main.py"
  }
  dynamic "source" {
    for_each = each.key == "scrape_financials_init" ? [1] : []
    content {
      content  = file("../archive/legacy-ingestion/scripts/company_reference.py")
      filename = "company_reference.py"
    }
  }
  dynamic "source" {
    for_each = each.key == "scrape_ratings_init" ? [1] : []
    content {
      content  = file("../functions/ratings/scrape_ratings.py")
      filename = "scrape_ratings.py"
    }
  }
}

resource "google_storage_bucket" "data-brvm" {
  name                        = "data-${data.google_project.project.number}"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "google_storage_bucket" "archive-brvm" {
  project                     = var.project_id
  name                        = "archive-${data.google_project.project.number}"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "google_storage_bucket" "bucket" {
  name                        = "tmp-${data.google_project.project.number}"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}
resource "google_storage_bucket_object" "src-code" {
  for_each   = var.manage_legacy_source_objects ? toset(var.functions) : toset([])
  depends_on = [data.archive_file.assets, google_storage_bucket.bucket]
  name       = "${each.key}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.assets[each.key].output_path

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "google_storage_bucket_object" "new-function-src-code" {
  for_each   = var.manage_new_function_sources ? var.managed_function_sources : toset([])
  depends_on = [data.archive_file.new_function_assets, google_storage_bucket.bucket]
  name       = "${each.key}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.new_function_assets[each.key].output_path
}

resource "google_storage_bucket_object" "initialization-src-code" {
  for_each   = var.manage_new_function_sources ? var.initialization_functions : toset([])
  depends_on = [data.archive_file.initialization_assets, google_storage_bucket.bucket]
  name       = "${each.key}.zip"
  bucket     = google_storage_bucket.bucket.name
  source     = data.archive_file.initialization_assets[each.key].output_path

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "null_resource" "delete_archive" {
  # Trigger this resource whenever the archive changes
  for_each = var.manage_legacy_source_objects ? toset(var.functions) : toset([])
  triggers = {
    archive_path = data.archive_file.assets[each.key].output_path
  }
  provisioner "local-exec" {
    command = "rm -f ${data.archive_file.assets[each.key].output_path}"
  }
  depends_on = [data.archive_file.assets, google_storage_bucket_object.src-code]
}

resource "null_resource" "delete_new_function_archive" {
  for_each = var.manage_new_function_sources ? var.managed_function_sources : toset([])
  triggers = {
    archive_path = data.archive_file.new_function_assets[each.key].output_path
  }
  provisioner "local-exec" {
    command = "rm -f ${data.archive_file.new_function_assets[each.key].output_path}"
  }
  depends_on = [data.archive_file.new_function_assets, google_storage_bucket_object.new-function-src-code]
}
