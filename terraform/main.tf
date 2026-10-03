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

resource "google_bigquery_table" "brvm_companies" {
  dataset_id          = "stocks"
  table_id            = "brvm_companies"
  deletion_protection = true
  clustering          = ["sector"]
  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED" },
    { name = "name", type = "STRING", mode = "NULLABLE" },
    { name = "sector", type = "STRING", mode = "NULLABLE" },
    { name = "activity_description", type = "STRING", mode = "NULLABLE" },
  ])
  lifecycle { prevent_destroy = true }
}

resource "google_bigquery_table" "dividends" {
  dataset_id          = "stocks"
  table_id            = "dividends"
  deletion_protection = true
  clustering          = ["symbol"]
  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED" },
    { name = "dividend", type = "FLOAT", mode = "NULLABLE" },
    { name = "payment_date", type = "DATE", mode = "NULLABLE" },
    { name = "fiscal_year", type = "INTEGER", mode = "NULLABLE" },
  ])
  lifecycle { prevent_destroy = true }
}

resource "google_bigquery_table" "financials" {
  dataset_id          = "stocks"
  table_id            = "financials"
  deletion_protection = true
  clustering          = ["symbol"]
  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED" },
    { name = "fiscal_year", type = "INTEGER", mode = "REQUIRED" },
    { name = "revenue", type = "FLOAT", mode = "NULLABLE" },
    { name = "net_income", type = "FLOAT", mode = "NULLABLE" },
    { name = "total_debt", type = "FLOAT", mode = "NULLABLE" },
    { name = "cash_and_cash_equivalents", type = "FLOAT", mode = "NULLABLE" },
    { name = "total_equity", type = "FLOAT", mode = "NULLABLE" },
    { name = "collected_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "document_link", type = "STRING", mode = "NULLABLE" },
  ])
  lifecycle { prevent_destroy = true }
}

resource "google_bigquery_table" "ratings" {
  dataset_id          = "stocks"
  table_id            = "ratings"
  deletion_protection = true
  clustering          = ["symbol"]
  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED" },
    { name = "rating_year", type = "INTEGER", mode = "REQUIRED" },
    { name = "rating_short_term", type = "STRING", mode = "NULLABLE" },
    { name = "rating_long_term", type = "STRING", mode = "NULLABLE" },
    { name = "collected_at", type = "TIMESTAMP", mode = "NULLABLE" },
  ])
  lifecycle { prevent_destroy = true }
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
