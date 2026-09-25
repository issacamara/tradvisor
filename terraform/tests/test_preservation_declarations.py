"""Offline regression checks for the V1 preservation-only Terraform contract."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


TERRAFORM_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TERRAFORM_DIR.parent


class PreservationDeclarationTests(unittest.TestCase):
    def test_remaining_legacy_ownership_is_opt_in(self) -> None:
        variables = (TERRAFORM_DIR / "variables.tf").read_text()
        main = (TERRAFORM_DIR / "main.tf").read_text()
        iam = (TERRAFORM_DIR / "iam.tf").read_text()
        functions = (TERRAFORM_DIR / "functions.tf").read_text()
        outputs = (TERRAFORM_DIR / "outputs.tf").read_text()

        ownership_controls = {
            "manage_legacy_schedules": functions,
            "manage_legacy_project_services": main,
            "manage_legacy_iam_bindings": iam,
            "manage_legacy_bigquery_datasets": main,
            "manage_legacy_service_account_credentials": iam,
        }
        for control, declaration_file in ownership_controls.items():
            with self.subTest(control=control):
                self.assertRegex(
                    variables,
                    rf'variable "{control}"\s*\{{[^}}]*default\s*=\s*false',
                )
                self.assertIn(f"var.{control}", declaration_file)
                self.assertIn("explicitly approved ownership migration", variables)

        self.assertIn("var.manage_legacy_schedules ? var.jobs : {}", functions)
        self.assertIn(
            "var.manage_legacy_project_services ? toset(var.apis) : toset([])",
            main,
        )
        self.assertIn(
            "count                      = var.manage_legacy_bigquery_datasets ? 1 : 0",
            main,
        )
        self.assertEqual(
            iam.count("count      = var.manage_legacy_iam_bindings ? 1 : 0"),
            13,
        )
        self.assertEqual(
            iam.count(
                "count              = var.manage_legacy_service_account_credentials ? 1 : 0"
            )
            + iam.count(
                "count     = var.manage_legacy_service_account_credentials ? 1 : 0"
            )
            + iam.count(
                "count       = var.manage_legacy_service_account_credentials ? 1 : 0"
            ),
            3,
        )
        self.assertIn(
            "var.manage_legacy_service_account_credentials ? google_service_account_key.tradvisor_sa_key[0].private_key : null",
            outputs,
        )

    def test_existing_preservation_controls_remain_default_off(self) -> None:
        variables = (TERRAFORM_DIR / "variables.tf").read_text()
        functions = (TERRAFORM_DIR / "functions.tf").read_text()

        for control in (
            "manage_legacy_source_objects",
            "manage_legacy_workflows",
        ):
            with self.subTest(control=control):
                self.assertRegex(
                    variables,
                    rf'variable "{control}"\s*\{{[^}}]*default\s*=\s*false',
                )
        self.assertIn(
            "var.manage_legacy_source_objects ? toset(var.functions) : toset([])",
            (TERRAFORM_DIR / "buckets.tf").read_text(),
        )
        self.assertIn(
            "count           = var.manage_legacy_workflows ? length(var.functions) / 2 : 0",
            functions,
        )

    def test_legacy_source_objects_are_opt_in(self) -> None:
        variables = (TERRAFORM_DIR / "variables.tf").read_text()
        buckets = (TERRAFORM_DIR / "buckets.tf").read_text()
        functions = (TERRAFORM_DIR / "functions.tf").read_text()

        self.assertRegex(
            variables,
            r'variable "manage_legacy_source_objects"\s*\{[^}]*default\s*=\s*false',
        )
        guard = (
            "var.manage_legacy_source_objects ? "
            "toset(var.functions) : toset([])"
        )
        self.assertEqual(buckets.count(guard), 3)
        self.assertIn('name       = "${each.key}.zip"', buckets)
        self.assertIn('object = "${each.key}.zip"', functions)
        self.assertNotIn(
            "google_storage_bucket_object.src-code[each.key].name",
            functions,
        )

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
