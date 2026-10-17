"""Shared credential-free fixtures for backend tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest


_CLOUD_CREDENTIAL_VARIABLES = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
)


@dataclass(frozen=True)
class LocalTestEnvironment:
    """Local-only settings that do not contact an emulator or cloud service."""

    firestore_emulator_host: str
    data_directory: str


@pytest.fixture
def credential_free_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[LocalTestEnvironment]:
    """Provide explicit local settings while ensuring cloud credentials are absent."""

    for variable in _CLOUD_CREDENTIAL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    emulator_host = "127.0.0.1:8080"
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", emulator_host)
    monkeypatch.setenv("TRADVISOR_TEST_DATA_DIR", os.fspath(tmp_path))

    yield LocalTestEnvironment(
        firestore_emulator_host=emulator_host,
        data_directory=os.fspath(tmp_path),
    )
