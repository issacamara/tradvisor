"""Smoke tests for the installable backend package boundary."""

from __future__ import annotations

import importlib

from conftest import LocalTestEnvironment


def test_backend_import_is_credential_free(
    credential_free_environment: LocalTestEnvironment,
) -> None:
    backend = importlib.import_module("backend")

    assert backend.__version__ == "0.1.0"
    assert credential_free_environment.firestore_emulator_host == "127.0.0.1:8080"
