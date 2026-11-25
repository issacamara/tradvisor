"""FI-1 runtime configuration and default adapter tests."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
import pytest
from functions.financials import fi1_job
from functions.financials.fi1_job import MODEL_ORDER, RuntimeConfiguration, _default_adapters, main

from fi1_support import (
    runtime_environment,
    disable_source_pacing_in_offline_tests,  # noqa: F401
)


def test_runtime_configuration_consumes_terraform_managed_values() -> None:
    configuration = RuntimeConfiguration.from_environment(runtime_environment())

    assert configuration.project_id == "fixture-project"
    assert configuration.environment == "development"
    assert configuration.dataset == "stocks"
    assert configuration.financials_table == "fixture-project.stocks.financials"
    assert configuration.staging_table == "fixture-project.stocks.financials_staging"
    assert configuration.model_order == MODEL_ORDER
    assert configuration.max_concurrent_requests == 4
    assert configuration.max_reports_per_symbol == 5
    assert configuration.selection_mode == "historical"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TRADVISOR_RUNTIME_TARGET", "api"),
        ("TRADVISOR_ENVIRONMENT_PROJECT_ID", "other-project"),
        ("TRADVISOR_INGESTION_FINANCIALS_TABLE", "fixture-project.stocks.other"),
        ("TRADVISOR_FINANCIALS_MAX_CONCURRENT_REQUESTS", "5"),
        ("TRADVISOR_FINANCIALS_MAX_REPORTS_PER_SYMBOL", "6"),
        ("TRADVISOR_FINANCIALS_MAX_ATTEMPTS_PER_MODEL", "2"),
        ("TRADVISOR_FINANCIALS_SELECTION_MODE", ""),
        ("TRADVISOR_FINANCIALS_SELECTION_MODE", "unexpected"),
    ],
)
def test_runtime_configuration_rejects_unapproved_values(name: str, value: str) -> None:
    environment = runtime_environment()
    environment[name] = value

    with pytest.raises(ValueError):
        RuntimeConfiguration.from_environment(environment)


@pytest.mark.parametrize("selection_mode", ["historical", "previous_year", "publication_year"])
def test_command_config_check_uses_injected_non_secret_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_mode: str,
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("TRADVISOR_FINANCIALS_SELECTION_MODE", selection_mode)

    main(["--check-config"])

    output = capsys.readouterr().out
    assert '"runtime_target":"financial_ingestion_job"' in output
    assert '"max_concurrent_requests":4' in output
    assert f'"selection_mode":"{selection_mode}"' in output
    assert "OPENROUTER_API_KEY" not in output


@pytest.mark.parametrize("selection_mode", ["historical", "previous_year", "publication_year"])
def test_command_passes_injected_bounds_models_and_mode_to_batch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_mode: str,
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-secret")
    monkeypatch.setenv("TRADVISOR_FINANCIALS_SELECTION_MODE", selection_mode)
    adapters = object()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(fi1_job, "_default_adapters", lambda *args: adapters)

    def run(adapters_arg: object, **kwargs: object):
        calls.append({"adapters": adapters_arg, **kwargs})
        return SimpleNamespace(as_dict=lambda: {"completion": None})

    monkeypatch.setattr(fi1_job, "run_batch", run)
    main([])

    assert calls == [
        {
            "adapters": adapters,
            "api_key": "test-only-secret",
            "model_order": MODEL_ORDER,
            "max_page_concurrency": 4,
            "max_annual_candidates": 5,
            "selection_mode": selection_mode,
        }
    ]
    assert "test-only-secret" not in capsys.readouterr().out


def test_default_adapters_use_the_generic_completion_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    observability = ModuleType("ingestion_observability")
    observability.managed_import_completion = lambda *args, **kwargs: {}  # type: ignore[attr-defined]
    bigquery = ModuleType("google.cloud.bigquery")
    bigquery.Client = lambda **kwargs: object()  # type: ignore[attr-defined]
    google = ModuleType("google")
    cloud = ModuleType("google.cloud")
    cloud.bigquery = bigquery  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ingestion_observability", observability)
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)

    adapters = _default_adapters("dev-project", "stocks", "development")
    assert adapters.completion(()) == {}
    assert not hasattr(adapters, "emit_event")
    assert not hasattr(adapters, "emit_symbol_outcome")
