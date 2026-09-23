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


def row_source(**updates: object) -> dict[str, object]:
    return {
        "source_id": "official-calendar",
        "source_url": "https://example.test/calendar",
        "source_date": "2026-01-01",
        "evidence_sha256": "a" * 64,
        **updates,
    }


def test_row_parser_requires_explicit_years_and_declared_fields() -> None:
    schedule_row = row_source(
        session_date="2026-09-23",
        is_open=True,
        officialization_time="15:00",
        timing_tolerance_seconds=60,
        verification="verified",
    )
    coverage_row = row_source(
        start_date="2026-09-01", end_date="2026-09-30", verification="verified"
    )

    parsed = calendar.parse_calendar_rows(
        schedule_rows=(schedule_row,), holiday_rows=(), coverage_rows=(coverage_row,)
    )
    assert parsed.schedules[0].session_date == date(2026, 9, 23)

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        calendar.parse_calendar_rows(
            schedule_rows=({**schedule_row, "session_date": "09-23"},),
            holiday_rows=(),
            coverage_rows=(coverage_row,),
        )
    with pytest.raises(ValueError, match="required calendar row field.*officialization_time"):
        calendar.parse_calendar_rows(
            schedule_rows=({key: value for key, value in schedule_row.items()
                            if key != "officialization_time"},),
            holiday_rows=(),
            coverage_rows=(coverage_row,),
        )
    with pytest.raises(ValueError, match="required calendar row field.*source_url"):
        calendar.parse_calendar_rows(
            schedule_rows=(),
            holiday_rows=({key: value for key, value in row_source(
                session_date="2026-09-23", verification="verified"
            ).items() if key != "source_url"},),
            coverage_rows=(),
        )


def test_row_parser_preserves_provisional_holiday_and_missing_coverage() -> None:
    day = date(2026, 9, 23)
    schedule_row = row_source(
        session_date=day.isoformat(),
        is_open=True,
        officialization_time="15:00",
        timing_tolerance_seconds=60,
        verification="verified",
    )
    holiday_row = row_source(session_date=day.isoformat(), verification="provisional")
    coverage_row = row_source(
        start_date=day.isoformat(), end_date=day.isoformat(), verification="verified"
    )
    parsed_version = calendar.build_calendar_version_from_rows(
        version="rows-v1",
        start_date=day,
        end_date=day,
        schedule_rows=(schedule_row,),
        holiday_rows=(holiday_row,),
        coverage_rows=(coverage_row,),
    )
    entry = parsed_version.for_date(day)
    assert entry.status is calendar.SessionStatus.UNKNOWN
    assert entry.verification is calendar.VerificationStatus.PROVISIONAL
    assert entry.coverage_status is calendar.CoverageStatus.KNOWN

    uncovered = calendar.build_calendar_version_from_rows(
        version="rows-v2",
        start_date=day,
        end_date=day,
        schedule_rows=(schedule_row,),
        holiday_rows=(),
        coverage_rows=(),
    ).for_date(day)
    assert uncovered.status is calendar.SessionStatus.OPEN
    assert uncovered.coverage_status is calendar.CoverageStatus.MISSING


def test_unverified_exception_retains_audit_fields_without_changing_status_or_cutoff() -> None:
    day = date(2026, 9, 23)
    rows = {
        **row_source(
            session_date=day.isoformat(),
            is_open=True,
            officialization_time="12:00",
            timing_tolerance_seconds=60,
            verification="provisional",
            recorded_at="2026-09-20T10:00:00+00:00",
            operator_id="operator-7",
        )
    }
    entry = calendar.build_calendar_version_from_rows(
        version="rows-exception",
        start_date=day,
        end_date=day,
        schedule_rows=(row_source(
            session_date=day.isoformat(),
            is_open=True,
            officialization_time="15:00",
            timing_tolerance_seconds=60,
            verification="verified",
        ),),
        holiday_rows=(),
        coverage_rows=(row_source(
            start_date=day.isoformat(), end_date=day.isoformat(), verification="verified"
        ),),
        exception_rows=(rows,),
    ).for_date(day)

    assert entry.status is calendar.SessionStatus.UNKNOWN
    assert entry.verification is calendar.VerificationStatus.PROVISIONAL
    assert entry.coverage_status is calendar.CoverageStatus.KNOWN
    assert entry.scheduled_officialization is None
    assert entry.completion_cutoff is None
    assert entry.exception_source == calendar.SourceReference(
        "official-calendar", "https://example.test/calendar", date(2026, 1, 1), "a" * 64
    )
    assert entry.exception_recorded_at == datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
    assert entry.exception_operator_id == "operator-7"


def test_row_calendar_content_identity_is_stable_for_identical_evidence() -> None:
    day = date(2026, 9, 23)
    schedule_row = row_source(
        session_date=day.isoformat(),
        is_open=True,
        officialization_time="15:00",
        timing_tolerance_seconds=60,
        verification="verified",
    )
    coverage_row = row_source(
        start_date=day.isoformat(), end_date=day.isoformat(), verification="verified"
    )
    versions = [
        calendar.build_calendar_version_from_rows(
            version=version,
            start_date=day,
            end_date=day,
            schedule_rows=(schedule_row,),
            holiday_rows=(),
            coverage_rows=(coverage_row,),
        )
        for version in ("content-v1", "content-v2")
    ]
    assert versions[0].content_sha256 == versions[1].content_sha256
    assert versions[0].entries == versions[1].entries


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


