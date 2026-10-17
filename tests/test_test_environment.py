"""Tests for the shared local test fixture contract."""

from __future__ import annotations

import os

from conftest import LocalTestEnvironment


def test_credential_free_environment_removes_cloud_configuration(
    credential_free_environment: LocalTestEnvironment,
) -> None:
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ
    assert "GOOGLE_CLOUD_PROJECT" not in os.environ
    assert os.environ["FIRESTORE_EMULATOR_HOST"] == "127.0.0.1:8080"
    assert os.environ["TRADVISOR_TEST_DATA_DIR"] == credential_free_environment.data_directory
