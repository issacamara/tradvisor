"""Offline tests for the FI-1 batch runner and its side-effect boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
import time
import importlib.util
import inspect
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from functions.financials.fi1_contracts import EXTRACTION_KEYS
from functions.financials.fi1_job import (
    MAX_RUNTIME_SECONDS,
    MODEL_ORDER,
    SELECTOR_URL,
    ActiveExecutionError,
    FirestoreExecutionLease,
    JobDeadlineExceeded,
    RuntimeAdapters,
    _default_adapters,
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


def test_default_writer_uses_legacy_managed_helper_call_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class Frame:
        def __init__(self, rows: list[dict[str, Any]], *, columns: list[str]) -> None:
            self.rows = rows
            self.columns = columns

    pandas = ModuleType("pandas")
    pandas.DataFrame = Frame  # type: ignore[attr-defined]
    helper = ModuleType("helper")

    def managed_writer(
        frame: object,
        revision_frame: object,
        project_id: str,
        dataset: str,
        archive: object,
        *,
        run_id: str | None = None,
    ) -> str:
        calls.append(
            ((frame, revision_frame, project_id, dataset, archive), {"run_id": run_id})
        )
        return "b" * 64

    helper.upsert_financials_and_archive = managed_writer  # type: ignore[attr-defined]
    observability = ModuleType("ingestion_observability")
    observability.emit_event = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    observability.managed_import_completion = lambda *args, **kwargs: {}  # type: ignore[attr-defined]
    bigquery = ModuleType("google.cloud.bigquery")
    bigquery.Client = lambda **kwargs: object()  # type: ignore[attr-defined]
    google = ModuleType("google")
    cloud = ModuleType("google.cloud")
    cloud.bigquery = bigquery  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pandas", pandas)
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.setitem(sys.modules, "ingestion_observability", observability)
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)

    adapters = _default_adapters("dev-project", "stocks")
    rows = [{"symbol": "ABC", "fiscal_year": 2024}]
    assert adapters.write_rows(rows, "fi1-run") == "b" * 64

    args, kwargs = calls[0]
    assert len(args) == 5
    assert isinstance(args[0], Frame)
    assert args[1] is None
    assert args[2:4] == ("dev-project", "stocks")
    assert callable(args[4])
    assert kwargs == {"run_id": "fi1-run"}

    writer_path = Path(__file__).parents[3] / "archive/legacy-ingestion/scripts/helper.py"
    spec = importlib.util.spec_from_file_location("fi1_managed_helper_contract", writer_path)
    assert spec is not None and spec.loader is not None
    helper_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper_module)
    inspect.signature(helper_module.upsert_financials_and_archive).bind(*args, **kwargs)


class _LeaseDocument:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state

    def get(self, *, transaction: object):
        del transaction
        data = dict(self.state) if self.state else None
        return SimpleNamespace(exists=data is not None, to_dict=lambda: data)


class _LeaseTransaction:
    def __init__(self, document: _LeaseDocument) -> None:
        self.document = document

    def set(self, document: _LeaseDocument, value: dict[str, object]) -> None:
        assert document is self.document
        self.document.state = dict(value)

    def delete(self, document: _LeaseDocument) -> None:
        assert document is self.document
        self.document.state.clear()


def _lease_store(document: _LeaseDocument):
    lock = threading.Lock()

    def transact(callback):
        with lock:
            return callback(_LeaseTransaction(document))

    return transact


def test_concurrent_fi1_runs_use_transactional_compare_and_set_lease() -> None:
    fake = Harness()
    document = _LeaseDocument({})
    transact = _lease_store(document)
    started = threading.Event()
    release = threading.Event()
    original_fetch = fake.adapters().fetch_text

    def blocking_fetch(url: str, timeout: float) -> str:
        if url == SELECTOR_URL:
            started.set()
            assert release.wait(timeout=2)
        return original_fetch(url, timeout)

    adapters = fake.adapters()
    adapters = RuntimeAdapters(
        **{
            **adapters.__dict__,
            "fetch_text": blocking_fetch,
            "execution_lease": lambda: FirestoreExecutionLease(
                transact, document, token="first-owner"
            ),
        }
    )
    results: list[object] = []
    worker = threading.Thread(
        target=lambda: results.append(run_batch(adapters, api_key="runtime-secret"))
    )
    worker.start()
    assert started.wait(timeout=2)

    competing = RuntimeAdapters(
        **{
            **adapters.__dict__,
            "execution_lease": lambda: FirestoreExecutionLease(
                transact, document, token="second-owner"
            ),
        }
    )
    with pytest.raises(ActiveExecutionError, match="another FI-1 execution is active"):
        run_batch(competing, api_key="runtime-secret")

    release.set()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert len(results) == 1
    assert document.state == {}


def test_expired_firestore_lease_allows_only_a_new_transactional_owner() -> None:
    document = _LeaseDocument({})
    now = [datetime(2026, 11, 1, tzinfo=timezone.utc)]
    transact = _lease_store(document)
    previous = FirestoreExecutionLease(
        transact,
        document,
        lease_seconds=2,
        renew_seconds=1,
        utcnow=lambda: now[0],
        token="expired-owner",
    )
    assert previous._transition(acquire=True)
    now[0] += timedelta(seconds=3)

    current = FirestoreExecutionLease(
        transact,
        document,
        lease_seconds=2,
        renew_seconds=1,
        utcnow=lambda: now[0],
        token="current-owner",
    )
    with current:
        assert document.state["owner"] == "current-owner"
    assert document.state == {}


def test_firestore_lease_releases_its_owner_after_batch_failure() -> None:
    document = _LeaseDocument({})
    lease = FirestoreExecutionLease(
        _lease_store(document), document, token="failing-owner"
    )

    with pytest.raises(RuntimeError, match="batch failed"):
        with lease:
            raise RuntimeError("batch failed")

    assert document.state == {}


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
