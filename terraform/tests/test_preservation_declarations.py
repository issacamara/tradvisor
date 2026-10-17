"""Offline regression checks for the V1 preservation-only Terraform contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import unittest


TERRAFORM_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TERRAFORM_DIR.parent


def _table_block(configuration: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "google_bigquery_table" "{resource_name}" \{{(.*?)\n\}}',
        configuration,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing BigQuery table resource {resource_name}")
    return match.group(1)


def _table_schema(block: str) -> list[dict[str, str]]:
    match = re.search(r"schema\s*=\s*jsonencode\((\[.*?\])\)", block, re.DOTALL)
    if match is None:
        raise AssertionError("BigQuery table resource is missing a schema")
    schema = re.sub(r"(name|type|mode)\s*=", r'"\1":', match.group(1))
    return json.loads(re.sub(r",(\s*\])", r"\1", schema))


def _share_writer_columns() -> tuple[str, ...]:
    tree = ast.parse((REPOSITORY_ROOT / "functions/shares/insert_shares.py").read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "MARKET_COLUMNS" for target in node.targets)
        ):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("share writer MARKET_COLUMNS contract is missing")


def _financial_writer_columns() -> tuple[str, ...]:
    source = (REPOSITORY_ROOT / "functions/financials/insert_financials.py").read_text()
    match = re.search(r"df\s*=\s*pd\.DataFrame\(\[\{(.*?)\}\]\)", source, re.DOTALL)
    if match is None:
        raise AssertionError("financial writer DataFrame contract is missing")
    return tuple(re.findall(r"['\"]([a-z_]+)['\"]\s*:", match.group(1)))


class PreservationDeclarationTests(unittest.TestCase):
    def test_run_scoped_staging_tables_are_declared_and_protected(self) -> None:
        configuration = (TERRAFORM_DIR / "main.tf").read_text()
        expected = {
            "shares_staging": ("shares_staging", _share_writer_columns()),
            "financials_staging": ("financials_staging", _financial_writer_columns()),
        }

        for resource_name, (table_id, writer_columns) in expected.items():
            with self.subTest(resource=resource_name):
                block = _table_block(configuration, resource_name)
                schema = _table_schema(block)
                schema_columns = tuple(field["name"] for field in schema)

                self.assertIn(f'table_id            = "{table_id}"', block)
                self.assertIn("deletion_protection = true", block)
                self.assertIn("lifecycle { prevent_destroy = true }", block)
                self.assertCountEqual(schema_columns, ("run_id", *writer_columns))
                self.assertEqual(schema[0], {"name": "run_id", "type": "STRING", "mode": "REQUIRED"})
                self.assertIn('clustering          = ["run_id", "symbol"]', block)

    def test_staging_payload_columns_match_the_canonical_merge_contract(self) -> None:
        configuration = (TERRAFORM_DIR / "main.tf").read_text()
        for canonical, staging in (("shares", "shares_staging"), ("financials", "financials_staging")):
            with self.subTest(canonical=canonical):
                canonical_schema = _table_schema(_table_block(configuration, canonical))
                staging_schema = _table_schema(_table_block(configuration, staging))
                self.assertEqual(staging_schema[1:], canonical_schema)

    def test_remaining_legacy_ownership_is_opt_in(self) -> None:
        variables = (TERRAFORM_DIR / "variables.tf").read_text()
        main = (TERRAFORM_DIR / "main.tf").read_text()
        iam = (TERRAFORM_DIR / "iam.tf").read_text()
        functions = (TERRAFORM_DIR / "functions.tf").read_text()
        outputs = (TERRAFORM_DIR / "outputs.tf").read_text()

        ownership_controls = {
            "manage_legacy_schedules": functions,
            "manage_legacy_project_services": main,
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
        self.assertIn(
            "object = google_storage_bucket_object.new-function-src-code[each.key].name",
            functions,
        )
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
