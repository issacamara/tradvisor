from datetime import datetime, timedelta, timezone
import io
import json
import logging

import pytest

from backend.observability.events import (
    OperationalEvent,
    PublicationControlEvents,
    SanitizedLogger,
    configure_json_stdout,
)
from backend.observability.health import is_stale


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def test_operational_event_is_sanitized_and_structured(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test-observability")
    with caplog.at_level(logging.INFO):
        SanitizedLogger(logger).event("publication", "success", duration_ms=12, attributes={"rows": 3}, now=NOW)
    fields = getattr(caplog.records[0], "tradvisor")
    assert fields["event"] == "publication"
    assert "rows" in fields


@pytest.mark.parametrize("key", ["authorization", "token", "password", "secret", "email", "uid"])
def test_sensitive_operational_attributes_are_rejected(key: str) -> None:
    with pytest.raises(ValueError):
        OperationalEvent("worker", "failed", NOW, attributes={key: "redacted"})


def test_missing_and_overdue_backup_evidence_is_stale() -> None:
    assert is_stale(None, now=NOW, max_age=timedelta(hours=24))
    assert is_stale(NOW - timedelta(hours=25), now=NOW, max_age=timedelta(hours=24))
    assert not is_stale(NOW - timedelta(hours=1), now=NOW, max_age=timedelta(hours=24))


def test_configured_stdout_is_one_sanitized_json_event() -> None:
    stream = io.StringIO()
    logger = configure_json_stdout(logging.getLogger("test-observability-json"), stream=stream)

    SanitizedLogger(logger).event("publication", "success", duration_ms=12, attributes={"rows": 3, "run_id": "run-42"}, now=NOW)

    assert json.loads(stream.getvalue()) == {
        "duration_ms": 12,
        "event": "publication",
        "occurred_at": "2026-09-26T12:00:00+00:00",
        "outcome": "success",
        "rows": 3,
        "run_id": "run-42",
    }


@pytest.mark.parametrize(
    "attributes",
    [
        {"correlation_id": "Bearer secret-token"},
        {"correlation_id": "operator@example.com"},
        {"correlation_id": "user-identifier-42"},
        {"error_class": '{"provider_body":"untrusted"}'},
        {"request_body": "untrusted"},
    ],
)
def test_sensitive_or_free_form_operational_values_are_rejected(attributes: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        OperationalEvent("worker", "failed", NOW, attributes=attributes)


@pytest.mark.parametrize(
    "event_name,outcome,attributes",
    [
        ("x" * 65, "success", {}),
        ("worker", "success", {"rows": 1_000_000_001}),
        ("worker", "success", {"release_id": "x" * 129}),
        ("worker", "success", {"unexpected": 1}),
    ],
)
def test_operational_names_and_values_are_bounded_and_allowlisted(event_name: str, outcome: str, attributes: dict[str, str | int]) -> None:
    with pytest.raises(ValueError):
        OperationalEvent(event_name, outcome, NOW, attributes=attributes)


def test_configured_stdout_drops_unstructured_log_content() -> None:
    stream = io.StringIO()
    logger = configure_json_stdout(logging.getLogger("test-observability-unstructured"), stream=stream)

    logger.error("provider body: operator@example.com Bearer secret-token")

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "logging.unstructured"
    assert payload["outcome"] == "dropped"
    assert "operator@example.com" not in stream.getvalue()


def test_publication_events_allow_only_bounded_sources_and_outcomes() -> None:
    stream = io.StringIO()
    events = PublicationControlEvents(
        SanitizedLogger(configure_json_stdout(logging.getLogger("test-publication-events"), stream=stream))
    )
    events.completion(source="shares", outcome="eligible_completion", now=NOW)
    events.control(outcome="published", sources="financials,shares", attempts=1, now=NOW)

    payloads = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert payloads[0]["source"] == "shares"
    assert payloads[1]["control_outcome"] == "published"


@pytest.mark.parametrize(
    "attributes",
    [
        {"source": "payload-body"},
        {"sources": "shares,ratings"},
        {"control_outcome": "free text identifier"},
    ],
)
def test_publication_event_attributes_reject_payloads_and_free_text(
    attributes: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        OperationalEvent("publication.control", "failed", NOW, attributes=attributes)
