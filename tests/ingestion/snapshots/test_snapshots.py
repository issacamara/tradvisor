"""Focused tests for immutable legacy-ingestion acquisition evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest


def _load_helper() -> ModuleType:
    helper_path = (
        Path(__file__).resolve().parents[3]
        / "archive"
        / "legacy-ingestion"
        / "scripts"
        / "helper.py"
    )
    specification = importlib.util.spec_from_file_location("ingestion_helper", helper_path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_import_is_safe_without_snapshot_or_client_activity(tmp_path: Path) -> None:
    helper = _load_helper()

    assert not list(tmp_path.iterdir())
    assert callable(helper.commit_source_snapshot)
    assert callable(helper.build_parser_manifest)


def test_retries_create_distinct_immutable_same_day_evidence(tmp_path: Path) -> None:
    helper = _load_helper()
    manifest = helper.build_parser_manifest("shares", "1.0", {"separator": "|"})
    acquired_at = datetime(2026, 9, 22, 8, 30, tzinfo=timezone.utc)

    first = helper.commit_source_snapshot(
        tmp_path,
        source="brvm-shares",
        run_id="20260922T083000Z-first",
        payload=b"symbol|close\nABC|100\n",
        parser_manifest=manifest,
        http_status=200,
        acquisition_complete=True,
        acquired_at=acquired_at,
    )
    retry = helper.commit_source_snapshot(
        tmp_path,
        source="brvm-shares",
        run_id="20260922T083000Z-retry",
        payload=b"symbol|close\nABC|100\n",
        parser_manifest=manifest,
        http_status=200,
        acquisition_complete=True,
        acquired_at=acquired_at,
    )

    assert first.directory != retry.directory
    assert Path(first.directory, "payload.bin").read_bytes() == b"symbol|close\nABC|100\n"
    assert Path(retry.directory, "COMMITTED").is_file()
    stored_manifest = json.loads(Path(first.directory, "manifest.json").read_text())
    assert stored_manifest["payload_sha256"] == first.payload_sha256
    assert stored_manifest["parser_manifest"]["configuration_sha256"] == manifest.configuration_sha256


@pytest.mark.parametrize(
    ("http_status", "complete"),
    [(503, True), (200, False)],
)
def test_failed_or_incomplete_acquisition_is_never_committed(
    tmp_path: Path, http_status: int, complete: bool
) -> None:
    helper = _load_helper()
    manifest = helper.build_parser_manifest("shares", "1.0")

    with pytest.raises(helper.AcquisitionNotCommittable):
        helper.commit_source_snapshot(
            tmp_path,
            source="brvm-shares",
            run_id="failed-attempt",
            payload=b"partial",
            parser_manifest=manifest,
            http_status=http_status,
            acquisition_complete=complete,
        )

    assert not (tmp_path / "brvm-shares").exists()


def test_existing_run_id_is_not_overwritten(tmp_path: Path) -> None:
    helper = _load_helper()
    manifest = helper.build_parser_manifest("shares", "1.0")
    arguments = {
        "source": "brvm-shares",
        "run_id": "run-001",
        "payload": b"original",
        "parser_manifest": manifest,
        "http_status": 200,
        "acquisition_complete": True,
    }
    snapshot = helper.commit_source_snapshot(tmp_path, **arguments)

    with pytest.raises(FileExistsError):
        helper.commit_source_snapshot(tmp_path, **arguments)

    assert Path(snapshot.directory, "payload.bin").read_bytes() == b"original"


def test_parser_manifest_is_deterministic_and_run_ids_are_unique() -> None:
    helper = _load_helper()

    first = helper.build_parser_manifest("shares", "1.0", {"b": 2, "a": 1})
    second = helper.build_parser_manifest("shares", "1.0", {"a": 1, "b": 2})
    now = datetime(2026, 9, 22, 8, 30, tzinfo=timezone.utc)

    assert first.configuration_sha256 == second.configuration_sha256
    assert helper.new_acquisition_run_id(now) != helper.new_acquisition_run_id(now)
