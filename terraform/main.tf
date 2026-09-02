terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }

  backend "gcs" {}
}

import {
  to = google_artifact_registry_repository.tradvisor
  id = "projects/${var.project_id}/locations/${var.region}/repositories/tradvisor"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "project" {}

resource "google_project_service" "apis" {
  for_each                   = toset(var.apis)
  project                    = var.project_id
  service                    = each.key
  disable_dependent_services = true
}

# =====================================================
# Artifact Registry
# =====================================================
resource "google_artifact_registry_repository" "tradvisor" {
  location      = var.region
  repository_id = "tradvisor"
  description   = "Docker images for TRADVISOR application"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# =====================================================
# BigQuery Dataset
# =====================================================
resource "google_bigquery_dataset" "stocks" {
  dataset_id                 = "stocks"
  location                   = var.region
  delete_contents_on_destroy = true
  depends_on                 = [google_project_service.apis]
}

# =====================================================
# Table: SHARES
# =====================================================
resource "google_bigquery_table" "shares" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.stocks.dataset_id
  table_id            = "shares"
  deletion_protection = true

  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED", description = "Stock symbol (e.g., NTLC, ORGT)" },
    { name = "name", type = "STRING", mode = "NULLABLE", description = "Company name" },
    { name = "open", type = "FLOAT", mode = "NULLABLE", description = "Opening price in XOF" },
    { name = "high", type = "FLOAT", mode = "NULLABLE", description = "Highest price in XOF" },
    { name = "low", type = "FLOAT", mode = "NULLABLE", description = "Lowest price in XOF" },
    { name = "close", type = "FLOAT", mode = "NULLABLE", description = "Closing price in XOF" },
    { name = "volume", type = "FLOAT", mode = "NULLABLE", description = "Trading volume" },
    { name = "date", type = "DATE", mode = "NULLABLE", description = "Trading date" }
  ])

  labels = {
    source = "sikafinance"
    type   = "market_data"
  }

  description = "Daily stock prices collected from BRVM"
}

# =====================================================
# Table: FINANCIALS
# =====================================================
resource "google_bigquery_table" "financials" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.stocks.dataset_id
  table_id            = "financials"
  deletion_protection = true

  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED", description = "Stock symbol" },
    { name = "fiscal_year", type = "INTEGER", mode = "REQUIRED", description = "Fiscal year of the financial statement" },
    { name = "revenue", type = "FLOAT", mode = "NULLABLE", description = "Total revenue or chiffre d'affaires" },
    { name = "net_income", type = "FLOAT", mode = "NULLABLE", description = "Net income or résultat net" },
    { name = "total_debt", type = "FLOAT", mode = "NULLABLE", description = "Total debt or total passifs/dettes" },
    { name = "cash_and_cash_equivalents", type = "FLOAT", mode = "NULLABLE", description = "Cash and cash equivalents or trésorerie" },
    { name = "total_equity", type = "FLOAT", mode = "NULLABLE", description = "Total equity or capitaux propres" },
    { name = "document_link", type = "STRING", mode = "NULLABLE", description = "URL to the financial document PDF" },
    { name = "collected_at", type = "TIMESTAMP", mode = "NULLABLE", description = "Timestamp when data was collected" }
  ])

  clustering = ["symbol"]

  labels = {
    source = "richbourse"
    type   = "fundamental"
  }

  description = "Annual financial statements collected from RichBourse"
}

# =====================================================
# Table: RATINGS
# =====================================================
resource "google_bigquery_table" "ratings" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.stocks.dataset_id
  table_id            = "ratings"
  deletion_protection = false

  lifecycle {
    replace_triggered_by = [google_bigquery_table.financials]
  }

  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED", description = "Stock symbol" },
    { name = "rating_year", type = "INTEGER", mode = "REQUIRED", description = "Year of the rating" },
    { name = "rating_short_term", type = "STRING", mode = "NULLABLE", description = "Short-term rating" },
    { name = "rating_long_term", type = "STRING", mode = "NULLABLE", description = "Long-term rating" },
    { name = "collected_at", type = "TIMESTAMP", mode = "NULLABLE", description = "Timestamp when data was collected" }
  ])

  clustering = ["symbol"]

  labels = {
    source = "richbourse"
    type   = "fundamental"
  }

  description = "Financial ratings collected from RichBourse"
}

# =====================================================
# Table: DIVIDENDS
# =====================================================
resource "google_bigquery_table" "dividends" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.stocks.dataset_id
  table_id            = "dividends"
  deletion_protection = true

  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED", description = "Stock symbol" },
    { name = "dividend", type = "FLOAT", mode = "NULLABLE", description = "Dividend amount in XOF" },
    { name = "payment_date", type = "DATE", mode = "NULLABLE", description = "Date when dividend was paid" },
    { name = "fiscal_year", type = "INTEGER", mode = "NULLABLE", description = "Fiscal year linked to the dividend" }
  ])

  clustering = ["symbol"]

  labels = {
    source = "richbourse"
    type   = "fundamental"
  }

  description = "Dividend payments collected from RichBourse"
}

# =====================================================
# Table: BRVM_COMPANIES
# =====================================================
resource "google_bigquery_table" "brvm_companies" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.stocks.dataset_id
  table_id            = "brvm_companies"
  deletion_protection = true

  schema = jsonencode([
    { name = "symbol", type = "STRING", mode = "REQUIRED", description = "Stock symbol (e.g., NTLC, ORGT)" },
    { name = "name", type = "STRING", mode = "NULLABLE", description = "Company name" },
    { name = "sector", type = "STRING", mode = "NULLABLE", description = "Business sector (e.g., Banking, Telecom, Industry)" },
    { name = "activity_description", type = "STRING", mode = "NULLABLE", description = "Description of the company's activity" }
  ])

  clustering = ["sector"]

  labels = {
    source = "brvm"
    type   = "company_reference"
  }

  description = "BRVM listed companies with sector classification"
}

# Email notification channel for budget alerts
resource "google_monitoring_notification_channel" "email_alert" {
  project      = var.project_id
  display_name = "Cloud Run Budget Email Alert"
  type         = "email"

  labels = {
    email_address = "issacamara20@gmail.com" # Replace with your email address
  }
}


resource "google_billing_budget" "tradvisor_budget" {
  billing_account = var.billing_account_id # Format: "01XXXX-XXXXXX-XXXXXX"
  display_name    = "${var.project_id} - Cloud Run Budget Alert"

  # Scope budget specifically to this project & Cloud Run service
  budget_filter {
    projects = ["projects/${data.google_project.project.number}"]
    services = ["services/152E-C115-5142"] # GCP Service ID for Cloud Run
  }

  # Set target monthly spending cap (e.g., $10)
  amount {
    specified_amount {
      currency_code = "EUR"
      units         = "10"
    }
  }

  # --- THRESHOLD RULES ---

  # 1. Early Warning: Actual spend reaches 50% ($5)
  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }

  # 2. Early Warning: Actual spend reaches 80% ($8)
  threshold_rules {
    threshold_percent = 0.8
    spend_basis       = "CURRENT_SPEND"
  }

  # 3. Surge Defense (PROACTIVE): Forecasted spend will reach 100% ($10)
  # Fires as soon as GCP algorithms detect an abnormal spike heading toward your limit
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  # Link notification channel
  all_updates_rule {
    monitoring_notification_channels = [
      google_monitoring_notification_channel.email_alert.id
    ]
  }
}