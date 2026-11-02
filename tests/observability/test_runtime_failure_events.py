from __future__ import annotations

import importlib.util
import io
import json
import logging
from pathlib import Path

import pytest

import backend.jobs.daily as daily
from backend.observability.events import SanitizedLogger, configure_json_stdout


def test_daily_failure_event_contains_only_error_class(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(
        daily,
        "EVENTS",
        SanitizedLogger(configure_json_stdout(logging.getLogger("test-daily-events"), stream=stream)),
    )
    class Factory:
        def build(self, *, run_id: str):
            raise RuntimeError("Bearer sentinel-token")

    with pytest.raises(RuntimeError, match="daily batch build failed"):
        daily.run_daily(run_id="run-1", factory=Factory(), publisher=object())

    output = stream.getvalue()
    payload = json.loads(output)
    assert payload["event"] == "daily.build"
    assert payload["outcome"] == "failed"
    assert payload["error_class"] == "RuntimeError"
    assert "sentinel-token" not in output


def test_packaged_entrypoint_formatter_redacts_exception_text(capsys: pytest.CaptureFixture[str]) -> None:
    path = Path(__file__).parents[2] / "archive" / "legacy-ingestion" / "scripts" / "ingestion_observability.py"
    spec = importlib.util.spec_from_file_location("packaged_ingestion_observability", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    @module.observed_entrypoint("ingestion.test")
    def failing_entrypoint():
        raise ValueError("provider body Bearer sentinel-token")

    with pytest.raises(ValueError):
        failing_entrypoint()

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["event"] == "ingestion.test"
    assert payload["error_class"] == "ValueError"
    assert "sentinel-token" not in output


def test_fi1_symbol_outcome_has_a_finite_allowlisted_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = Path(__file__).parents[2] / "archive" / "legacy-ingestion" / "scripts" / "ingestion_observability.py"
    spec = importlib.util.spec_from_file_location("fi1_diagnostic_observability", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.emit_fi1_symbol_outcome("ABC", "failed", error_class="ProviderHTTP503")

    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "ingestion.fi1.symbol"
    assert set(payload) == {
        "event", "outcome", "occurred_at", "symbol", "error_class",
    }

    module.emit_fi1_commit_counts(inserted=2, updated=1)
    commit = json.loads(capsys.readouterr().out)
    assert commit["event"] == "ingestion.fi1.commit"
    assert commit["inserted"] == 2
    assert commit["updated"] == 1

    module.emit_fi1_stage_failure("writer", error_class="RuntimeError")
    failure = json.loads(capsys.readouterr().out)
    assert failure["event"] == "ingestion.fi1.failure"
    assert failure["stage"] == "writer"

    with pytest.raises(ValueError, match="invalid FI-1 commit counts"):
        module.emit_fi1_commit_counts(inserted=0, updated=0)
    with pytest.raises(ValueError, match="invalid FI-1 symbol outcome"):
        module.emit_fi1_symbol_outcome("operator@example.com", "failed")
    with pytest.raises(ValueError, match="invalid FI-1 stage failure"):
        module.emit_fi1_stage_failure("provider", error_class="RuntimeError")
