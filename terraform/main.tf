terraform {
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }
}

provider "google" {
  project                         = var.project_id
  region                          = var.region
  add_terraform_attribution_label = false
}

resource "google_bigquery_dataset" "stocks" {
  count                      = var.manage_legacy_bigquery_datasets ? 1 : 0
  dataset_id                 = "stocks"
  location                   = var.region
  delete_contents_on_destroy = false
  depends_on                 = [google_project_service.apis]

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "google_bigquery_table" "shares" {
  dataset_id          = "stocks"
  table_id            = "shares"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "date"
  }

  clustering = ["symbol"]

  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "NULLABLE" },
    { name = "name", type = "STRING", mode = "NULLABLE" },
    { name = "open", type = "FLOAT", mode = "NULLABLE" },
    { name = "high", type = "FLOAT", mode = "NULLABLE" },
    { name = "low", type = "FLOAT", mode = "NULLABLE" },
    { name = "close", type = "FLOAT", mode = "NULLABLE" },
    { name = "volume", type = "FLOAT", mode = "NULLABLE" },
    { name = "date", type = "DATE", mode = "NULLABLE" },
  ])

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_service" "apis" {
  project                    = var.project_id
  for_each                   = var.manage_legacy_project_services ? toset(var.apis) : toset([])
  service                    = each.key
  disable_dependent_services = false
  disable_on_destroy         = false

  lifecycle {
    prevent_destroy = true
  }
}


data "google_project" "project" {}
