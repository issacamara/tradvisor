"""Contract tests for the packaged ingestion configuration boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


CONFIGURATION = (
    Path(__file__).resolve().parents[2]
    / "archive"
    / "legacy-ingestion"
    / "scripts"
    / "ingestion_configuration.py"
)


def _module():
    specification = importlib.util.spec_from_file_location(
        "ingestion_configuration_contract", CONFIGURATION
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _environment() -> dict[str, str]:
    values = {
        "TRADVISOR_RUNTIME_TARGET": "ingestion",
        "TRADVISOR_ENVIRONMENT": "development",
        "GOOGLE_CLOUD_PROJECT": "fixture-project",
        "TRADVISOR_TARGET_PROJECT_ID": "fixture-project",
        "TRADVISOR_ENVIRONMENT_PROJECT_ID": "fixture-project",
        "TRADVISOR_INGESTION_SERVICE_ACCOUNT": "fixture-ingestion@fixture-project.iam.gserviceaccount.com",
        "TRADVISOR_INGESTION_DATA_BUCKET": "fixture-data-bucket",
        "TRADVISOR_INGESTION_ARCHIVE_BUCKET": "fixture-archive-bucket",
        "TRADVISOR_INGESTION_DATASET": "stocks",
    }
    for asset in ("companies", "shares", "dividends", "financials", "ratings"):
        values[f"TRADVISOR_INGESTION_{asset.upper()}_TABLE"] = (
            f"fixture-project.stocks.{asset}"
        )
    endpoints = {
        "SHARES": "https://source.example.test/shares",
        "BRVM_SESSION": "https://source.example.test/sessions",
        "BONDS": "https://source.example.test/bonds",
        "CAPITALIZATIONS": "https://source.example.test/capitalizations",
        "VOLUMES": "https://source.example.test/volumes",
        "INDICES": "https://source.example.test/indices",
        "DIVIDENDS": "https://source.example.test/dividends",
        "FINANCIALS": "https://source.example.test/financials",
        "RATINGS": "https://source.example.test/ratings",
        "COMPANY_LISTING": "https://source.example.test/companies",
    }
    values.update({f"TRADVISOR_INGESTION_SOURCE_{name}_URL": url for name, url in endpoints.items()})
    return values


def test_explicit_configuration_exposes_only_project_bound_targets() -> None:
    module = _module()

    configuration = module.IngestionConfiguration.from_environment(_environment())

    assert configuration.data_bucket == "fixture-data-bucket"
    assert configuration.archive_bucket == "fixture-archive-bucket"
    assert configuration.table_for("financials") == "fixture-project.stocks.financials"
    assert configuration.endpoint_for("shares") == "https://source.example.test/shares"


def test_mismatched_project_fails_before_a_provider_client_can_be_created() -> None:
    module = _module()
    values = _environment()
    values["TRADVISOR_TARGET_PROJECT_ID"] = "other-project"

    with pytest.raises(module.IngestionConfigurationError, match="environment target"):
        module.IngestionConfiguration.from_environment(values)


def test_adc_project_drift_is_rejected_before_storage_or_bigquery_client_creation() -> None:
    module = _module()
    configuration = module.IngestionConfiguration.from_environment(_environment())

    with pytest.raises(module.IngestionConfigurationError, match="does not match"):
        configuration.validate_application_default_project("other-project")


def test_source_endpoints_require_explicit_safe_https_targets() -> None:
    module = _module()
    values = _environment()
    values["TRADVISOR_INGESTION_SOURCE_RATINGS_URL"] = "http://source.example.test/ratings"

    with pytest.raises(module.IngestionConfigurationError, match="RATINGS"):
        module.IngestionConfiguration.from_environment(values)