@pytest.mark.parametrize(
    ("is_open", "verification"),
    [
        (True, calendar.VerificationStatus.PROVISIONAL),
        (False, calendar.VerificationStatus.PROVISIONAL),
        (True, calendar.VerificationStatus.UNVERIFIED),
        (False, calendar.VerificationStatus.UNVERIFIED),
    ],
)
def test_unconfirmed_schedule_rows_remain_unknown_without_timing(
    is_open: bool, verification: object
) -> None:
    day = date(2026, 9, 23)
    evidence = calendar.DatedScheduleEvidence(
        day,
        is_open,
        time(15) if is_open else None,
        source(),
        verification,
    )
    entry = build(day, schedules=(evidence,)).for_date(day)

    assert entry.status is calendar.SessionStatus.UNKNOWN
    assert entry.verification is verification
    assert entry.coverage_status is calendar.CoverageStatus.KNOWN
    assert entry.scheduled_officialization is None
    assert entry.timing_tolerance_seconds is None
    assert entry.completion_cutoff is None


@pytest.mark.parametrize(
    ("is_open", "expected_status", "expected_officialization", "expected_cutoff"),
    [
        (
            True,
            calendar.SessionStatus.OPEN,
            datetime(2026, 9, 23, 15, tzinfo=timezone.utc),
            datetime(2026, 9, 23, 15, 1, tzinfo=timezone.utc),
        ),
        (False, calendar.SessionStatus.CLOSED, None, None),
    ],
)
def test_verified_schedule_rows_retain_status_and_timing(
    is_open: bool,
    expected_status: object,
    expected_officialization: datetime | None,
    expected_cutoff: datetime | None,
) -> None:
    day = date(2026, 9, 23)
    evidence = calendar.DatedScheduleEvidence(
        day,
        is_open,
        time(15) if is_open else None,
        source(),
        calendar.VerificationStatus.VERIFIED,
    )
    entry = build(day, schedules=(evidence,)).for_date(day)

    assert entry.status is expected_status
    assert entry.verification is calendar.VerificationStatus.VERIFIED
    assert entry.scheduled_officialization == expected_officialization
    assert entry.completion_cutoff == expected_cutoff


def test_verified_holiday_still_overrides_verified_open_schedule() -> None:
    day = date(2026, 9, 23)
    holiday = calendar.HolidayEvidence(day, source("verified-holiday"))
    entry = build(day, schedules=(schedule(day),), holidays=(holiday,)).for_date(day)

    assert entry.status is calendar.SessionStatus.CLOSED
    assert entry.verification is calendar.VerificationStatus.VERIFIED
    assert entry.scheduled_officialization is None
    assert entry.completion_cutoff is None


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


@pytest.mark.parametrize(
    "coverage_verification",
    [None, calendar.VerificationStatus.PROVISIONAL],
)
def test_verified_exception_requires_verified_coverage_for_cutoff(
    coverage_verification: object | None,
) -> None:
    day = date(2026, 8, 17)
    exception = calendar.CalendarException(
        day,
        True,
        time(12),
        source("official-notice"),
        datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
        "trusted-operator",
    )
    coverage = (
        (period(day, day, coverage_verification),)
        if coverage_verification is not None
        else ()
    )
    entry = calendar.build_calendar_version(
        version="exception-without-verified-coverage",
        start_date=day,
        end_date=day,
        schedules=(schedule(day),),
        holidays=(),
        coverage=coverage,
        exceptions=(exception,),
    ).for_date(day)

    assert entry.status is calendar.SessionStatus.OPEN
    assert entry.verification is (
        coverage_verification or calendar.VerificationStatus.UNVERIFIED
    )
    assert entry.scheduled_officialization == datetime(
        2026, 8, 17, 12, tzinfo=timezone.utc
    )
    assert entry.completion_cutoff is None


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


def test_mixed_known_and_unknown_entries_index_only_verified_known_states() -> None:
    first = date(2026, 9, 21)
    unknown = first + timedelta(days=1)
    holiday = first + timedelta(days=2)
    provisional = first + timedelta(days=3)
    grid = calendar.build_calendar_version(
        version="mixed-v1",
        start_date=first,
        end_date=provisional,
        schedules=(
            schedule(first),
            schedule(provisional, state=calendar.VerificationStatus.PROVISIONAL),
        ),
        holidays=(calendar.HolidayEvidence(holiday, source("verified-holiday")),),
        coverage=(period(first, provisional),),
    )

    assert [entry.session_id for entry in grid.entries] == [
        day.isoformat() for day in (first, unknown, holiday, provisional)
    ]
    assert [entry.status for entry in grid.entries] == [
        calendar.SessionStatus.OPEN,
        calendar.SessionStatus.UNKNOWN,
        calendar.SessionStatus.CLOSED,
        calendar.SessionStatus.UNKNOWN,
    ]
    assert [entry.session_index for entry in grid.entries] == [0, None, 1, None]


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
    assert corrected.for_date(day).session_id == initial.for_date(day).session_id
    assert corrected.for_date(day).session_id == day.isoformat()
    assert corrected.for_date(day).session_index == initial.for_date(day).session_index == 0
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
