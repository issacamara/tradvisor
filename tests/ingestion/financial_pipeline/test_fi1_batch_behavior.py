"""FI-1 batch ordering, failure isolation, redaction and deadline tests."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse
import pytest
from functions.financials.fi1_job import MAX_RUNTIME_SECONDS, MODEL_ORDER, SELECTOR_URL, JobDeadlineExceeded, RuntimeAdapters, _get_response, run_batch

from fi1_support import (
    FIXTURES,
    VALID,
    selector_html,
    Harness,
    run,
    disable_source_pacing_in_offline_tests,  # noqa: F401
)


def test_symbol_pages_are_requested_serially_in_selector_order() -> None:
    symbols = tuple(f"S{i}" for i in range(9))
    fake = Harness(symbols=symbols)

    run(fake)

    assert fake.fetches.count(SELECTOR_URL) == 1
    page_queries = [
        parse_qs(urlparse(url).query)
        for url in fake.fetches[1:]
        if parse_qs(urlparse(url).query).get("page") == ["1"]
    ]
    assert [query["symbole"][0] for query in page_queries] == list(symbols)


def test_ten_terminal_symbols_flush_once_and_use_unique_batch_ids() -> None:
    fake = Harness(symbols=tuple(f"S{i}" for i in range(11)))

    run(fake)

    assert [len(rows) for rows, _ in fake.writes] == [10, 1]
    assert len({run_id for _, run_id in fake.writes}) == 2
    assert fake.completion_batches == [("a" * 64, "a" * 64)]


def test_failed_report_discards_all_rows_for_its_symbol() -> None:
    fake = Harness(symbols=("ABC",), years=(2025, 2024))

    def extract(pdf: bytes, model: str, key: str, timeout: float):
        if pdf.endswith(b"2024"):
            raise RuntimeError("failed")
        return {**VALID, "fiscal_year": int(pdf[-4:])}

    fake.extract = extract

    outcome = run(fake)

    assert outcome.failed == 1
    assert fake.writes == []
    assert fake.completions == []


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

    assert fake.actions == ["state_read", "staging_load", "merge_commit", "completion"]
    assert fake.completions == ["a" * 64]


def test_writer_failure_prints_only_failure_class_and_cannot_emit_completion(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness()
    adapters = fake.adapters()

    def failed_write(rows: list[dict[str, Any]], run_id: str) -> str:
        fake.actions.append("write")
        raise RuntimeError("commit failed")

    adapters = RuntimeAdapters(**{**adapters.__dict__, "write_rows": failed_write})

    with pytest.raises(RuntimeError, match="commit failed"):
        run_batch(adapters, api_key="runtime-secret")
    assert fake.actions == ["state_read", "write"]
    assert fake.completions == []
    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: succeeded",
        "FI-1 writer failed (RuntimeError)",
    ]


def test_commit_counts_wait_for_a_validated_receipt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness()
    adapters = RuntimeAdapters(
        **{**fake.adapters().__dict__, "write_rows": lambda _rows, _run_id: "invalid"}
    )

    with pytest.raises(RuntimeError, match="managed commit receipt"):
        run_batch(adapters, api_key="runtime-secret")

    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: succeeded",
        "FI-1 writer failed (RuntimeError)",
    ]


def test_untrusted_symbol_is_redacted_from_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness(symbols=("customer@example.com",))

    run(fake)

    output = capsys.readouterr().out
    assert "customer@example.com" not in output
    assert "FI-1 symbol redacted: succeeded" in output


def test_completion_failure_is_a_bounded_stage_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness()
    adapters = fake.adapters()

    def failed_completion(_fingerprints: Sequence[str]) -> Mapping[str, Any]:
        raise RuntimeError("completion failed")

    adapters = RuntimeAdapters(**{**adapters.__dict__, "completion": failed_completion})

    with pytest.raises(RuntimeError, match="completion failed"):
        run_batch(adapters, api_key="runtime-secret")
    assert fake.completions == []
    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: succeeded",
        "FI-1 batch committed: inserted=1 updated=0",
        "FI-1 completion failed (RuntimeError)",
    ]


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
    assert fake.writes == []
    assert fake.completions == []


def test_sentinels_never_enter_rows_or_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    sentinel = "PRIVATE_PDF_TEXT_PROMPT_PROVIDER_RESPONSE"

    def extract(*args):
        raise RuntimeError(sentinel)

    fake = Harness(extract=extract)
    outcome = run(fake)
    output = capsys.readouterr().out
    serialized = repr((fake.writes, output, outcome.as_dict()))

    assert sentinel not in serialized
    assert "https://www.richbourse.com/ABC-2024.pdf" not in output
    assert fake.writes == []


def test_successful_batch_does_not_print_source_pdf_or_extracted_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness()

    outcome = run(fake)
    output = capsys.readouterr().out
    retained = repr((fake.writes, output, outcome.as_dict()))

    assert "PRIVATE_PDF_SENTINEL" not in retained
    assert "https://www.richbourse.com/ABC-2024.pdf" not in output
    assert fake.writes


def test_runtime_budget_cannot_exceed_sixty_minutes() -> None:
    fake = Harness()

    with pytest.raises(ValueError, match="between 1 and 3600"):
        run(fake, max_duration_seconds=MAX_RUNTIME_SECONDS + 1)


def test_deadline_prevents_writes_and_completion(capsys: pytest.CaptureFixture[str]) -> None:
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
    assert "FI-1 execution deadline exceeded" in capsys.readouterr().out
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
