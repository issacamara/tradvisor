variable "project_id" {
  description = "Id of the project"
  type        = string
  default     = "sbx-31371-6tmkyf48crzuvr9197r7"
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
  "insert_shares", "insert_bonds", "update_dividends", "update_capitalizations"]
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