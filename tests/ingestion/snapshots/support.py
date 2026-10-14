"""Ephemeral filesystem evidence fixtures for snapshot tests only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class AcquisitionNotCommittable(ValueError):
    """Raised when fixture acquisition evidence cannot be committed."""


@dataclass(frozen=True)
class ParserManifest:
    parser_name: str
    parser_version: str
    configuration: dict[str, Any]
    configuration_sha256: str


@dataclass(frozen=True)
class SourceSnapshot:
    source: str
    run_id: str
    acquired_at: str
    http_status: int
    payload_sha256: str
    payload_bytes: int
    parser_manifest: ParserManifest
    directory: str


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _safe_identifier(value: str, field: str) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError(f"{field} must use only letters, digits, '.', '_' or '-'")
    return value


def build_parser_manifest(
    parser_name: str,
    parser_version: str,
    configuration: Mapping[str, Any] | None = None,
) -> ParserManifest:
    _safe_identifier(parser_name, "parser_name")
    _safe_identifier(parser_version, "parser_version")
    normalized_configuration = dict(configuration or {})
    return ParserManifest(
        parser_name=parser_name,
        parser_version=parser_version,
        configuration=normalized_configuration,
        configuration_sha256=hashlib.sha256(
            _canonical_json(normalized_configuration)
        ).hexdigest(),
    )


def new_acquisition_run_id(now: datetime | None = None) -> str:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return f"{instant.astimezone(timezone.utc):%Y%m%dT%H%M%S%fZ}-{os.urandom(6).hex()}"


def commit_source_snapshot(
    snapshot_root: str | Path,
    *,
    source: str,
    run_id: str,
    payload: bytes,
    parser_manifest: ParserManifest,
    http_status: int,
    acquisition_complete: bool,
    acquired_at: datetime | None = None,
) -> SourceSnapshot:
    source = _safe_identifier(source, "source")
    run_id = _safe_identifier(run_id, "run_id")
    if not 200 <= http_status < 300:
        raise AcquisitionNotCommittable(
            f"HTTP status {http_status} cannot be committed as a successful acquisition"
        )
    if not acquisition_complete:
        raise AcquisitionNotCommittable("incomplete acquisition cannot be committed")

    instant = acquired_at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("acquired_at must be timezone-aware")
    run_directory = Path(snapshot_root) / source / run_id
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(
            f"snapshot evidence already exists for source={source!r}, run_id={run_id!r}"
        ) from error

    snapshot = SourceSnapshot(
        source=source,
        run_id=run_id,
        acquired_at=instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        http_status=http_status,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        payload_bytes=len(payload),
        parser_manifest=parser_manifest,
        directory=str(run_directory),
    )
    try:
        (run_directory / "payload.bin").write_bytes(payload)
        (run_directory / "manifest.json").write_bytes(_canonical_json(asdict(snapshot)))
        (run_directory / "COMMITTED").write_text("\n", encoding="ascii")
    except Exception:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise
    return snapshot
