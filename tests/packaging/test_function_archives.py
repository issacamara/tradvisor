"""Offline checks for reusable ingestion function archive contents."""

from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "archive" / "legacy-ingestion" / "scripts"
TERRAFORM = ROOT / "terraform"


def test_each_registered_function_has_a_source_and_runtime() -> None:
    variables = (TERRAFORM / "variables.tf").read_text()
    functions = re.search(r'variable "functions"\s*\{(.*?)\n\}', variables, re.S)
    runtimes = re.search(r'variable "function_runtimes"\s*\{(.*?)\n\}', variables, re.S)
    assert functions is not None and runtimes is not None
    names = re.findall(r'"([a-z_]+)"', functions.group(1))
    runtime_names = set(re.findall(r'^\s*([a-z_]+)\s*=\s*"python[0-9]+"', runtimes.group(1), re.M))
    assert names
    for name in names:
        assert (SCRIPTS / f"{name}.py").is_file()
        assert name in runtime_names


def test_archive_includes_common_resources_and_declared_local_modules() -> None:
    buckets = (TERRAFORM / "buckets.tf").read_text()
    variables = (TERRAFORM / "variables.tf").read_text()
    assert 'filename = "main.py"' in buckets
    assert 'filename = "helper.py"' in buckets
    assert 'filename = "config.yml"' in buckets
    assert 'filename = "requirements.txt"' in buckets
    assert 'lookup(var.function_local_files, each.key, [])' in buckets
    assert 'insert_shares = ["scrape_shares.py"]' in variables

    source = ast.parse((SCRIPTS / "insert_shares.py").read_text())
    imported_local = {
        node.module
        for node in ast.walk(source)
        if isinstance(node, ast.ImportFrom) and node.module == "scrape_shares"
    }
    assert imported_local == {"scrape_shares"}
    assert (SCRIPTS / "scrape_shares.py").is_file()


def test_packaging_keeps_credentials_as_references_and_resources_preserved() -> None:
    buckets = (TERRAFORM / "buckets.tf").read_text()
    functions = (TERRAFORM / "functions.tf").read_text()
    iam = (TERRAFORM / "iam.tf").read_text()
    variables = (TERRAFORM / "variables.tf").read_text()

    assert "secret_data" not in buckets
    assert "google_service_account.tradvisor_sa.email" in functions
    assert "google_service_account_key.tradvisor_sa_key" in iam
    assert 'default     = false' in variables[variables.index('variable "manage_legacy_source_objects"'):]
    assert "prevent_destroy = true" in buckets
