output "function_uri" {
  value = [for f in google_cloudfunctions2_function.functions : f.service_config[0].uri]
}

output "project_number" {
  value = data.google_project.project.number
}

output "service_account_private_key" {
  value     = google_service_account_key.tradvisor_sa_key.private_key
  sensitive = true
}
