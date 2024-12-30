output "function_uri" {
  value = google_cloudfunctions2_function.scrape-shares.service_config[0].uri
}

output "project_number" {
  value = data.google_project.project.number
}