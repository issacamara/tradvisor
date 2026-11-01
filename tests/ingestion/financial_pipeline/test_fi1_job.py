"""Offline tests for the FI-1 batch runner and its side-effect boundaries."""

from __future__ import annotations

from pathlib import Path
import threading
import time
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from functions.financials.fi1_contracts import EXTRACTION_KEYS
from functions.financials.fi1_job import (
    MAX_RUNTIME_SECONDS,
    MODEL_ORDER,
    SELECTOR_URL,
    JobDeadlineExceeded,
    RuntimeAdapters,
    _get_response,
    run_batch,
)


FIXTURES = Path(__file__).parent / "fixtures"
VALID = {
    "fiscal_year": 2024,
    "revenue": 10,
    "net_income": 2,
    "total_debt": 3,
    "cash_and_cash_equivalents": 4,
    "total_equity": 5,
}


def selector_html(*symbols: str) -> str:
    options = "".join(f'<option value="{symbol}">{symbol}</option>' for symbol in symbols)
    return f'<select id="symbole">{options}</select>'


def report_page(symbol: str, years: tuple[int, ...]) -> str:
    rows = "".join(
        f'<div class="ligne_paire"><a href="/{symbol}-{year}.pdf">'
        f"Rapport annuel Exercice {year}</a></div>"
        for year in years
    )
    return f"<html><body>{rows}</body></html>"


class Harness:
    def __init__(
        self,
        symbols: tuple[str, ...] = ("ABC",),
        *,
        years: tuple[int, ...] = (2024,),
        existing: dict[tuple[str, int], str] | None = None,
        extract: Any = None,
    ) -> None:
        self.symbols = symbols
        self.years = years
        self.existing = existing or {}
        self.extract = extract or (
            lambda pdf, model, key, timeout: {
                **VALID,
                "fiscal_year": int(pdf[-4:]),
            }
        )
        self.fetches: list[str] = []
        self.downloads: list[str] = []
        self.attempts: list[str] = []
        self.writes: list[tuple[list[dict[str, Any]], str]] = []
        self.completions: list[str] = []
        self.events: list[tuple[str, str, dict[str, object]]] = []
        self.state_reads = 0
        self.actions: list[str] = []

    def adapters(self) -> RuntimeAdapters:
        def fetch_text(url: str, timeout: float) -> str:
            del timeout
            self.fetches.append(url)
            if url == SELECTOR_URL:
                return selector_html(*self.symbols)
            symbol = parse_qs(urlparse(url).query).get("symbole", [""])[0]
            return report_page(symbol, self.years)

        def download_pdf(url: str, timeout: float) -> bytes:
            del timeout
            self.downloads.append(url)
            year = url.rsplit("-", 1)[-1].split(".", 1)[0]
            return b"PRIVATE_PDF_SENTINEL" + year.encode()

        def prepare_document(pdf: bytes) -> str:
            return pdf.decode()

        def provider_attempt(document: str, model: str, key: str, timeout: float):
            self.attempts.append(model)
            return self.extract(document.encode(), model, key, timeout)

        def read_existing():
            self.state_reads += 1
            return dict(self.existing)

        def write_rows(rows: list[dict[str, Any]], run_id: str) -> str:
            self.actions.append("write")
            self.writes.append((rows, run_id))
            return "a" * 64

        def completion(fingerprint: str):
            self.actions.append("completion")
            self.completions.append(fingerprint)
            return {
                "source": "financials",
                "status": "succeeded",
                "managed_write": {"revision_fingerprint": fingerprint},
            }

        def emit(name: str, outcome: str, **fields: object) -> None:
            self.events.append((name, outcome, fields))

        return RuntimeAdapters(
            fetch_text=fetch_text,
            download_pdf=download_pdf,
            prepare_document=prepare_document,
            provider_attempt=provider_attempt,
            read_existing=read_existing,
            write_rows=write_rows,
            completion=completion,
            emit_event=emit,
        )


def run(harness: Harness, **kwargs: Any):
    return run_batch(harness.adapters(), api_key="runtime-secret", **kwargs)


