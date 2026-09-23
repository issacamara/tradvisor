"""Parse source-backed exchange calendar evidence into immutable versions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo


EXCHANGE_TIMEZONE = ZoneInfo("Africa/Abidjan")
UTC = timezone.utc
OFFICIALIZATION_BUFFER = timedelta(seconds=60)


class SessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PROVISIONAL = "provisional"
    UNVERIFIED = "unverified"


class CoverageStatus(StrEnum):
    KNOWN = "known"
    MISSING = "missing"


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    source_url: str
    source_date: date
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.source_url.strip():
            raise ValueError("source_id and source_url are required")
        if len(self.evidence_sha256) != 64:
            raise ValueError("evidence_sha256 must be a SHA-256 hex digest")
        try:
            int(self.evidence_sha256, 16)
        except ValueError as error:
            raise ValueError("evidence_sha256 must be a SHA-256 hex digest") from error


@dataclass(frozen=True)
class DatedScheduleEvidence:
    session_date: date
    is_open: bool
    officialization_time: time | None
    source: SourceReference
    verification: VerificationStatus = VerificationStatus.VERIFIED
    timing_tolerance_seconds: int = 60

    def __post_init__(self) -> None:
        if self.is_open != (self.officialization_time is not None):
            raise ValueError(
                "open sessions require an officialization time; closed sessions must omit it"
            )
        if self.timing_tolerance_seconds < 0:
            raise ValueError("timing_tolerance_seconds cannot be negative")


@dataclass(frozen=True)
class HolidayEvidence:
    session_date: date
    source: SourceReference
    verification: VerificationStatus = VerificationStatus.VERIFIED


@dataclass(frozen=True)
class CalendarException:
    session_date: date
    is_open: bool
    officialization_time: time | None
    source_notice: SourceReference
    recorded_at: datetime
    operator_id: str
    timing_tolerance_seconds: int = 60
    verification: VerificationStatus = VerificationStatus.VERIFIED

    def __post_init__(self) -> None:
        if self.is_open != (self.officialization_time is not None):
            raise ValueError(
                "open exceptions require an officialization time; closed exceptions must omit it"
            )
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        if not self.operator_id.strip():
            raise ValueError("operator_id is required")
        if self.timing_tolerance_seconds < 0:
            raise ValueError("timing_tolerance_seconds cannot be negative")


@dataclass(frozen=True)
class CoveragePeriod:
    start_date: date
    end_date: date
    verification: VerificationStatus
    source: SourceReference

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("coverage end_date precedes start_date")

    def includes(self, value: date) -> bool:
        return self.start_date <= value <= self.end_date


@dataclass(frozen=True)
class CalendarEntry:
    session_date: date
    status: SessionStatus
    verification: VerificationStatus
    coverage_status: CoverageStatus
    scheduled_officialization: datetime | None
    timing_tolerance_seconds: int | None
    completion_cutoff: datetime | None
    source_references: tuple[SourceReference, ...]
    exception_source: SourceReference | None = None
    exception_recorded_at: datetime | None = None
    exception_operator_id: str | None = None


@dataclass(frozen=True)
class CalendarVersion:
    version: str
    parent_version: str | None
    entries: tuple[CalendarEntry, ...]
    content_sha256: str

    def for_date(self, session_date: date) -> CalendarEntry:
        for entry in self.entries:
            if entry.session_date == session_date:
                return entry
        raise KeyError(session_date)


@dataclass(frozen=True)
class CalendarInputs:
    schedules: tuple[DatedScheduleEvidence, ...]
    holidays: tuple[HolidayEvidence, ...]
    coverage: tuple[CoveragePeriod, ...]
    exceptions: tuple[CalendarException, ...]


def parse_explicit_date(value: str) -> date:
    """Parse only a fully qualified ISO date; never borrow a year from context."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"date must include an explicit YYYY-MM-DD year: {value!r}") from error
    if parsed.isoformat() != value:
        raise ValueError(f"date must use YYYY-MM-DD: {value!r}")
    return parsed


def _required(row: Mapping[str, object], field: str) -> object:
    if field not in row or row[field] is None or row[field] == "":
        raise ValueError(f"required calendar row field is missing: {field}")
    return row[field]


