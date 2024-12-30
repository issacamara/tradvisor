terraform {
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


data "archive_file" "scrape_shares" {
  type        = "zip"
  output_path = "scrape_brvm_shares.zip"

  source {
    content  = file("../scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("../scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("../scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("../scripts/scrape_brvm_shares.py")
    filename = "main.py"
  }
}

data "archive_file" "insert_shares" {
  type        = "zip"
  output_path = "insert_shares.zip"

  source {
    content  = file("../scripts/helper.py")
    filename = "helper.py"
  }
  source {
    content  = file("../scripts/config.yml")
    filename = "config.yml"
  }
  source {
    content  = file("../scripts/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("../scripts/insert_shares.py")
    filename = "main.py"
  }
}


# resource "google_project_service" "cloud_run" {
#   project = var.project_id
#   service = "run.googleapis.com"
# }
# resource "google_project_service" "cloudfunctions" {
#   project = var.project_id
#   service = "cloudfunctions.googleapis.com"
# }
# # Enable the Cloud Build API
# resource "google_project_service" "cloud_build" {
#   project = var.project_id
#   service = "cloudbuild.googleapis.com"
# }
# # Enable the BigQuery API
# resource "google_project_service" "bigquery" {
#   project = var.project_id
#   service = "bigquery.googleapis.com"
# }
# resource "google_project_service" "workflows" {
#   project = var.project_id
#   service = "workflows.googleapis.com"
# }
# resource "google_project_service" "scheduler" {
#   project = var.project_id
#   service = "scheduler.googleapis.com"
# }


resource "google_cloudfunctions2_function" "scrape-shares" {
  name        = "scrape_shares_function"
  location    = var.region
  description = "This function scrapes shares from BRVM"
  build_config {
    runtime     = "python39"
    entry_point = "entry_point" # Set the entry point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.scrape_shares.name
      }
    }
  }
  service_config {
    max_instance_count = 1
    available_memory   = "256M"
    timeout_seconds    = 120
    service_account_email = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  }

}

resource "google_cloudfunctions2_function" "insert-shares" {
  name        = "insert_shares_function"
  location    = var.region
  description = "This function inserts shares to BigQuery"
  build_config {
    runtime     = "python39"
    entry_point = "entry_point" # Set the entry point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.insert_shares.name
      }
    }
  }
  service_config {
    max_instance_count = 1
    available_memory   = "512M"
    timeout_seconds    = 120
    service_account_email = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  }

}

resource "google_bigquery_dataset" "stocks" {
  dataset_id = "stocks"
  location    = var.region
  delete_contents_on_destroy = true
}

resource "google_workflows_workflow" "share-workflow" {
  name     = "share-workflow"

  description = "A workflow to run two cloud functions sequentially"

#   source_contents = file("../scripts/workflow.yml")

  service_account = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
#   service_account = "projects/${data.google_project.project.number}/serviceAccounts/${data.google_project.project.number}-compute@developer.gserviceaccount.com"

  source_contents =  <<EOF
- scrape-shares:
    call: http.get
    args:
      url: ${google_cloudfunctions2_function.scrape-shares.url}
      auth:
        type: OIDC
        audience: ${google_cloudfunctions2_function.scrape-shares.url}

- insert-shares:
    call: http.get
    args:
      url: ${google_cloudfunctions2_function.insert-shares.url}
      auth:
        type: OIDC
        audience: ${google_cloudfunctions2_function.insert-shares.url}
EOF
}

# Step 4: Create a Scheduler Job to trigger the Workflow daily at 8 PM Bamako time
resource "google_cloud_scheduler_job" "shares-job" {
  name        = "shares-job"
  description = "A job to trigger the workflow daily at 8 PM Bamako time"
  schedule    = "0 20 * * *"
  time_zone   = "Africa/Bamako"

  http_target {
    http_method = "POST"
    uri = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${google_workflows_workflow.share-workflow.name}/executions"

    oidc_token {
      service_account_email = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
    }
  }
}

data "google_project" "project" {}

