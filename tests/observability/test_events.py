from datetime import datetime, timedelta, timezone
import logging

import pytest

from backend.observability.events import OperationalEvent, SanitizedLogger
from backend.observability.health import is_stale


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def test_operational_event_is_sanitized_and_structured(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test-observability")
    with caplog.at_level(logging.INFO):
        SanitizedLogger(logger).event("publication", "success", duration_ms=12, attributes={"rows": 3}, now=NOW)
    assert caplog.records[0].tradvisor["event"] == "publication"
    assert "rows" in caplog.records[0].tradvisor


@pytest.mark.parametrize("key", ["authorization", "token", "password", "secret", "email", "uid"])
def test_sensitive_operational_attributes_are_rejected(key: str) -> None:
    with pytest.raises(ValueError):
        OperationalEvent("worker", "failed", NOW, attributes={key: "redacted"})


def test_missing_and_overdue_backup_evidence_is_stale() -> None:
    assert is_stale(None, now=NOW, max_age=timedelta(hours=24))
    assert is_stale(NOW - timedelta(hours=25), now=NOW, max_age=timedelta(hours=24))
    assert not is_stale(NOW - timedelta(hours=1), now=NOW, max_age=timedelta(hours=24))
