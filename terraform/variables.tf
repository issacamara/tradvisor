variable "project_id" {
  description = "Id of the project"
  type        = string
  default     = "dev-tradvisor"
  #   default     = "sbx-31371-uw1yf3stmtx5c52rawmo"
}
variable "region" {
  description = "Region of the project"
  type        = string
  default     = "europe-central2"
}

variable "recovery_register_cleanup_members" {
  description = "Explicit principals allowed to delete recovery-register objects after evidence-qualified cleanup; empty by default"
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for member in var.recovery_register_cleanup_members :
      can(regex("^(user|group|serviceAccount):", member))
    ])
    error_message = "Cleanup principals must use a user:, group:, or serviceAccount: member identity."
  }
}

variable "functions" {
  description = "List of function names"
  type        = list(string)
  default = ["scrape_shares", "scrape_dividends", "insert_shares", "insert_dividends",
  "scrape_financials", "insert_financials", "scrape_ratings", "insert_ratings"]
}

variable "initialization_functions" {
  description = "One-time initialization functions retained from the production ingestion topology"
  type        = set(string)
  default     = ["scrape_financials_init", "scrape_ratings_init"]
}

variable "managed_function_sources" {
  description = "Function source archives managed by the V1 development deployment"
  type        = set(string)
  default = [
    "scrape_shares",
    "insert_shares",
    "scrape_dividends",
    "insert_dividends",
    "scrape_financials",
    "insert_financials",
    "scrape_ratings",
    "insert_ratings",
  ]
}

variable "manage_new_function_sources" {
  description = "Whether Terraform may upload source archives for newly managed ingestion functions"
  type        = bool
  default     = false
}

variable "function_runtimes" {
  description = "Deployed runtime preserved for each legacy Gen 2 function"
  type        = map(string)
  default = {
    scrape_shares          = "python311"
    scrape_dividends       = "python311"
    insert_shares          = "python311"
    insert_dividends       = "python311"
    scrape_financials      = "python311"
    insert_financials      = "python311"
    scrape_financials_init = "python311"
    scrape_ratings         = "python311"
    insert_ratings         = "python311"
    scrape_ratings_init    = "python311"
  }
}

variable "function_local_files" {
  description = "Local Python modules and data files required by each existing function artifact"
  type        = map(list(string))
  default = {
    insert_shares          = ["scrape_shares.py"]
    scrape_financials      = ["insert_financials.py", "scrape_financials_init.py"]
    insert_financials      = ["financial_normalization.py"]
    scrape_financials_init = ["company_reference.py", "insert_financials.py"]
    scrape_ratings_init    = ["scrape_ratings.py"]
  }
}

variable "manage_legacy_source_objects" {
  description = "Whether Terraform manages legacy function source archives and storage objects"
  type        = bool
  default     = false
}

variable "apis" {
  description = "List of apis"
  type        = list(string)
  default = ["run.googleapis.com", "cloudfunctions.googleapis.com", "cloudbuild.googleapis.com",
    "bigquery.googleapis.com", "workflows.googleapis.com", "cloudscheduler.googleapis.com", "cloudtasks.googleapis.com",
    "run.googleapis.com", "iam.googleapis.com", "secretmanager.googleapis.com",
  "cloudresourcemanager.googleapis.com"]
}

variable "jobs" {
  type = map(object({
    name     = string
    schedule = string
  }))
  default = {
    job1 = { name = "shares", schedule = "0 20 * * 1-5" }
    job3 = { name = "dividends", schedule = "0 20 1 * *" }
    job5 = { name = "financials", schedule = "0 20 1 * *" }
    job6 = { name = "ratings", schedule = "0 20 1 * *" }
  }
}

variable "manage_legacy_workflows" {
  description = "Whether Terraform owns the pre-existing legacy workflows"
  type        = bool
  default     = false
}

variable "manage_legacy_schedules" {
  description = "Whether Terraform owns pre-existing legacy schedules; enabling requires an explicitly approved ownership migration"
  type        = bool
  default     = false
}

variable "manage_legacy_project_services" {
  description = "Whether Terraform owns pre-existing project service enablement; enabling requires an explicitly approved ownership migration"
  type        = bool
  default     = false
}

variable "manage_legacy_bigquery_datasets" {
  description = "Whether Terraform owns pre-existing BigQuery datasets; enabling requires an explicitly approved ownership migration"
  type        = bool
  default     = false
}

variable "manage_legacy_service_account_credentials" {
  description = "Whether Terraform owns pre-existing service-account credentials and secret resources; enabling requires an explicitly approved ownership migration"
  type        = bool
  default     = false
}

variable "configure_v1_runtime" {
  description = "Opt in to the development-only V1 Cloud Run API and bounded batch job definitions"
  type        = bool
  default     = false
}

variable "configure_v1_api" {
  description = "Opt in to the development-only V1 Cloud Run API without creating the batch job"
  type        = bool
  default     = false
}

