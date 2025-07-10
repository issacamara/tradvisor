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

variable "apis" {
  description = "List of apis"
  type        = list(string)
  default = ["run.googleapis.com", "cloudfunctions.googleapis.com", "cloudbuild.googleapis.com",
              "bigquery.googleapis.com", "workflows.googleapis.com", "cloudscheduler.googleapis.com",
              "run.googleapis.com", "iam.googleapis.com","secretmanager.googleapis.com",
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

variable "docker_image" {
  description = "Docker image URL on DockerHub (username/repo:tag)"
  type        = string
  default     = "issacamara/tradvisor:latest"
}