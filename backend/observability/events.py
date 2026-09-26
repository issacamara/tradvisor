"""Minimal operational events with an explicit no-secrets boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Mapping

_FORBIDDEN_KEYS = frozenset({"authorization", "token", "password", "secret", "api_key", "email", "uid"})


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
        if any(key.casefold() in _FORBIDDEN_KEYS for key in self.attributes):
            raise ValueError("operational attributes contain a forbidden sensitive key")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration cannot be negative")

    def as_log_fields(self) -> dict[str, str | int | float | bool]:
        return {"event": self.name, "outcome": self.outcome, "occurred_at": self.occurred_at.astimezone(timezone.utc).isoformat(), "duration_ms": self.duration_ms or 0, **dict(self.attributes)}


def record_event(logger: logging.Logger, event: OperationalEvent) -> None:
    logger.info("tradvisor_operational_event", extra={"tradvisor": event.as_log_fields()})


class SanitizedLogger:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def event(self, name: str, outcome: str, *, duration_ms: int | None = None, attributes: Mapping[str, str | int | float | bool] | None = None, now: datetime | None = None) -> None:
        record_event(self._logger, OperationalEvent(name, outcome, now or datetime.now(timezone.utc), duration_ms, attributes or {}))
