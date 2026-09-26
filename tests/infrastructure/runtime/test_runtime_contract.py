from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]


class RuntimeContractTests(unittest.TestCase):
    def test_api_scales_to_zero_and_caps_requests(self) -> None:
        runtime = (ROOT / "terraform/runtime.tf").read_text()
        self.assertIn('resource "google_cloud_run_v2_service" "v1_api"', runtime)
        self.assertIn("min_instance_count = 0", runtime)
        self.assertIn("max_instance_count = 3", runtime)
        self.assertIn('timeout                          = "60s"', runtime)
        self.assertIn("max_instance_request_concurrency = 40", runtime)

    def test_job_has_finite_task_and_retry_limits(self) -> None:
        runtime = (ROOT / "terraform/runtime.tf").read_text()
        self.assertIn('resource "google_cloud_run_v2_job" "v1_bounded_job"', runtime)
        self.assertIn("task_count  = 1", runtime)
        self.assertIn("parallelism = 1", runtime)
        self.assertIn("max_retries     = 1", runtime)
        self.assertIn('timeout         = "900s"', runtime)

    def test_runtime_requires_immutable_images_and_development_project(self) -> None:
        variables = (ROOT / "terraform/variables.tf").read_text()
        runtime = (ROOT / "terraform/runtime.tf").read_text()
        self.assertEqual(variables.count('can(regex("@sha256:[0-9a-f]{64}$"'), 2)
        self.assertGreaterEqual(runtime.count('var.project_id == "dev-tradvisor"'), 2)
        self.assertNotRegex(runtime, r"(?m)\s*schedule\s*=")

    def test_new_identity_does_not_use_legacy_reconciliating_bindings(self) -> None:
        runtime = (ROOT / "terraform/runtime.tf").read_text()
        self.assertIn('resource "google_project_iam_member" "v1_runtime_firestore"', runtime)
        self.assertIn('resource "google_secret_manager_secret_iam_member"', runtime)
        self.assertNotIn("google_project_iam_binding", runtime)


if __name__ == "__main__":
    unittest.main()
