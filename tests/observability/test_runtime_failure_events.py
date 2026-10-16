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
