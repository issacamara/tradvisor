from __future__ import annotations

import subprocess
from collections.abc import Callable
from unittest.mock import Mock

import pytest

import scripts.deployment.verify_openrouter_secret_version as secret_gate
from scripts.deployment.verify_openrouter_secret_version import (
    has_enabled_version,
)


def test_enabled_version_check_lists_metadata_only() -> None:
    run: Callable[..., subprocess.CompletedProcess[str]] = Mock(
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="1\n", stderr="")
    )

    assert has_enabled_version("openrouter-key", "dev-tradvisor", run=run)

    args = run.call_args.args[0]
    assert args == [
        "gcloud",
        "secrets",
        "versions",
        "list",
        "openrouter-key",
        "--project=dev-tradvisor",
        "--filter=state=ENABLED",
        "--format=value(name)",
    ]
    assert "access" not in args
    assert run.call_args.kwargs == {"check": False, "capture_output": True, "text": True}


@pytest.mark.parametrize(
    ("returncode", "stdout"),
    [(0, ""), (1, "1\n"), (1, "")],
)
def test_missing_or_unreadable_enabled_version_fails_closed(
    returncode: int,
    stdout: str,
) -> None:
    run: Callable[..., subprocess.CompletedProcess[str]] = Mock(
        return_value=subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")
    )

    assert not has_enabled_version("openrouter-key", "dev-tradvisor", run=run)


def test_secret_reference_must_be_explicit_and_non_secret_shaped() -> None:
    run = Mock()

    assert not has_enabled_version("", "dev-tradvisor", run=run)
    assert not has_enabled_version("key-with-newline\nvalue", "dev-tradvisor", run=run)
    assert not has_enabled_version("openrouter-key", "", run=run)
    run.assert_not_called()


def test_command_line_gate_rejects_missing_reference_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENROUTER_SECRET_ID", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "dev-tradvisor")

    assert secret_gate.main() == 2
    assert "OPENROUTER_SECRET_ID" in capsys.readouterr().err


def test_missing_enabled_version_fails_without_emitting_reference_or_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENROUTER_SECRET_ID", "openrouter-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "dev-tradvisor")
    monkeypatch.setattr(secret_gate, "has_enabled_version", lambda *_: False)

    assert secret_gate.main() == 1
    captured = capsys.readouterr()
    assert "openrouter-key" not in captured.out + captured.err
    assert "no enabled version" in captured.err
