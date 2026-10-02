locals {
  v1_shares_schema = [
    { name = "symbol", type = "STRING", mode = "REQUIRED" },
    { name = "session_date", type = "DATE", mode = "REQUIRED" },
    { name = "revision_id", type = "STRING", mode = "REQUIRED" },
    { name = "source_id", type = "STRING", mode = "REQUIRED" },
    { name = "source_observation_id", type = "STRING", mode = "REQUIRED" },
    { name = "source_revision_id", type = "STRING", mode = "REQUIRED" },
    { name = "session_date_status", type = "STRING", mode = "REQUIRED" },
    { name = "trade_status", type = "STRING", mode = "REQUIRED" },
    { name = "close", type = "NUMERIC", mode = "NULLABLE" },
    { name = "high", type = "NUMERIC", mode = "NULLABLE" },
    { name = "low", type = "NUMERIC", mode = "NULLABLE" },
    { name = "volume", type = "INT64", mode = "NULLABLE" },
    { name = "basis", type = "STRING", mode = "REQUIRED" },
    { name = "original_source_date", type = "DATE", mode = "REQUIRED" },
    { name = "price_basis_ref", type = "STRING", mode = "REQUIRED" },
    { name = "validated_available_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "actual_xof_turnover", type = "NUMERIC", mode = "NULLABLE" },
    { name = "liquidity_basis", type = "STRING", mode = "NULLABLE" },
    { name = "suspension_status", type = "STRING", mode = "REQUIRED" },
    { name = "reason_codes", type = "STRING", mode = "REPEATED" },
    { name = "source_published_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "collected_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "known_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "snapshot_uri", type = "STRING", mode = "NULLABLE" },
    { name = "snapshot_sha256", type = "STRING", mode = "NULLABLE" },
    { name = "parser_version", type = "STRING", mode = "REQUIRED" },
  ]
}

# The live V1 API and shares ingestion both use this lowercase canonical table.
resource "google_bigquery_table" "v1_shares" {
  count               = var.configure_v1_runtime ? 1 : 0
  project             = var.project_id
  dataset_id          = "stocks"
  table_id            = "shares"
  schema              = jsonencode(local.v1_shares_schema)
  deletion_protection = true
  clustering          = ["symbol"]

  time_partitioning {
    type  = "DAY"
    field = "session_date"
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = var.project_id == "dev-tradvisor"
      error_message = "V1 ingestion tables are restricted to the development project."
    }
  }

  depends_on = [google_bigquery_dataset.stocks]
}
