from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "archive"
    / "legacy-ingestion"
    / "scripts"
    / "calendar.py"
)
SPEC = importlib.util.spec_from_file_location("exchange_calendar", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
calendar = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calendar
SPEC.loader.exec_module(calendar)


def source(source_id: str = "brvm-schedule") -> object:
    return calendar.SourceReference(
        source_id=source_id,
        source_url=f"https://example.test/{source_id}",
        source_date=date(2026, 1, 1),
        evidence_sha256="a" * 64,
    )


def period(start: date, end: date, state: object = None) -> object:
    return calendar.CoveragePeriod(
        start,
        end,
        state or calendar.VerificationStatus.VERIFIED,
        source("coverage"),
    )


def schedule(day: date, officialization: time = time(15), state: object = None) -> object:
    return calendar.DatedScheduleEvidence(
        day,
        True,
        officialization,
        source(),
        state or calendar.VerificationStatus.VERIFIED,
    )


def build(
    day: date,
    *,
    schedules: tuple = (),
    holidays: tuple = (),
    exceptions: tuple = (),
    cover: bool = True,
    version: str = "v1",
    parent: str | None = None,
) -> object:
    return calendar.build_calendar_version(
        version=version,
        parent_version=parent,
        start_date=day,
        end_date=day,
        schedules=schedules,
        holidays=holidays,
        coverage=(period(day, day),) if cover else (),
        exceptions=exceptions,
    )


def test_date_parser_requires_explicit_four_digit_year() -> None:
    assert calendar.parse_explicit_date("2026-08-17") == date(2026, 8, 17)
    for value in ("08-17", "2026/08/17", "2026-2-03", "2026-02-30"):
        with pytest.raises(ValueError):
            calendar.parse_explicit_date(value)


def test_provisional_holiday_does_not_certify_a_closure() -> None:
    day = date(2026, 8, 17)
    holiday = calendar.HolidayEvidence(
        day, source("movable-holiday"), calendar.VerificationStatus.PROVISIONAL
    )
    entry = build(day, schedules=(schedule(day),), holidays=(holiday,)).for_date(day)

    assert entry.status is calendar.SessionStatus.UNKNOWN
    assert entry.verification is calendar.VerificationStatus.PROVISIONAL
    assert entry.coverage_status is calendar.CoverageStatus.KNOWN
    assert entry.completion_cutoff is None
    assert holiday.source in entry.source_references


def test_verified_date_exception_overrides_base_and_retains_provenance() -> None:
    day = date(2026, 8, 17)
    notice = source("official-notice")
    recorded = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)
    exception = calendar.CalendarException(
        day, True, time(12), notice, recorded, "trusted-operator"
    )
    provisional_holiday = calendar.HolidayEvidence(
        day, source("provisional-holiday"), calendar.VerificationStatus.PROVISIONAL
    )
    entry = build(
        day,
        schedules=(schedule(day),),
        holidays=(provisional_holiday,),
        exceptions=(exception,),
    ).for_date(day)

    assert entry.status is calendar.SessionStatus.OPEN
    assert entry.verification is calendar.VerificationStatus.VERIFIED
    assert entry.scheduled_officialization == datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
    assert entry.completion_cutoff == datetime(2026, 8, 17, 12, 1, tzinfo=timezone.utc)
    assert entry.exception_source == notice
    assert entry.exception_recorded_at == recorded
    assert entry.exception_operator_id == "trusted-operator"
    assert provisional_holiday.source in entry.source_references


def test_missing_historical_coverage_remains_unverified() -> None:
    day = date(1999, 12, 31)
    entry = build(day, schedules=(schedule(day),), cover=False).for_date(day)

    assert entry.status is calendar.SessionStatus.OPEN
    assert entry.coverage_status is calendar.CoverageStatus.MISSING
    assert entry.verification is calendar.VerificationStatus.UNVERIFIED
    assert not calendar.is_session_complete(entry, datetime(2000, 1, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize(
    ("officialization", "expected_cutoff"),
    [
        (time(15), datetime(2026, 9, 23, 15, 1, tzinfo=timezone.utc)),
        (time(12), datetime(2026, 9, 23, 12, 1, tzinfo=timezone.utc)),
    ],
)
def test_normal_and_exceptional_cutoff_microsecond_boundaries(
    officialization: time, expected_cutoff: datetime
) -> None:
    day = date(2026, 9, 23)
    entry = build(day, schedules=(schedule(day, officialization),)).for_date(day)
    cutoff = expected_cutoff

    assert entry.scheduled_officialization == cutoff - timedelta(minutes=1)
    assert entry.completion_cutoff == cutoff
    assert not calendar.is_session_complete(entry, cutoff - timedelta(microseconds=1))
    assert calendar.is_session_complete(entry, cutoff)
    assert calendar.is_session_complete(entry, cutoff + timedelta(microseconds=1))
    assert calendar.price_available_by_deadline(cutoff - timedelta(microseconds=1), cutoff)
    assert calendar.price_available_by_deadline(cutoff, cutoff)
    assert not calendar.price_available_by_deadline(cutoff + timedelta(microseconds=1), cutoff)


def test_grid_has_no_weekday_or_holiday_eve_inference() -> None:
    monday = date(2026, 9, 21)
    tuesday = monday + timedelta(days=1)
    grid = calendar.build_calendar_version(
        version="v1",
        start_date=monday,
        end_date=tuesday,
        schedules=(schedule(monday),),
        holidays=(),
        coverage=(period(monday, tuesday),),
    )

    assert grid.for_date(monday).status is calendar.SessionStatus.OPEN
    assert grid.for_date(tuesday).status is calendar.SessionStatus.UNKNOWN
    assert grid.for_date(tuesday).verification is calendar.VerificationStatus.UNVERIFIED


def test_correction_publishes_new_version_without_mutating_retained_version() -> None:
    day = date(2026, 9, 23)
    initial = build(day, schedules=(schedule(day),), version="v1")
    original_entry = initial.for_date(day)
    notice = calendar.CalendarException(
        day,
        True,
        time(12),
        source("corrected-notice"),
        datetime(2026, 9, 23, 11, tzinfo=timezone.utc),
        "calendar-operator",
    )
    corrected = build(
        day,
        schedules=(schedule(day),),
        exceptions=(notice,),
        version="v2",
        parent="v1",
    )

    assert corrected.parent_version == initial.version
    assert corrected.version != initial.version
    assert corrected.content_sha256 != initial.content_sha256
    assert corrected.for_date(day).completion_cutoff == datetime(
        2026, 9, 23, 12, 1, tzinfo=timezone.utc
    )
    assert initial.for_date(day) == original_entry
    assert initial.for_date(day).completion_cutoff == datetime(
        2026, 9, 23, 15, 1, tzinfo=timezone.utc
    )


def test_holiday_eve_has_no_implicit_early_close() -> None:
    day = date(2026, 12, 24)
    entry = build(day, schedules=(schedule(day),)).for_date(day)
    assert entry.scheduled_officialization == datetime(2026, 12, 24, 15, tzinfo=timezone.utc)
