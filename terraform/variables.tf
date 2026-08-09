variable "project_id" {
  description = "Id of the project"
  type        = string
  default     = "prod-tradvisor"
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

variable "apis" {
  description = "List of apis"
  type        = list(string)
  default = ["cloudresourcemanager.googleapis.com", "run.googleapis.com", "cloudfunctions.googleapis.com", "cloudbuild.googleapis.com",
              "bigquery.googleapis.com", "workflows.googleapis.com", "cloudscheduler.googleapis.com",
              "run.googleapis.com", "iam.googleapis.com","secretmanager.googleapis.com", "artifactregistry.googleapis.com"]
}

variable "jobs" {
  type = map(object({
    name     = string
    schedule = string
  }))
  default = {
    job1 = { name = "shares", schedule = "0 20 * * 1-5" }
    # job2 = { name = "bonds", schedule = "0 20 1 * *" }  # Disabled
    job3 = { name = "dividends", schedule = "0 20 1 * *" }
    job4 = { name = "capitalizations", schedule = "0 20 1 7 *" }
    job5 = { name = "financials", schedule = "0 6 1 * *" }    # First day of month at 6am
    job6 = { name = "ratings", schedule = "0 6 5 * *" }        # Fifth day of month at 6am
  }
}

variable "docker_image" {
  description = "Docker image URL on DockerHub (username/repo:tag)"
  type        = string
  default     = "issacamara/tradvisor:latest"
}

variable "tradvisor_gmail_acc" {
  description = "Gmail account for sending alerts (JSON: {SMTP_USERNAME: email, SMTP_PASSWORD: password})"
  type = object({
    SMTP_USERNAME = string
    SMTP_PASSWORD = string
  })
  sensitive   = true
}

variable "openrouter_api_key" {
  description = "OpenRouter API key for extracting financial data from PDFs"
  type        = string
  sensitive   = true
}

variable "auth_disabled" {
  description = "Disable authentication for development/testing (set to 'true' for dev, 'false' for prod)"
  type        = string
  default     = "false"
}

variable "environment" {
  description = "Environment name (dev or prod) - used for display in Settings page"
  type        = string
  default     = "prod"
}