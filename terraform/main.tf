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
  project = var.project_id
  region  = var.region
}

resource "google_bigquery_dataset" "stocks" {
  dataset_id                 = "stocks"
  location                   = var.region
  delete_contents_on_destroy = true
  depends_on                 = [google_project_service.apis]
}

resource "google_project_service" "apis" {
  project                    = var.project_id
  for_each                   = toset(var.apis)
  service                    = each.key
  disable_dependent_services = true
}


data "google_project" "project" {}
