variable "configure_v1_identity" {
  description = "Opt in to configuring development email/password sign-in after reviewing current identity settings"
  type        = bool
  default     = false
}

variable "v1_identity_authorized_domains" {
  description = "Verified development redirect domains: localhost, 127.0.0.1, or the configured development Firebase domains"
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for domain in var.v1_identity_authorized_domains :
      domain == "localhost" ||
      domain == "127.0.0.1" ||
      domain == "${var.project_id}.web.app" ||
      domain == "${var.project_id}.firebaseapp.com"
    ])
    error_message = "Identity redirect domains must be local or belong to the configured development Firebase project."
  }
}

# Sign-in establishes identity only. Backend verified-email and manual allowlist
# checks remain the application admission boundary.
resource "google_identity_platform_config" "v1_development" {
  count              = var.configure_v1_identity ? 1 : 0
  project            = var.project_id
  authorized_domains = var.v1_identity_authorized_domains

  sign_in {
    email {
      enabled           = true
      password_required = true
    }
  }

  lifecycle {
    precondition {
      condition     = var.project_id == "dev-tradvisor"
      error_message = "V1 identity configuration is restricted to the configured development project."
    }

    precondition {
      condition     = length(var.v1_identity_authorized_domains) > 0
      error_message = "Set verified development identity domains before enabling this configuration."
    }
  }
}