def test_full_batch_uses_only_injected_offline_adapters() -> None:
    fake = Harness()

    outcome = run(fake)

    assert outcome.inserted == 1
    assert outcome.failed == 0
    assert fake.fetches.count(SELECTOR_URL) == 1
    assert fake.state_reads == 1
    assert fake.downloads == ["https://www.richbourse.com/ABC-2024.pdf"]
    assert fake.writes[0][0][0]["symbol"] == "ABC"
    assert tuple(key for key in fake.writes[0][0][0] if key in EXTRACTION_KEYS) == EXTRACTION_KEYS
    assert fake.actions == ["write", "completion"]
    assert outcome.completion is not None


def test_symbol_pages_are_bounded_to_four_concurrent_requests() -> None:
    fake = Harness(symbols=tuple(f"S{i}" for i in range(9)))
    adapters = fake.adapters()
    original_fetch = adapters.fetch_text
    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0

    def tracked_fetch(url: str, timeout: float) -> str:
        nonlocal in_flight, max_in_flight
        if url == SELECTOR_URL:
            return original_fetch(url, timeout)
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.01)
        try:
            return original_fetch(url, timeout)
        finally:
            with lock:
                in_flight -= 1

    adapters = RuntimeAdapters(
        **{**adapters.__dict__, "fetch_text": tracked_fetch}
    )
    outcome = run_batch(adapters, api_key="runtime-secret")

    assert outcome.discovered_symbols == 9
    assert fake.fetches.count(SELECTOR_URL) == 1
    assert max_in_flight <= 4
    assert max_in_flight > 1


def test_at_most_newest_five_annual_reports_are_processed() -> None:
    fixture = (FIXTURES / "fi1_symbol_page.html").read_text()
    fake = Harness(years=(2025, 2024, 2023, 2022, 2021, 2020))
    adapters = fake.adapters()
    adapters = RuntimeAdapters(**{**adapters.__dict__, "fetch_text": lambda url, timeout: (
        selector_html("ABC") if url == SELECTOR_URL else fixture
    )})

    outcome = run_batch(adapters, api_key="runtime-secret")

    assert outcome.annual_candidates == 5
    assert outcome.inserted == 5
    assert len(fake.downloads) == 5
    assert len(fake.attempts) == 5
    assert all("quarter" not in url and "half" not in url for url in fake.downloads)


def test_unchanged_link_skips_and_changed_link_replaces_same_identity() -> None:
    fake = Harness(years=(2025, 2024, 2023))
    fake.existing = {
        ("ABC", 2025): "https://www.richbourse.com/ABC-2025.pdf",
        ("ABC", 2024): "https://www.richbourse.com/old-2024.pdf",
    }

    outcome = run(fake)

    assert outcome.skipped == 1
    assert outcome.inserted == 1
    assert outcome.updated == 1
    assert len(fake.downloads) == 2
    rows = fake.writes[0][0]
    assert {(row["symbol"], row["fiscal_year"]) for row in rows} == {
        ("ABC", 2024),
        ("ABC", 2023),
    }
    assert fake.state_reads == 1


def test_unchanged_only_does_not_download_extract_or_write() -> None:
    link = "https://www.richbourse.com/ABC-2024.pdf"
    fake = Harness(existing={("ABC", 2024): link})

    outcome = run(fake)

    assert outcome.skipped == 1
    assert fake.downloads == []
    assert fake.attempts == []
    assert fake.writes == []
    assert fake.completions == []


@pytest.mark.parametrize(
    "bad_result",
    [
        RuntimeError("provider failed"),
        {**VALID, "fiscal_year": 2023},
        {**VALID, "revenue": None, "net_income": None, "total_debt": None,
         "cash_and_cash_equivalents": None, "total_equity": None},
    ],
)
def test_provider_fallback_attempts_each_approved_model_once(bad_result: Any) -> None:
    def extract(pdf: bytes, model: str, key: str, timeout: float):
        if model == MODEL_ORDER[0]:
            if isinstance(bad_result, Exception):
                raise bad_result
            return bad_result
        return dict(VALID)

    fake = Harness(extract=extract)

    outcome = run(fake)

    assert fake.attempts == list(MODEL_ORDER[:2])
    assert outcome.model_attempts == 2
    assert outcome.inserted == 1


