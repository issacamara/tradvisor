"""Shared, non-public helpers for trusted administrative commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Mapping

from backend.admin.admission import FirestoreAdmissionStore
from backend.configuration import RuntimeConfiguration
from backend.observability import SanitizedLogger, configure_json_stdout
from backend.recovery.register import GcsStorageAdapter, StorageAdapter

UTC = timezone.utc
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_ACTIONS = ("deny", "grant")


@dataclass(frozen=True, slots=True)
class AdminClients:
    """Explicit clients bound to one validated environment target."""

    store: Any
    config: RuntimeConfiguration


def parse_utc(value: str) -> datetime:
    """Parse an explicit UTC instant without accepting local-time ambiguity."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("created-at must be an ISO-8601 UTC instant") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("created-at must include an explicit UTC offset")
    return parsed.astimezone(UTC)


def require_identifier(value: str, *, field: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded opaque identifier")
    return value


def build_clients(environ: Mapping[str, str] | None = None) -> AdminClients:
    """Validate the admin target before importing or constructing cloud clients."""
    config = RuntimeConfiguration.from_environment("admin", environ)
    from google.cloud import firestore  # type: ignore[import-untyped]
    from google.cloud import storage  # type: ignore[import-untyped]

    firestore_client = firestore.Client(
        project=config.project_id,
        database=config.firestore_database,
    )
    storage_client = storage.Client(project=config.project_id)
    register: StorageAdapter = GcsStorageAdapter(storage_client.bucket(config.recovery_bucket))
    return AdminClients(FirestoreAdmissionStore(register, firestore_client), config)


def emit_success(
    events: SanitizedLogger,
    *,
    command: str,
    operation_id: str,
    action: str,
    sequence: int,
    active: bool | None = None,
) -> None:
    attributes: dict[str, str | int | bool] = {
        "correlation_id": require_identifier(operation_id, field="operation-id"),
        "count": 1,
        "attempt": 1,
    }
    if active is not None:
        attributes["records"] = sequence
    events.event(f"command.{command}", "succeeded", attributes=attributes)
    result: dict[str, str | int | bool] = {
        "action": action,
        "operation_id": operation_id,
        "sequence": sequence,
        "status": "succeeded",
    }
    if active is not None:
        result["active"] = active
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


def emit_failure(events: SanitizedLogger, *, command: str, operation_id: str | None, error: Exception) -> None:
    attributes: dict[str, str | int | bool] = {"error_class": type(error).__name__}
    if operation_id is not None and _IDENTIFIER.fullmatch(operation_id):
        attributes["correlation_id"] = operation_id
    events.event(f"command.{command}", "failed", attributes=attributes)


def logger(name: str) -> SanitizedLogger:
    return SanitizedLogger(configure_json_stdout(logging.getLogger(name)))


def add_common_arguments(parser: Any) -> None:
    parser.add_argument("--operation-id", required=True, help="Stable opaque ID reused for retries")
    parser.add_argument("--operator", required=True, help="Opaque trusted operator identity")
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--predecessor")
    parser.add_argument("--created-at", required=True, help="ISO-8601 UTC instant")


def valid_action(value: str) -> str:
    if value not in _ACTIONS:
        raise ValueError("action must be deny or grant")
    return value
