from __future__ import annotations

import builtins
from pathlib import Path
from typing import NoReturn

import pytest

from backend.configuration import (
    PublicationControlConfiguration,
    RuntimeConfiguration,
    RuntimeConfigurationError,
    WorkflowDispatchConfiguration,
)
from backend.app import _production_analysis_publisher
from backend.jobs.runtime import build_worker


ROOT = Path(__file__).resolve().parents[2]


def api_environment(target: str = "api") -> dict[str, str]:
    return {
        "TRADVISOR_RUNTIME_TARGET": target,
        "TRADVISOR_ENVIRONMENT": "development",
        "GOOGLE_CLOUD_PROJECT": "example-dev",
        "TRADVISOR_TARGET_PROJECT_ID": "example-dev",
        "TRADVISOR_ENVIRONMENT_PROJECT_ID": "example-dev",
        "GOOGLE_CLOUD_FIRESTORE_DATABASE": "(default)",
        "TRADVISOR_SERVING_TARGET": "firestore",
        "FIRESTORE_CURSOR_SECRET": "fixture-only-secret",
        "TRADVISOR_CORS_ORIGINS": "http://localhost:3000, https://investors.example.test",
        "WORKFLOW_REGION": "europe-central2",
        "MARKET_DATA_TABLE": "example-dev.stocks.shares",
        "TRADVISOR_RECOVERY_BUCKET": "example-dev-recovery-register",
        "FINANCIALS_TABLE": "example-dev.stocks.financials",
    }


@pytest.mark.parametrize("target", ["api", "daily_job", "admin"])
def test_each_runtime_target_uses_the_explicit_shared_contract(target: str) -> None:
    config = RuntimeConfiguration.from_environment(target, api_environment(target))  # type: ignore[arg-type]

    assert config.environment == "development"
    assert config.project_id == config.target_project_id == "example-dev"
    assert config.firestore_database == "(default)"
    assert config.serving_target == "firestore"
    assert "fixture-only-secret" not in repr(config)


def test_missing_target_fields_fail_without_defaults() -> None:
    with pytest.raises(RuntimeConfigurationError, match="GOOGLE_CLOUD_PROJECT"):
        RuntimeConfiguration.from_environment("daily_job", {})


def test_target_project_mismatch_is_rejected() -> None:
    values = api_environment()
    values["TRADVISOR_TARGET_PROJECT_ID"] = "example-production"

    with pytest.raises(RuntimeConfigurationError, match="does not match"):
        RuntimeConfiguration.from_environment("api", values)


def test_environment_project_binding_prevents_cross_environment_targets() -> None:
    values = api_environment()
    values["TRADVISOR_ENVIRONMENT"] = "development"
    values["TRADVISOR_TARGET_PROJECT_ID"] = "example-production"
    values["TRADVISOR_ENVIRONMENT_PROJECT_ID"] = "example-dev"
    values["GOOGLE_CLOUD_PROJECT"] = "example-production"

    with pytest.raises(RuntimeConfigurationError, match="environment target"):
        RuntimeConfiguration.from_environment("api", values)


@pytest.mark.parametrize(
    "table",
    [
        "other-project.stocks.shares",
        "example-dev.stocks.shares;DROP TABLE x",
        "example-dev..shares",
        "example-dev.stocks",
    ],
)
def test_table_ids_must_be_fully_qualified_and_in_the_selected_project(table: str) -> None:
    values = api_environment()
    values["MARKET_DATA_TABLE"] = table

    with pytest.raises(RuntimeConfigurationError, match="fully qualified table"):
        RuntimeConfiguration.from_environment("api", values)


@pytest.mark.parametrize(
    ("environment", "origins"),
    [
        ("production", "http://localhost:3000"),
        ("development", "*"),
        ("development", "https://investors.example.test/path"),
        ("development", "https://user:pass@investors.example.test"),
    ],
)
def test_cors_rejects_unsafe_or_non_origin_values(environment: str, origins: str) -> None:
    values = api_environment()
    values["TRADVISOR_ENVIRONMENT"] = environment
    values["TRADVISOR_CORS_ORIGINS"] = origins

    with pytest.raises(RuntimeConfigurationError, match="TRADVISOR_CORS_ORIGINS"):
        RuntimeConfiguration.from_environment("api", values)


def test_daily_job_configuration_requires_both_project_bound_tables() -> None:
    values = api_environment()
    values.pop("FINANCIALS_TABLE")

    with pytest.raises(RuntimeConfigurationError, match="FINANCIALS_TABLE"):
        RuntimeConfiguration.from_environment("daily_job", values)


def test_workflow_dispatcher_requires_an_explicit_consistent_target() -> None:
    values = api_environment("workflow_dispatcher")
    values.pop("FIRESTORE_CURSOR_SECRET")
    values["TRADVISOR_TARGET_PROJECT_ID"] = "other-project"

    with pytest.raises(RuntimeConfigurationError, match="does not match"):
        WorkflowDispatchConfiguration.from_environment(values)


@pytest.mark.parametrize("value", ["", "0", "-1", "1.5", "301"])
def test_publication_control_debounce_is_required_positive_and_bounded(value: str) -> None:
    with pytest.raises(RuntimeConfigurationError, match="TRADVISOR_PUBLICATION_DEBOUNCE_SECONDS"):
        PublicationControlConfiguration.from_environment(
            {"TRADVISOR_PUBLICATION_DEBOUNCE_SECONDS": value}
        )


def test_publication_control_debounce_accepts_a_bounded_release_value() -> None:
    assert PublicationControlConfiguration.from_environment(
        {"TRADVISOR_PUBLICATION_DEBOUNCE_SECONDS": "60"}
    ).debounce_seconds == 60


def test_runtime_role_must_match_the_requested_config() -> None:
    with pytest.raises(RuntimeConfigurationError, match="does not match"):
        RuntimeConfiguration.from_environment("daily_job", api_environment())


def test_empty_cors_list_is_an_explicit_valid_setting() -> None:
    values = api_environment()
    values["TRADVISOR_CORS_ORIGINS"] = ""

    assert RuntimeConfiguration.from_environment("api", values).cors_origins == ()


def test_daily_job_rejects_invalid_configuration_before_cloud_client_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported_cloud_client = False
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        nonlocal imported_cloud_client
        if name == "google.cloud":
            imported_cloud_client = True
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(
        RuntimeConfiguration,
        "from_environment",
        staticmethod(_raise_missing_config),
    )

    with pytest.raises(RuntimeConfigurationError, match="fixture configuration failure"):
        build_worker()

    assert not imported_cloud_client


def test_api_rejects_invalid_configuration_before_store_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        RuntimeConfiguration,
        "from_environment",
        staticmethod(_raise_missing_config),
    )

    with pytest.raises(RuntimeConfigurationError, match="fixture configuration failure"):
        _production_analysis_publisher()

    _production_analysis_publisher.cache_clear()


def _raise_missing_config(target: str) -> NoReturn:
    raise RuntimeConfigurationError("fixture configuration failure")


def test_operator_example_and_docs_never_embed_a_cursor_secret() -> None:
    example = (ROOT / "backend/.env.example").read_text()
    docs = (ROOT / "docs/operations/runtime-configuration.md").read_text()

    assert "FIRESTORE_CURSOR_SECRET=" in example
    assert "fixture-only-secret" not in example + docs
    assert "TRADVISOR_TARGET_PROJECT_ID" in docs
    assert "Rule version boundary" in docs