variable "configure_v1_monitoring" {
  description = "Opt in to development-only bounded V1 log retention and alert policies"
  type        = bool
  default     = false
}

variable "v1_log_retention_days" {
  description = "Finite retention for V1 application logs"
  type        = number
  default     = 30

  validation {
    condition     = var.v1_log_retention_days >= 1 && var.v1_log_retention_days <= 90
    error_message = "V1 log retention must be between 1 and 90 days."
  }
}

variable "v1_monitoring_check_interval_seconds" {
  description = "Finite interval for V1 freshness and failure checks"
  type        = number
  default     = 900

  validation {
    condition     = var.v1_monitoring_check_interval_seconds >= 300 && var.v1_monitoring_check_interval_seconds <= 86400
    error_message = "V1 monitoring checks must run between five minutes and one day apart."
  }
}

variable "v1_runtime_service_account_id" {
  description = "Dedicated service account ID for the opt-in V1 runtime"
  type        = string
  default     = "tradvisor-v1-api"
}

variable "v1_cursor_secret_id" {
  description = "Metadata-only secret name referenced by the V1 runtime for cursor signing"
  type        = string
  default     = "tradvisor-v1-cursor-secret"
}

variable "v1_api_service_name" {
  description = "Development-only Cloud Run API service name"
  type        = string
  default     = "tradvisor-v1-api"
}

variable "v1_api_image" {
  description = "Approved development container image for the V1 API; required when runtime configuration is enabled"
  type        = string
  default     = ""
}

variable "v1_api_timeout_seconds" {
  description = "Bounded request timeout for the V1 API"
  type        = number
  default     = 60

  validation {
    condition     = var.v1_api_timeout_seconds >= 1 && var.v1_api_timeout_seconds <= 300
    error_message = "V1 API timeout must be between 1 and 300 seconds."
  }
}

variable "v1_api_max_instance_count" {
  description = "Bounded maximum API instance count"
  type        = number
  default     = 1

  validation {
    condition     = var.v1_api_max_instance_count >= 1 && var.v1_api_max_instance_count <= 10
    error_message = "V1 API max instances must be between 1 and 10."
  }
}

variable "v1_api_max_request_concurrency" {
  description = "Bounded maximum concurrent requests per API instance"
  type        = number
  default     = 20

  validation {
    condition     = var.v1_api_max_request_concurrency >= 1 && var.v1_api_max_request_concurrency <= 80
    error_message = "V1 API request concurrency must be between 1 and 80."
  }
}

variable "v1_batch_job_name" {
  description = "Development-only Cloud Run Job name for bounded analysis work"
  type        = string
  default     = "tradvisor-v1-batch"
}

variable "v1_batch_image" {
  description = "Approved development container image for bounded V1 jobs; required when runtime configuration is enabled"
  type        = string
  default     = ""
}

variable "v1_batch_command" {
  description = "Explicit bounded job command; required when runtime configuration is enabled"
  type        = list(string)
  default     = []
}

variable "v1_analytical_snapshot_table" {
  description = "Development-only BigQuery table containing published analytical snapshot envelopes"
  type        = string
  default     = ""

  validation {
    condition     = var.v1_analytical_snapshot_table == "" || can(regex("^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$", var.v1_analytical_snapshot_table))
    error_message = "The analytical snapshot table must be project.dataset.table."
  }
}

variable "v1_analytical_snapshot_name" {
  description = "Development-only named analytical snapshot selected by the manual Cloud Run Job"
  type        = string
  default     = ""
}

variable "v1_financials_table" {
  description = "Development-only raw financials table used by the bounded daily precompute"
  type        = string
  default     = ""
  validation {
    condition     = var.v1_financials_table == "" || can(regex("^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$", var.v1_financials_table))
    error_message = "The financials table must be project.dataset.table."
  }
}

variable "v1_analytical_financials_table" {
  description = "Development-only partitioned table containing the latest three financial years per symbol"
  type        = string
  default     = ""
  validation {
    condition     = var.v1_analytical_financials_table == "" || can(regex("^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$", var.v1_analytical_financials_table))
    error_message = "The analytical financials table must be project.dataset.table."
  }
}

variable "v1_batch_timeout_seconds" {
  description = "Bounded timeout for each V1 batch task"
  type        = number
  default     = 900

  validation {
    condition     = var.v1_batch_timeout_seconds >= 1 && var.v1_batch_timeout_seconds <= 3600
    error_message = "V1 batch timeout must be between 1 and 3600 seconds."
  }
}

variable "v1_batch_max_retries" {
  description = "Finite retry count for each V1 batch task"
  type        = number
  default     = 2

  validation {
    condition     = var.v1_batch_max_retries >= 0 && var.v1_batch_max_retries <= 5
    error_message = "V1 batch retries must be between 0 and 5."
  }
}
