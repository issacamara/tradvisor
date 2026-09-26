"""Bounded, sanitized operational telemetry primitives."""

from .events import OperationalEvent, SanitizedLogger, record_event
from .health import is_stale

__all__ = ["OperationalEvent", "SanitizedLogger", "is_stale", "record_event"]
