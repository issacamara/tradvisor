"""FI-1 report-selection and publication-year tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
import pytest
from functions.financials import fi1_job
from functions.financials.fi1_job import MODEL_ORDER, SELECTOR_URL, RuntimeAdapters, run_batch

from fi1_support import (
    FIXTURES,
    VALID,
    selector_html,
    Harness,
    run,
    disable_source_pacing_in_offline_tests,
)  # noqa: F401 (imported fixtures)


@pytest.mark.parametrize(("year", "expected"), [(2026, [2025, 2021]), (2027, [2026, 2025])])
def test_batch_uses_current_year_for_report_selection(year: int, expected: list[int]) -> None:
    fake = Harness(years=(2026, 2025, 2021, 2020))
    adapters = fake.adapters()
    adapters = RuntimeAdapters(
        **{**adapters.__dict__, "utcnow": lambda: datetime(year, 1, 1, tzinfo=timezone.utc)}
    )

    run_batch(adapters, api_key="runtime-secret")

    assert [row["fiscal_year"] for row in fake.writes[0][0]] == expected


def test_previous_year_mode_selects_only_utc_previous_year() -> None:
    fake = Harness(years=(2026, 2025, 2024, 2021))
    adapters = fake.adapters()
    adapters = RuntimeAdapters(
        **{
            **adapters.__dict__,
            # Local calendar says 2027-01-01, but the instant is still 2026 UTC.
            "utcnow": lambda: datetime(2027, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1))),
        }
    )

    outcome = run_batch(adapters, api_key="runtime-secret", selection_mode="previous_year")

    assert outcome.annual_candidates == 1
    assert [row["fiscal_year"] for row in fake.writes[0][0]] == [2025]
    assert [url.rsplit("-", 1)[-1].split(".", 1)[0] for url in fake.downloads] == ["2025"]


def test_previous_year_without_target_report_has_no_extraction_or_write() -> None:
    fake = Harness(years=(2024, 2021))

    outcome = run(fake, selection_mode="previous_year")

    assert outcome.annual_candidates == 0
    assert fake.downloads == []
    assert fake.attempts == []
    assert fake.writes == []
    assert fake.completions == []


def test_previous_year_target_stays_fixed_when_clock_crosses_utc_new_year() -> None:
    fake = Harness(symbols=("ABC", "DEF"), years=(2026, 2025, 2024))
    clock_values = iter(
        [
            datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
            datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc),
            datetime(2027, 1, 1, 0, 2, tzinfo=timezone.utc),
        ]
    )
    adapters = fake.adapters()
    adapters = RuntimeAdapters(**{**adapters.__dict__, "utcnow": lambda: next(clock_values)})

    outcome = run_batch(adapters, api_key="runtime-secret", selection_mode="previous_year")

    assert outcome.annual_candidates == 2
    assert [row["fiscal_year"] for rows, _ in fake.writes for row in rows] == [2025, 2025]


def test_publication_year_tries_sixth_candidate_then_stops_after_first_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fi1_job.time, "sleep", lambda _: None)
    fake = Harness()
    adapters = fake.adapters()
    first_page = (FIXTURES / "fi1_publication_page_five_failures.html").read_text()
    second_page = (FIXTURES / "fi1_publication_page_sixth_valid.html").read_text()
    attempted_documents: list[str] = []

    def fetch_text(url: str, timeout: float) -> str:
        del timeout
        fake.fetches.append(url)
        if url == SELECTOR_URL:
            return selector_html("ABC")
        page = parse_qs(urlparse(url).query)["page"][0]
        return first_page if page == "1" else second_page

    def download_pdf(url: str, timeout: float) -> bytes:
        del timeout
        fake.downloads.append(url)
        return url.rsplit("-", 1)[-1].split(".", 1)[0].encode()

    def provider_attempt(document: str, model: str, key: str, timeout: float):
        fake.attempts.append(model)
        attempted_documents.append(document)
        if document != "2020":
            raise ValueError("invalid source document")
        return {**VALID, "fiscal_year": int(document)}

    adapters = RuntimeAdapters(
        **{
            **adapters.__dict__,
            "fetch_text": fetch_text,
            "download_pdf": download_pdf,
            "provider_attempt": provider_attempt,
        }
    )

    outcome = run_batch(adapters, api_key="runtime-secret", selection_mode="publication_year")

    assert outcome.failed == 0
    assert outcome.annual_candidates == 7
    assert [urlparse(url).query for url in fake.fetches if url != SELECTOR_URL] == [
        "symbole=ABC&page=1", "symbole=ABC&page=2"
    ]
    assert [url.rsplit("-", 1)[-1] for url in fake.downloads] == [
        "2025.pdf", "2024.pdf", "2023.pdf", "2022.pdf", "2021.pdf", "2020.pdf"
    ]
    assert attempted_documents == [
        document
        for document in ("2025", "2024", "2023", "2022", "2021")
        for _ in MODEL_ORDER
    ] + ["2020"]
    assert [row["fiscal_year"] for row in fake.writes[0][0]] == [2020]
    assert outcome.completion is not None


def test_publication_year_with_no_current_year_candidate_does_not_download_or_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fi1_job.time, "sleep", lambda _: None)
    fake = Harness()
    adapters = fake.adapters()
    old_publication_page = (
        FIXTURES / "fi1_publication_page_no_current_candidate.html"
    ).read_text()

    def fetch_text(url: str, timeout: float) -> str:
        del timeout
        fake.fetches.append(url)
        if url == SELECTOR_URL:
            return selector_html("ABC")
        return old_publication_page

    def unexpected_download(url: str, timeout: float) -> bytes:
        del timeout
        pytest.fail(f"unexpected PDF download: {url}")

    adapters = RuntimeAdapters(
        **{
            **adapters.__dict__,
            "fetch_text": fetch_text,
            "download_pdf": unexpected_download,
        }
    )

    outcome = run_batch(adapters, api_key="runtime-secret", selection_mode="publication_year")

    assert outcome.annual_candidates == 0
    assert [urlparse(url).query for url in fake.fetches if url != SELECTOR_URL] == [
        "symbole=ABC&page=1"
    ]
    assert fake.downloads == []
    assert fake.writes == []


@pytest.mark.parametrize("ending_page", ["repeat", "empty"])
def test_publication_year_stops_on_repeated_or_empty_pages(
    monkeypatch: pytest.MonkeyPatch,
    ending_page: str,
) -> None:
    monkeypatch.setattr(fi1_job.time, "sleep", lambda _: None)
    fake = Harness()
    adapters = fake.adapters()
    first_page = (FIXTURES / "fi1_publication_page_failure.html").read_text()

    def fetch_text(url: str, timeout: float) -> str:
        del timeout
        fake.fetches.append(url)
        if url == SELECTOR_URL:
            return selector_html("ABC")
        return first_page if ending_page == "repeat" or parse_qs(urlparse(url).query)["page"] == ["1"] else ""

    def download_pdf(url: str, timeout: float) -> bytes:
        del timeout
        fake.downloads.append(url)
        return b"2025"

    def provider_attempt(document: str, model: str, key: str, timeout: float):
        del document, model, key, timeout
        return {**VALID, "fiscal_year": 2025}

    adapters = RuntimeAdapters(
        **{
            **adapters.__dict__,
            "fetch_text": fetch_text,
            "download_pdf": download_pdf,
            "provider_attempt": provider_attempt,
        }
    )

    outcome = run_batch(adapters, api_key="runtime-secret", selection_mode="publication_year")

    page_urls = [url for url in fake.fetches if url != SELECTOR_URL]
    assert len(page_urls) == 2
    assert outcome.inserted == 1
    assert [row["fiscal_year"] for row in fake.writes[0][0]] == [2025]
