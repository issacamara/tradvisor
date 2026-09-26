"""Offline checks for the opt-in, development-only V1 runtime contract."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
TERRAFORM = ROOT / "terraform"


class RuntimeConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.variables = (TERRAFORM / "variables.tf").read_text()
        self.runtime = (TERRAFORM / "runtime.tf").read_text()
        self.dockerfile = (ROOT / "backend/Dockerfile").read_text()

    def test_runtime_is_opt_in_and_development_only(self) -> None:
        self.assertRegex(
            self.variables,
            r'variable "configure_v1_runtime"\s*\{[^}]*default\s*=\s*false',
        )
        self.assertIn("count        = local.v1_runtime_enabled ? 1 : 0", self.runtime)
        self.assertIn('condition     = var.project_id == "dev-tradvisor"', self.runtime)
        self.assertNotIn("prod-tradvisor", self.runtime)

    def test_api_scales_to_zero_and_is_bounded(self) -> None:
        self.assertIn("min_instance_count = 0", self.runtime)
        self.assertIn("max_instance_count = var.v1_api_max_instance_count", self.runtime)
        self.assertIn("max_instance_request_concurrency = var.v1_api_max_request_concurrency", self.runtime)
        self.assertIn('timeout         = "${var.v1_api_timeout_seconds}s"', self.runtime)
        self.assertIn("cpu_idle = true", self.runtime)
        self.assertRegex(self.variables, r'variable "v1_api_timeout_seconds"\s*\{')
        self.assertRegex(self.variables, r'variable "v1_api_max_instance_count"\s*\{')
        self.assertRegex(self.variables, r'variable "v1_api_max_request_concurrency"\s*\{')

    def test_api_invoker_is_opt_in_for_firebase_frontend(self) -> None:
        self.assertIn(
            'resource "google_cloud_run_v2_service_iam_member" "v1_api_public_invoker"',
            self.runtime,
        )
        self.assertIn('role     = "roles/run.invoker"', self.runtime)
        self.assertIn('member   = "allUsers"', self.runtime)
        self.assertIn("count    = local.v1_runtime_enabled ? 1 : 0", self.runtime)

    def test_batch_job_has_finite_timeout_and_retries(self) -> None:
        self.assertIn('resource "google_cloud_run_v2_job" "v1_batch"', self.runtime)
        self.assertRegex(self.runtime, r"max_retries\s*=\s*var\.v1_batch_max_retries")
        self.assertRegex(
            self.runtime,
            r'timeout\s*=\s*"\$\{var\.v1_batch_timeout_seconds\}s"',
        )
        self.assertIn("length(var.v1_batch_command) > 0", self.runtime)
        self.assertRegex(self.variables, r'variable "v1_batch_max_retries"\s*\{')

    def test_runtime_uses_dedicated_identity_and_metadata_only_secret(self) -> None:
        self.assertIn('resource "google_service_account" "v1_runtime"', self.runtime)
        self.assertIn('resource "google_secret_manager_secret" "v1_cursor"', self.runtime)
        self.assertIn('resource "google_secret_manager_secret_iam_member" "v1_runtime_cursor"', self.runtime)
        self.assertIn('secret_key_ref {', self.runtime)
        self.assertNotIn("secret_data", self.runtime)
        self.assertNotIn("private_key", self.runtime)
        self.assertIn("FIRESTORE_CURSOR_SECRET", self.runtime)
        self.assertNotIn('v1_runtime_logging', self.runtime)

    def test_container_listens_on_cloud_run_port(self) -> None:
        self.assertIn('container_port = 8080', self.runtime)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", self.dockerfile)
        self.assertRegex(self.dockerfile, r"--host\s+0\.0\.0\.0")
        self.assertRegex(self.dockerfile, r"--port\s+\$\{PORT\}")


if __name__ == "__main__":
    unittest.main()
