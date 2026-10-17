"""Minimal operational events with an explicit no-secrets boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import re
import sys
from typing import Mapping, TextIO


_MAX_EVENT_NAME_LENGTH = 64
_MAX_TEXT_VALUE_LENGTH = 128
_MAX_COUNT = 1_000_000_000
_MAX_DURATION_MS = 86_400_000
_EVENT_NAME = re.compile(r"[a-z][a-z0-9_.-]*\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]+\Z")
_SAFE_ERROR_CLASS = re.compile(r"[A-Za-z][A-Za-z0-9_.]*\Z")
_SENSITIVE_VALUE = re.compile(r"authorization|bearer|token|password|secret|api[_-]?key|email|uid|identifier|body", re.IGNORECASE)
_COUNT_ATTRIBUTES = frozenset({"count", "rows", "records", "attempt", "retry_count"})
_CORRELATION_ATTRIBUTES = frozenset({"batch_id", "correlation_id", "release_id", "run_id"})
_ALLOWED_ATTRIBUTES = _COUNT_ATTRIBUTES | _CORRELATION_ATTRIBUTES | frozenset({"error_class"})


def _bounded_name(value: str, *, field: str) -> None:
    if not value or len(value) > _MAX_EVENT_NAME_LENGTH or _EVENT_NAME.fullmatch(value) is None:
        raise ValueError(f"operational {field} must be a bounded lowercase name")


def _bounded_text(value: str, *, field: str, pattern: re.Pattern[str]) -> None:
    if not value or len(value) > _MAX_TEXT_VALUE_LENGTH or _SENSITIVE_VALUE.search(value) or pattern.fullmatch(value) is None:
        raise ValueError(f"operational {field} is not a safe bounded value")


@dataclass(frozen=True, slots=True)
class OperationalEvent:
    name: str
    outcome: str
    occurred_at: datetime
    duration_ms: int | None = None
    attributes: Mapping[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() != timezone.utc.utcoffset(self.occurred_at):
            raise ValueError("operational events require an explicit UTC timestamp")
        _bounded_name(self.name, field="event name")
        _bounded_name(self.outcome, field="outcome")
        if self.duration_ms is not None and (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or not 0 <= self.duration_ms <= _MAX_DURATION_MS
        ):
            raise ValueError("duration must be a bounded non-negative integer")
        unexpected_attributes = set(self.attributes) - _ALLOWED_ATTRIBUTES
        if unexpected_attributes:
            raise ValueError("operational attributes must use the bounded allowlist")
        for key, value in self.attributes.items():
            if key in _COUNT_ATTRIBUTES:
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_COUNT:
                    raise ValueError("operational count attributes must be bounded integers")
            elif key in _CORRELATION_ATTRIBUTES:
                if not isinstance(value, str):
                    raise ValueError("operational correlation attributes must be strings")
                _bounded_text(value, field=key, pattern=_SAFE_IDENTIFIER)
            elif key == "error_class":
                if not isinstance(value, str):
                    raise ValueError("operational error_class must be a string")
                _bounded_text(value, field=key, pattern=_SAFE_ERROR_CLASS)

    def as_log_fields(self) -> dict[str, str | int | float | bool]:
        return {"event": self.name, "outcome": self.outcome, "occurred_at": self.occurred_at.astimezone(timezone.utc).isoformat(), "duration_ms": self.duration_ms or 0, **dict(self.attributes)}


def record_event(logger: logging.Logger, event: OperationalEvent) -> None:
    logger.info("tradvisor_operational_event", extra={"tradvisor": event.as_log_fields(), "_tradvisor_event": event})


class JsonStdoutFormatter(logging.Formatter):
    """Render only validated operational events as one JSON object per stdout line."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "_tradvisor_event", None)
        if isinstance(event, OperationalEvent):
            fields = event.as_log_fields()
        else:
            fields = {
                "event": "logging.unstructured",
                "outcome": "dropped",
                "occurred_at": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "duration_ms": 0,
            }
        return json.dumps(fields, separators=(",", ":"), sort_keys=True, allow_nan=False)


def configure_json_stdout(logger: logging.Logger, *, stream: TextIO | None = None) -> logging.Logger:
    """Configure one stdout handler for sanitized operational events only."""

    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(JsonStdoutFormatter())
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


class SanitizedLogger:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def event(self, name: str, outcome: str, *, duration_ms: int | None = None, attributes: Mapping[str, str | int | float | bool] | None = None, now: datetime | None = None) -> None:
        record_event(self._logger, OperationalEvent(name, outcome, now or datetime.now(timezone.utc), duration_ms, attributes or {}))