def _row_date(row: Mapping[str, object], field: str) -> date:
    value = _required(row, field)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an explicit YYYY-MM-DD string")
    return parse_explicit_date(value)


def _row_text(row: Mapping[str, object], field: str) -> str:
    value = _required(row, field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _row_verification(row: Mapping[str, object]) -> VerificationStatus:
    value = _required(row, "verification")
    try:
        return VerificationStatus(value)
    except (TypeError, ValueError) as error:
        raise ValueError("verification must be verified, provisional, or unverified") from error


def _row_source(row: Mapping[str, object]) -> SourceReference:
    return SourceReference(
        source_id=_row_text(row, "source_id"),
        source_url=_row_text(row, "source_url"),
        source_date=_row_date(row, "source_date"),
        evidence_sha256=_row_text(row, "evidence_sha256"),
    )


def _row_time(row: Mapping[str, object], field: str) -> time | None:
    if field not in row:
        raise ValueError(f"required calendar row field is missing: {field}")
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an explicit HH:MM[:SS] string or null")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an explicit HH:MM[:SS] string or null") from error
    if value not in {parsed.strftime("%H:%M"), parsed.strftime("%H:%M:%S")}:
        raise ValueError(f"{field} must use canonical ISO time notation")
    return parsed


def _row_bool(row: Mapping[str, object], field: str) -> bool:
    value = _required(row, field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _row_nonnegative_int(row: Mapping[str, object], field: str) -> int:
    value = _required(row, field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _row_recorded_at(row: Mapping[str, object]) -> datetime:
    value = _required(row, "recorded_at")
    if not isinstance(value, str):
        raise ValueError("recorded_at must be a timezone-aware ISO datetime string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("recorded_at must be a timezone-aware ISO datetime string") from error
    if parsed.tzinfo is None:
        raise ValueError("recorded_at must be a timezone-aware ISO datetime string")
    return parsed


def parse_calendar_rows(
    *,
    schedule_rows: Iterable[Mapping[str, object]],
    holiday_rows: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
    exception_rows: Iterable[Mapping[str, object]] = (),
) -> CalendarInputs:
    """Parse stored/extracted mappings without fetching or interpreting source documents.

    Schedule rows require session_date, is_open, officialization_time, verification,
    timing_tolerance_seconds, source_id, source_url, source_date, and evidence_sha256.
    Holiday rows require session_date, verification, and the four source fields.
    Coverage rows require start_date, end_date, verification, and the four source fields.
    Exception rows require session_date, is_open, officialization_time, verification,
    timing_tolerance_seconds, recorded_at, operator_id, and the four source fields.
    Dates use YYYY-MM-DD; times use HH:MM[:SS]; recorded_at includes a UTC offset.
    A closed row supplies null for officialization_time. Extra columns are ignored.
    """
    schedules = tuple(
        DatedScheduleEvidence(
            _row_date(row, "session_date"),
            _row_bool(row, "is_open"),
            _row_time(row, "officialization_time"),
            _row_source(row),
            _row_verification(row),
            _row_nonnegative_int(row, "timing_tolerance_seconds"),
        )
        for row in schedule_rows
    )
    holidays = tuple(
        HolidayEvidence(
            _row_date(row, "session_date"), _row_source(row), _row_verification(row)
        )
        for row in holiday_rows
    )
    coverage = tuple(
        CoveragePeriod(
            _row_date(row, "start_date"),
            _row_date(row, "end_date"),
            _row_verification(row),
            _row_source(row),
        )
        for row in coverage_rows
    )
    exceptions = tuple(
        CalendarException(
            _row_date(row, "session_date"),
            _row_bool(row, "is_open"),
            _row_time(row, "officialization_time"),
            _row_source(row),
            _row_recorded_at(row),
            _row_text(row, "operator_id"),
            _row_nonnegative_int(row, "timing_tolerance_seconds"),
            _row_verification(row),
        )
        for row in exception_rows
    )
    return CalendarInputs(schedules, holidays, coverage, exceptions)


def _as_utc_instant(session_date: date, officialization: time) -> datetime:
    local = datetime.combine(session_date, officialization, tzinfo=EXCHANGE_TIMEZONE)
    return local.astimezone(UTC)


def _verification(*states: VerificationStatus) -> VerificationStatus:
    if VerificationStatus.UNVERIFIED in states:
        return VerificationStatus.UNVERIFIED
    if VerificationStatus.PROVISIONAL in states:
        return VerificationStatus.PROVISIONAL
    return VerificationStatus.VERIFIED


def _reference_payload(source: SourceReference) -> dict[str, str]:
    return {
        "source_id": source.source_id,
        "source_url": source.source_url,
        "source_date": source.source_date.isoformat(),
        "evidence_sha256": source.evidence_sha256,
    }


def _entry_payload(entry: CalendarEntry) -> dict[str, object]:
    return {
        "session_date": entry.session_date.isoformat(),
        "status": entry.status.value,
        "verification": entry.verification.value,
        "coverage_status": entry.coverage_status.value,
        "scheduled_officialization": entry.scheduled_officialization.isoformat()
        if entry.scheduled_officialization
        else None,
        "timing_tolerance_seconds": entry.timing_tolerance_seconds,
        "completion_cutoff": (
            entry.completion_cutoff.isoformat() if entry.completion_cutoff else None
        ),
        "source_references": [_reference_payload(source) for source in entry.source_references],
        "exception_source": (
            _reference_payload(entry.exception_source) if entry.exception_source else None
        ),
        "exception_recorded_at": entry.exception_recorded_at.isoformat()
        if entry.exception_recorded_at
        else None,
        "exception_operator_id": entry.exception_operator_id,
    }


def _make_entry(
    session_date: date,
    schedule: DatedScheduleEvidence | None,
    holiday: HolidayEvidence | None,
    coverage: CoveragePeriod | None,
    exception: CalendarException | None,
) -> CalendarEntry:
    if exception is not None:
        verified_exception = exception.verification is VerificationStatus.VERIFIED
        verified_coverage = (
            coverage is not None
            and coverage.verification is VerificationStatus.VERIFIED
        )
        status = (
            (SessionStatus.OPEN if exception.is_open else SessionStatus.CLOSED)
            if verified_exception
            else SessionStatus.UNKNOWN
        )
        verification = _verification(
            exception.verification,
            coverage.verification if coverage else VerificationStatus.UNVERIFIED,
        )
        coverage_status = CoverageStatus.KNOWN if coverage else CoverageStatus.MISSING
        officialization = (
            _as_utc_instant(session_date, exception.officialization_time)
            if verified_exception and exception.officialization_time
            else None
        )
        sources = tuple(
            source
            for source in (
                schedule.source if schedule else None,
                holiday.source if holiday else None,
                exception.source_notice,
                coverage.source if coverage else None,
            )
            if source is not None
        )
        return CalendarEntry(
            session_date,
            status,
            verification,
            coverage_status,
            officialization,
            exception.timing_tolerance_seconds if officialization else None,
            (
                officialization + OFFICIALIZATION_BUFFER
                if officialization and verified_coverage
                else None
            ),
            sources,
            exception.source_notice,
            exception.recorded_at.astimezone(UTC),
            exception.operator_id,
        )

    sources = tuple(
        source
        for source in (
            schedule.source if schedule else None,
            holiday.source if holiday else None,
            coverage.source if coverage else None,
        )
        if source is not None
    )
    verification = _verification(
        coverage.verification if coverage else VerificationStatus.UNVERIFIED,
        schedule.verification if schedule else VerificationStatus.UNVERIFIED,
        holiday.verification if holiday else VerificationStatus.VERIFIED,
    )
    coverage_status = CoverageStatus.KNOWN if coverage else CoverageStatus.MISSING
    if holiday is not None:
        status = (
            SessionStatus.CLOSED
            if holiday.verification is VerificationStatus.VERIFIED
            else SessionStatus.UNKNOWN
        )
    elif schedule is not None:
        status = (
            (SessionStatus.OPEN if schedule.is_open else SessionStatus.CLOSED)
            if schedule.verification is VerificationStatus.VERIFIED
            else SessionStatus.UNKNOWN
        )
    else:
        status = SessionStatus.UNKNOWN

    officialization = (
        _as_utc_instant(session_date, schedule.officialization_time)
        if schedule and schedule.is_open and status is SessionStatus.OPEN
        else None
    )
    return CalendarEntry(
        session_date,
        status,
        verification,
        coverage_status,
        officialization,
        schedule.timing_tolerance_seconds if officialization and schedule else None,
        officialization + OFFICIALIZATION_BUFFER if officialization else None,
        sources,
    )


def build_calendar_version(
    *,
    version: str,
    start_date: date,
    end_date: date,
    schedules: Iterable[DatedScheduleEvidence],
    holidays: Iterable[HolidayEvidence],
    coverage: Iterable[CoveragePeriod],
    exceptions: Iterable[CalendarException] = (),
    parent_version: str | None = None,
) -> CalendarVersion:
    """Build a complete immutable grid; omitted dates remain explicitly unknown."""
    if not version.strip():
        raise ValueError("version is required")
    if end_date < start_date:
        raise ValueError("end_date precedes start_date")

    def index_unique(items: Iterable[object], field: str) -> dict[date, object]:
        result: dict[date, object] = {}
        for item in items:
            item_date = getattr(item, field)
            if not start_date <= item_date <= end_date:
                raise ValueError(f"{field} {item_date} falls outside the requested grid")
            if item_date in result:
                raise ValueError(
                    f"multiple records for {item_date}; resolve precedence in source evidence"
                )
            result[item_date] = item
        return result

    schedule_by_date = index_unique(schedules, "session_date")
    holiday_by_date = index_unique(holidays, "session_date")
    exception_by_date = index_unique(exceptions, "session_date")

    coverage_periods = tuple(coverage)
    for period in coverage_periods:
        if period.start_date < start_date or period.end_date > end_date:
            raise ValueError("coverage period falls outside the requested grid")

    entries: list[CalendarEntry] = []
    current = start_date
    while current <= end_date:
        matching_coverage = [period for period in coverage_periods if period.includes(current)]
        if len(matching_coverage) > 1:
            raise ValueError(f"overlapping coverage declarations for {current}")
        entry = _make_entry(
            current,
            schedule_by_date.get(current),
            holiday_by_date.get(current),
            matching_coverage[0] if matching_coverage else None,
            exception_by_date.get(current),
        )
        entries.append(entry)
        current += timedelta(days=1)

    payload = {
        "parent_version": parent_version,
        "entries": [_entry_payload(entry) for entry in entries],
    }
    canonical = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return CalendarVersion(version, parent_version, tuple(entries), digest)


def build_calendar_version_from_rows(
    *,
    version: str,
    start_date: date,
    end_date: date,
    schedule_rows: Iterable[Mapping[str, object]],
    holiday_rows: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
    exception_rows: Iterable[Mapping[str, object]] = (),
    parent_version: str | None = None,
) -> CalendarVersion:
    """Parse evidence rows and publish one immutable, content-addressed version."""
    inputs = parse_calendar_rows(
        schedule_rows=schedule_rows,
        holiday_rows=holiday_rows,
        coverage_rows=coverage_rows,
        exception_rows=exception_rows,
    )
    return build_calendar_version(
        version=version,
        parent_version=parent_version,
        start_date=start_date,
        end_date=end_date,
        schedules=inputs.schedules,
        holidays=inputs.holidays,
        coverage=inputs.coverage,
        exceptions=inputs.exceptions,
    )


def is_session_complete(entry: CalendarEntry, now: datetime) -> bool:
    """Freshness completion is inclusive at the verified conservative cutoff."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return (
        entry.status is SessionStatus.OPEN
        and entry.verification is VerificationStatus.VERIFIED
        and entry.coverage_status is CoverageStatus.KNOWN
        and entry.completion_cutoff is not None
        and now.astimezone(UTC) >= entry.completion_cutoff
    )


def price_available_by_deadline(validated_available_at: datetime, deadline: datetime) -> bool:
    """Price eligibility is inclusive and compares timezone-aware UTC instants."""
    if validated_available_at.tzinfo is None or deadline.tzinfo is None:
        raise ValueError("availability and deadline must be timezone-aware")
    return validated_available_at.astimezone(UTC) <= deadline.astimezone(UTC)
