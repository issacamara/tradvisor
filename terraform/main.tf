terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }

  backend "gcs" {
  }
}

import {
  to = google_artifact_registry_repository.tradvisor
  id = "projects/${var.project_id}/locations/${var.region}/repositories/tradvisor"
}

provider "google" {
  project = var.project_id
  region  = var.region
} 

resource "google_bigquery_dataset" "stocks" {
  dataset_id                 = "stocks"
  location                   = var.region
  delete_contents_on_destroy = true
  depends_on                 = [google_project_service.apis]
}

# =====================================================
# Artifact Registry Repository
# =====================================================
resource "google_artifact_registry_repository" "tradvisor" {
  location      = var.region
  repository_id = "tradvisor"
  description   = "Docker images for TRADVISOR application"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# =====================================================
# Table: financials
# Annual financial statements from RichBourse
# =====================================================
resource "google_bigquery_table" "financials" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.stocks.dataset_id
  table_id   = "financials"

  deletion_protection = true

  schema = jsonencode([
    {
      name        = "symbol"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Stock symbol (e.g., NTLC, ORGT)"
    },
    {
      name        = "fiscal_year"
      type        = "INTEGER"
      mode        = "REQUIRED"
      description = "Fiscal year of the financial statement"
    },
    {
      name        = "revenue"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Total revenue or chiffre d'affaires"
    },
    {
      name        = "net_income"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Net income or résultat net"
    },
    {
      name        = "total_debt"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Total debt or total passifs/dettes"
    },
    {
      name        = "cash_and_cash_equivalents"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cash and cash equivalents or trésorerie"
    },
    {
      name        = "total_equity"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Total equity or capitaux propres"
    },
    {
      name        = "announcement_date"
      type        = "DATE"
      mode        = "NULLABLE"
      description = "Date of the financial announcement (used for smart PDF download)"
    },
    {
      name        = "document_link"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "URL to the financial document PDF"
    },
    {
      name        = "collected_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "Timestamp when data was collected"
    }
  ])

  # No partitioning for financials (fiscal_year is INTEGER, not TIMESTAMP/DATE)
  clustering = ["symbol"]

  labels = {
    source = "richbourse"
    type   = "fundamental"
  }

  description = "Annual financial statements collected from RichBourse"
}

# =====================================================
# Table: ratings
# Financial ratings from RichBourse
# =====================================================
resource "google_bigquery_table" "ratings" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.stocks.dataset_id
  table_id   = "ratings"

  deletion_protection = false

  lifecycle {
    replace_triggered_by = [google_bigquery_table.financials]
  }

  schema = jsonencode([
    {
      name        = "symbol"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Stock symbol (e.g., NTLC, ORGT)"
    },
    {
      name        = "rating_year"
      type        = "INTEGER"
      mode        = "REQUIRED"
      description = "Year of the rating (e.g., 2025)"
    },
    {
      name        = "rating_short_term"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Short-term rating (e.g., A1 perspective Stable)"
    },
    {
      name        = "rating_long_term"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Long-term rating (e.g., AA- perspective Stable)"
    },
    {
      name        = "collected_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "Timestamp when data was collected"
    }
  ])

  # No partitioning - using INTEGER year

  clustering = ["symbol"]

  labels = {
    source = "richbourse"
    type   = "fundamental"
  }

  description = "Financial ratings collected from RichBourse"
}

# Note: ratings table uses rating_year (INTEGER) instead of rating_date

# Note: financials table cannot be partitioned because fiscal_year is INTEGER
# If you want partitioning, change fiscal_year to a DATE or TIMESTAMP field

resource "google_project_service" "apis" {
  project = var.project_id
  for_each = toset(var.apis)
  service                    = each.key
  disable_dependent_services = true
  
  lifecycle {
    # Prevent destroying API services to avoid errors when other resources exist
    # This allows terraform destroy to work without manual cleanup
    # prevent_destroy = true
  }
}


data "google_project" "project" {}



# Output the service URL
output "service_url" {
  value = google_cloud_run_v2_service.tradvisor_service.uri
}
