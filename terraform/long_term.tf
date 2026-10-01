locals {
  v1_financial_precompute_enabled = (
    var.configure_v1_runtime &&
    var.v1_financials_table != "" &&
    var.v1_analytical_financials_table != ""
  )
}

resource "google_bigquery_data_transfer_config" "v1_financial_precompute" {
  count                = local.v1_financial_precompute_enabled ? 1 : 0
  project              = var.project_id
  location             = "US"
  display_name         = "tradvisor-v1-financial-precompute"
  data_source_id       = "scheduled_query"
  schedule             = "every 24 hours"
  service_account_name = google_service_account.v1_runtime[0].email
  params = {
    query = <<-SQL
      CREATE OR REPLACE TABLE `${var.v1_analytical_financials_table}`
      PARTITION BY DATE(fiscal_year, 12, 31)
      CLUSTER BY symbol AS
      SELECT symbol, fiscal_year, revenue, net_income, total_debt,
             cash_and_cash_equivalents, total_equity, collected_at, document_link
      FROM `${var.v1_financials_table}`
      WHERE fiscal_year IS NOT NULL
      QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) <= 3
    SQL
  }
}