@pytest.mark.parametrize(
    "existing",
    [
        {},
        {("ABC", 2024): "https://www.richbourse.com/old.pdf"},
    ],
)
def test_all_model_failure_preserves_state_and_emits_no_completion(existing) -> None:
    def failed(*args: object) -> None:
        raise ValueError("bad")

    fake = Harness(existing=existing, extract=failed)

    outcome = run(fake)

    assert outcome.failed == 1
    assert fake.attempts == list(MODEL_ORDER)
    assert fake.writes == []
    assert fake.completions == []
    assert fake.existing == existing
    assert outcome.completion is None


def test_successful_completion_follows_committed_changed_write() -> None:
    fake = Harness()

    run(fake)

    assert fake.actions == ["write", "completion"]
    assert fake.completions == ["a" * 64]


def test_writer_failure_cannot_emit_completion() -> None:
    fake = Harness()
    adapters = fake.adapters()

    def failed_write(rows: list[dict[str, Any]], run_id: str) -> str:
        fake.actions.append("write")
        raise RuntimeError("commit failed")

    adapters = RuntimeAdapters(**{**adapters.__dict__, "write_rows": failed_write})

    with pytest.raises(RuntimeError, match="commit failed"):
        run_batch(adapters, api_key="runtime-secret")
    assert fake.actions == ["write"]
    assert fake.completions == []


def test_failed_report_suppresses_batch_completion_even_after_other_write() -> None:
    fake = Harness(years=(2025, 2024))
    def selective(pdf: bytes, model: str, key: str, timeout: float):
        if pdf.endswith(b"2024"):
            raise RuntimeError("failed")
        return {**VALID, "fiscal_year": int(pdf[-4:])}

    fake.extract = selective
    adapters = fake.adapters()
    outcome = run_batch(adapters, api_key="runtime-secret")

    assert outcome.failed == 1
    assert len(fake.writes) == 1
    assert fake.completions == []


def test_sentinels_never_enter_rows_or_telemetry() -> None:
    sentinel = "PRIVATE_PDF_TEXT_PROMPT_PROVIDER_RESPONSE"

    def extract(*args):
        raise RuntimeError(sentinel)

    fake = Harness(extract=extract)
    outcome = run(fake)
    serialized = repr((fake.writes, fake.events, outcome.as_dict()))

    assert sentinel not in serialized
    assert "https://www.richbourse.com/ABC-2024.pdf" not in repr(fake.events)
    assert fake.writes == []


def test_successful_batch_does_not_retain_source_pdf_or_extracted_text() -> None:
    fake = Harness()

    outcome = run(fake)
    retained = repr((fake.writes, fake.events, outcome.as_dict()))

    assert "PRIVATE_PDF_SENTINEL" not in retained
    assert "https://www.richbourse.com/ABC-2024.pdf" not in repr(fake.events)
    assert fake.writes


def test_runtime_budget_cannot_exceed_sixty_minutes() -> None:
    fake = Harness()

    with pytest.raises(ValueError, match="between 1 and 3600"):
        run(fake, max_duration_seconds=MAX_RUNTIME_SECONDS + 1)


def test_deadline_prevents_writes_and_completion() -> None:
    fake = Harness()
    now = [0.0]
    adapters = fake.adapters()
    original_fetch = adapters.fetch_text

    def advancing_fetch(url: str, timeout: float) -> str:
        now[0] += 2
        return original_fetch(url, timeout)

    adapters = RuntimeAdapters(
        **{**adapters.__dict__, "fetch_text": advancing_fetch, "monotonic": lambda: now[0]}
    )

    with pytest.raises(JobDeadlineExceeded):
        run_batch(adapters, api_key="runtime-secret", max_duration_seconds=1)
    assert fake.writes == []
    assert fake.completions == []


def test_off_origin_redirect_is_rejected_before_following(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Response:
        status_code = 302
        content = b""
        headers = {"Location": "https://files.invalid/report.pdf"}

    def get(url: str, **kwargs: object):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        return Response()

    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.CurlHttpVersion = SimpleNamespace(V1_1=object())  # type: ignore[attr-defined]
    curl_cffi.requests = SimpleNamespace(get=get)  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", curl_cffi)

    with pytest.raises(ValueError, match="outside the approved origin"):
        _get_response("https://www.richbourse.com/report", accept="application/pdf", timeout=1)
    assert calls == ["https://www.richbourse.com/report"]
