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
variable "functions" {
  description = "List of function names"
  type        = list(string)
  default = ["scrape_shares", "scrape_bonds", "scrape_dividends", "scrape_capitalizations",
  "insert_shares", "insert_bonds", "insert_dividends", "insert_capitalizations"]
}

variable "function_runtimes" {
  description = "Deployed runtime preserved for each legacy Gen 2 function"
  type        = map(string)
  default = {
    scrape_shares          = "python311"
    scrape_bonds           = "python39"
    scrape_dividends       = "python311"
    scrape_capitalizations = "python39"
    insert_shares          = "python311"
    insert_bonds           = "python39"
    insert_dividends       = "python311"
    insert_capitalizations = "python39"
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
    "bigquery.googleapis.com", "workflows.googleapis.com", "cloudscheduler.googleapis.com",
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
    job2 = { name = "bonds", schedule = "0 20 1 * *" }
    job3 = { name = "dividends", schedule = "0 20 1 * *" }
    job4 = { name = "capitalizations", schedule = "0 20 1 7 *" }
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

variable "v1_api_image" {
  description = "Immutable development-only API image reference"
  type        = string
  default     = ""

  validation {
    condition     = var.v1_api_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.v1_api_image))
    error_message = "The V1 API image must be pinned by sha256 digest."
  }
}

variable "v1_job_image" {
  description = "Immutable development-only bounded job image reference"
  type        = string
  default     = ""

  validation {
    condition     = var.v1_job_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.v1_job_image))
    error_message = "The V1 job image must be pinned by sha256 digest."
  }
}

variable "v1_cursor_secret_id" {
  description = "Existing development Secret Manager secret ID used to sign private cursors"
  type        = string
  default     = ""

  validation {
    condition     = var.v1_cursor_secret_id == "" || can(regex("^[A-Za-z0-9_-]{1,255}$", var.v1_cursor_secret_id))
    error_message = "The cursor secret must be an existing Secret Manager secret ID."
  }
}
