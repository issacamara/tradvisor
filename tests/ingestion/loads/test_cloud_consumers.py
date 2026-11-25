"""Cloud-backed ingestion consumer retry tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
import pytest

from loads_support import (
    _load_helper,
)  # noqa: F401 (imported fixtures)


class _SourceBlob:
    def __init__(self, name: str, content: str) -> None:
        self.name = name
        self._content = content

    def download_as_text(self) -> str:
        return self._content


def _install_cloud_runtime(
    monkeypatch: pytest.MonkeyPatch, blobs: list[_SourceBlob]
) -> None:
    monkeypatch.setenv("TRADVISOR_RUNTIME_TARGET", "ingestion")
    monkeypatch.setenv("TRADVISOR_ENVIRONMENT", "development")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "fixture-project")
    monkeypatch.setenv("TRADVISOR_TARGET_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("TRADVISOR_ENVIRONMENT_PROJECT_ID", "fixture-project")
    monkeypatch.setenv(
        "TRADVISOR_INGESTION_SERVICE_ACCOUNT",
        "fixture-ingestion@fixture-project.iam.gserviceaccount.com",
    )
    monkeypatch.setenv("TRADVISOR_INGESTION_DATA_BUCKET", "fixture-data-bucket")
    monkeypatch.setenv("TRADVISOR_INGESTION_ARCHIVE_BUCKET", "fixture-archive-bucket")
    monkeypatch.setenv("TRADVISOR_INGESTION_DATASET", "stocks")
    for asset in ("SHARES", "DIVIDENDS", "FINANCIALS", "RATINGS"):
        monkeypatch.setenv(
            f"TRADVISOR_INGESTION_{asset}_TABLE",
            f"fixture-project.stocks.{asset.lower()}",
        )
    bucket = SimpleNamespace(list_blobs=lambda prefix: blobs)
    storage = ModuleType("google.cloud.storage")
    storage.Client = lambda **kwargs: SimpleNamespace(bucket=lambda name: bucket)  # type: ignore[attr-defined]
    auth = ModuleType("google.auth")
    auth.default = lambda: ("fixture-credentials", "fixture-project")  # type: ignore[attr-defined]
    cloud = ModuleType("google.cloud")
    cloud.storage = storage  # type: ignore[attr-defined]
    google = ModuleType("google")
    google.auth = auth  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", storage)


def _load_cloud_consumer(
    monkeypatch: pytest.MonkeyPatch, path: Path, helper: ModuleType, name: str
) -> ModuleType:
    configuration_path = (
        Path(__file__).resolve().parents[3]
        / "functions"
        / "ingestion"
        / "ingestion_configuration.py"
    )
    configuration_specification = importlib.util.spec_from_file_location(
        "ingestion_configuration", configuration_path
    )
    assert (
        configuration_specification is not None
        and configuration_specification.loader is not None
    )
    configuration = importlib.util.module_from_spec(
        configuration_specification
    )
    monkeypatch.setitem(sys.modules, "ingestion_configuration", configuration)
    configuration_specification.loader.exec_module(configuration)

    framework = ModuleType("functions_framework")
    framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", framework)
    monkeypatch.setitem(sys.modules, "helper", helper)
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def test_dividend_entrypoint_retries_gcs_source_without_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blob = _SourceBlob("dividends-2026-10-14.csv", "payment_id|symbol\npayment-1|ABC\n")
    _install_cloud_runtime(monkeypatch, [blob])
    canonical: dict[str, dict[str, object]] = {}
    calls: list[str] = []
    archive_attempts = 0
    helper = ModuleType("helper")
    helper.get_project_number = lambda project_id: "123"  # type: ignore[attr-defined]

    def archive(source_bucket: str, archive_bucket: str, blob_name: str) -> None:
        nonlocal archive_attempts
        assert (source_bucket, archive_bucket, blob_name) == (
            "fixture-data-bucket",
            "fixture-archive-bucket",
            blob.name,
        )
        archive_attempts += 1
        calls.append("archive")
        if archive_attempts == 1:
            raise OSError("archive unavailable")

    def upsert_and_archive(frame, _project, _dataset, _table, keys, archive_callback) -> None:
        assert keys == ["payment_id"]
        for row in frame.to_dict("records"):
            canonical[row["payment_id"]] = row
        calls.append("upsert")
        archive_callback()

    helper.move_csv_file_gcp = archive  # type: ignore[attr-defined]
    helper.upsert_and_archive = upsert_and_archive  # type: ignore[attr-defined]
    module = _load_cloud_consumer(
        monkeypatch,
        Path(__file__).resolve().parents[3] / "functions" / "dividends" / "insert_dividends.py",
        helper,
        "cloud_only_dividends",
    )

    with pytest.raises(OSError, match="archive unavailable"):
        module.entry_point()
    assert canonical == {"payment-1": {"payment_id": "payment-1", "symbol": "ABC"}}
    assert calls == ["upsert", "archive"]

    assert module.entry_point() == "Data upsert successfully completed !\n"
    assert calls == ["upsert", "archive", "upsert", "archive"]
    assert len(canonical) == 1


def test_rating_entrypoint_preserves_revision_identity_across_gcs_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blob = _SourceBlob(
        "ratings-2026-10-14.csv", "symbol|source_revision_id\nABC|revision-1\n"
    )
    _install_cloud_runtime(monkeypatch, [blob])
    canonical: set[tuple[str, str]] = set()
    calls: list[str] = []
    archive_attempts = 0
    helper = ModuleType("helper")
    helper.get_project_number = lambda project_id: "123"  # type: ignore[attr-defined]
    helper.load_files = lambda _config, asset: [blob] if asset == "ratings" else []  # type: ignore[attr-defined]

    def upsert(frame, _project, _dataset, _table, keys, *, update_matched):
        assert keys == ["symbol", "source_revision_id"]
        assert update_matched is False
        canonical.update((row["symbol"], row["source_revision_id"]) for row in frame.to_dict("records"))
        calls.append("upsert")

    def archive(source_bucket: str, archive_bucket: str, blob_name: str) -> None:
        nonlocal archive_attempts
        assert (source_bucket, archive_bucket, blob_name) == (
            "fixture-data-bucket",
            "fixture-archive-bucket",
            blob.name,
        )
        archive_attempts += 1
        calls.append("archive")
        if archive_attempts == 1:
            raise OSError("archive unavailable")

    helper.upsert_into_bigquery = upsert  # type: ignore[attr-defined]
    helper.move_csv_file_gcp = archive  # type: ignore[attr-defined]
    module = _load_cloud_consumer(
        monkeypatch,
        Path(__file__).resolve().parents[3] / "functions" / "ratings" / "insert_ratings.py",
        helper,
        "cloud_only_ratings",
    )

    with pytest.raises(OSError, match="archive unavailable"):
        module.entry_point()
    assert canonical == {("ABC", "revision-1")}
    assert calls == ["upsert", "archive"]

    assert module.entry_point() == "Data insertion successfully completed !\n"
    assert calls == ["upsert", "archive", "upsert", "archive"]
    assert len(canonical) == 1


def test_shared_loader_rejects_missing_cloud_project_without_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _load_helper()
    _install_cloud_runtime(monkeypatch, [])
    sys.modules["google.auth"].default = lambda: ("fixture-credentials", None)  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="application-default project"):
        helper.load_files({"csv_directory": "local-data"}, "ratings")
