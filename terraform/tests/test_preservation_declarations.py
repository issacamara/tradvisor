"""Offline regression checks for the V1 preservation-only Terraform contract."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


TERRAFORM_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TERRAFORM_DIR.parent


class PreservationDeclarationTests(unittest.TestCase):
    def test_legacy_resources_are_not_force_destroyable(self) -> None:
        configuration = "\n".join(
            path.read_text() for path in TERRAFORM_DIR.glob("*.tf")
        )

        self.assertNotIn("force_destroy               = true", configuration)
        self.assertNotIn("delete_contents_on_destroy = true", configuration)
        self.assertNotIn("disable_dependent_services = true", configuration)
        self.assertNotIn("timestamp()", configuration)

    def test_preserved_resources_have_destroy_protection(self) -> None:
        configuration = "\n".join(
            path.read_text() for path in TERRAFORM_DIR.glob("*.tf")
        )

        self.assertGreaterEqual(configuration.count("prevent_destroy = true"), 10)
        self.assertIn("ignore_changes  = [keepers]", configuration)

    def test_legacy_iam_bindings_do_not_reconcile_memberships(self) -> None:
        iam = (TERRAFORM_DIR / "iam.tf").read_text()
        binding_count = len(re.findall(r'resource "google_project_iam_binding"', iam))

        self.assertEqual(binding_count, 13)
        self.assertEqual(iam.count("ignore_changes = [members]"), binding_count)

    def test_terraform_plan_artifacts_are_ignored(self) -> None:
        artifacts = (
            "terraform/approved.tfplan",
            "terraform/approved.tfplan.json",
            "terraform/tfplan",
            "terraform/tfplan.json",
            "terraform/approved.plan",
            "terraform/approved.plan.json",
        )

        for artifact in artifacts:
            result = subprocess.run(
                ["git", "-C", str(REPOSITORY_ROOT), "check-ignore", "--quiet", artifact],
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{artifact} must be ignored")

    def test_terraform_backend_configuration_files_are_ignored(self) -> None:
        backend_configs = (
            "terraform/backend.hcl",
            "terraform/backend.tfbackend",
            "terraform/private.backend.hcl",
            "terraform/backend-dev.tfbackend",
            "terraform/operator.backend.hcl",
        )

        for backend_config in backend_configs:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(REPOSITORY_ROOT),
                    "check-ignore",
                    "--quiet",
                    backend_config,
                ],
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"{backend_config} must be ignored",
            )


if __name__ == "__main__":
    unittest.main()
