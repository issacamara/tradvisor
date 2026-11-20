"""Offline tests for the FI-1 batch runner and its side-effect boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import threading
import importlib.util
import inspect
from types import ModuleType, SimpleNamespace
from typing import Any, Sequence
from urllib.parse import parse_qs, urlparse

import pytest

from functions.financials import fi1_job
from functions.financials.fi1_job import EXTRACTION_KEYS
from functions.financials.fi1_job import (
    MAX_RUNTIME_SECONDS,
    MODEL_ORDER,
    SELECTOR_URL,
    JobDeadlineExceeded,
    ProviderHTTPError,
    RuntimeConfiguration,
    RuntimeAdapters,
    _default_adapters,
    _get_response,
    main,
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


@pytest.fixture(autouse=True)
def disable_source_pacing_in_offline_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fi1_job.time, "sleep", lambda _: None)


def runtime_environment() -> dict[str, str]:
    return {
        "TRADVISOR_RUNTIME_TARGET": "financial_ingestion_job",
        "TRADVISOR_ENVIRONMENT": "development",
        "GOOGLE_CLOUD_PROJECT": "fixture-project",
        "TRADVISOR_TARGET_PROJECT_ID": "fixture-project",
        "TRADVISOR_ENVIRONMENT_PROJECT_ID": "fixture-project",
        "TRADVISOR_INGESTION_DATASET": "stocks",
        "TRADVISOR_INGESTION_COMPANIES_TABLE": "fixture-project.stocks.brvm_companies",
        "TRADVISOR_INGESTION_FINANCIALS_TABLE": "fixture-project.stocks.financials",
        "TRADVISOR_INGESTION_FINANCIALS_STAGING_TABLE": "fixture-project.stocks.financials_staging",
        "TRADVISOR_FINANCIALS_MODEL_PRIMARY": MODEL_ORDER[0],
        "TRADVISOR_FINANCIALS_MODEL_FALLBACKS": ",".join(MODEL_ORDER[1:]),
        "TRADVISOR_FINANCIALS_MAX_CONCURRENT_REQUESTS": "4",
        "TRADVISOR_FINANCIALS_MAX_REPORTS_PER_SYMBOL": "5",
        "TRADVISOR_FINANCIALS_MAX_ATTEMPTS_PER_MODEL": "1",
    }


def test_runtime_configuration_consumes_terraform_managed_values() -> None:
    configuration = RuntimeConfiguration.from_environment(runtime_environment())

    assert configuration.project_id == "fixture-project"
    assert configuration.environment == "development"
    assert configuration.dataset == "stocks"
    assert configuration.financials_table == "fixture-project.stocks.financials"
    assert configuration.staging_table == "fixture-project.stocks.financials_staging"
    assert configuration.model_order == MODEL_ORDER
    assert configuration.max_concurrent_requests == 4
    assert configuration.max_reports_per_symbol == 5
    assert configuration.selection_mode == "historical"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TRADVISOR_RUNTIME_TARGET", "api"),
        ("TRADVISOR_ENVIRONMENT_PROJECT_ID", "other-project"),
        ("TRADVISOR_INGESTION_FINANCIALS_TABLE", "fixture-project.stocks.other"),
        ("TRADVISOR_FINANCIALS_MAX_CONCURRENT_REQUESTS", "5"),
        ("TRADVISOR_FINANCIALS_MAX_REPORTS_PER_SYMBOL", "6"),
        ("TRADVISOR_FINANCIALS_MAX_ATTEMPTS_PER_MODEL", "2"),
        ("TRADVISOR_FINANCIALS_SELECTION_MODE", ""),
        ("TRADVISOR_FINANCIALS_SELECTION_MODE", "unexpected"),
    ],
)
def test_runtime_configuration_rejects_unapproved_values(name: str, value: str) -> None:
    environment = runtime_environment()
    environment[name] = value

    with pytest.raises(ValueError):
        RuntimeConfiguration.from_environment(environment)


@pytest.mark.parametrize("selection_mode", ["historical", "previous_year", "publication_year"])
def test_command_config_check_uses_injected_non_secret_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_mode: str,
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("TRADVISOR_FINANCIALS_SELECTION_MODE", selection_mode)

    main(["--check-config"])

    output = capsys.readouterr().out
    assert '"runtime_target":"financial_ingestion_job"' in output
    assert '"max_concurrent_requests":4' in output
    assert f'"selection_mode":"{selection_mode}"' in output
    assert "OPENROUTER_API_KEY" not in output


@pytest.mark.parametrize("selection_mode", ["historical", "previous_year", "publication_year"])
def test_command_passes_injected_bounds_models_and_mode_to_batch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_mode: str,
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-secret")
    monkeypatch.setenv("TRADVISOR_FINANCIALS_SELECTION_MODE", selection_mode)
    adapters = object()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(fi1_job, "_default_adapters", lambda *args: adapters)

    def run(adapters_arg: object, **kwargs: object):
        calls.append({"adapters": adapters_arg, **kwargs})
        return SimpleNamespace(as_dict=lambda: {"completion": None})

    monkeypatch.setattr(fi1_job, "run_batch", run)
    main([])

    assert calls == [
        {
            "adapters": adapters,
            "api_key": "test-only-secret",
            "model_order": MODEL_ORDER,
            "max_page_concurrency": 4,
            "max_annual_candidates": 5,
            "selection_mode": selection_mode,
        }
    ]
    assert "test-only-secret" not in capsys.readouterr().out


def test_default_adapters_use_the_generic_completion_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    observability = ModuleType("ingestion_observability")
    observability.managed_import_completion = lambda *args, **kwargs: {}  # type: ignore[attr-defined]
    bigquery = ModuleType("google.cloud.bigquery")
    bigquery.Client = lambda **kwargs: object()  # type: ignore[attr-defined]
    google = ModuleType("google")
    cloud = ModuleType("google.cloud")
    cloud.bigquery = bigquery  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ingestion_observability", observability)
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)

    adapters = _default_adapters("dev-project", "stocks", "development")
    assert adapters.completion(()) == {}
    assert not hasattr(adapters, "emit_event")
    assert not hasattr(adapters, "emit_symbol_outcome")


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
        self.completion_batches: list[tuple[str, ...]] = []
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
            self.actions.append("state_read")
            return dict(self.existing)

        def write_rows(rows: list[dict[str, Any]], run_id: str) -> str:
            self.actions.extend(("staging_load", "merge_commit"))
            self.writes.append((rows, run_id))
            return "a" * 64

        def completion(fingerprints: Sequence[str]):
            self.actions.append("completion")
            self.completion_batches.append(tuple(fingerprints))
            self.completions.extend(fingerprints)
            return {
                "source": "financials",
                "status": "succeeded",
            "managed_write": {"revision_fingerprint": fingerprints[-1]},
            }

        return RuntimeAdapters(
            fetch_text=fetch_text,
            download_pdf=download_pdf,
            prepare_document=prepare_document,
            provider_attempt=provider_attempt,
            read_existing=read_existing,
            write_rows=write_rows,
            completion=completion,
            utcnow=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def run(harness: Harness, **kwargs: Any):
    return run_batch(harness.adapters(), api_key="runtime-secret", **kwargs)


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


def test_publication_year_tries_sixth_candidate_after_five_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fi1_job.time, "sleep", lambda _: None)
    fake = Harness()
    adapters = fake.adapters()
    first_page = (FIXTURES / "fi1_publication_page_five_failures.html").read_text()
    second_page = (FIXTURES / "fi1_publication_page_sixth_valid.html").read_text()

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
    assert [urlparse(url).query for url in fake.fetches if url != SELECTOR_URL] == [
        "symbole=ABC&page=1", "symbole=ABC&page=2"
    ]
    assert [url.rsplit("-", 1)[-1] for url in fake.downloads] == [
        "2025.pdf", "2024.pdf", "2023.pdf", "2022.pdf", "2021.pdf", "2020.pdf"
    ]
    assert [row["fiscal_year"] for row in fake.writes[0][0]] == [2020]
    assert outcome.completion is not None


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


def test_invalid_run_batch_mode_fails_before_adapter_access() -> None:
    fake = Harness()
    adapters = fake.adapters()

    with pytest.raises(ValueError, match="selection mode"):
        run_batch(adapters, api_key="runtime-secret", selection_mode="")

    assert fake.fetches == []
    assert fake.downloads == []
    assert fake.state_reads == 0


@pytest.mark.parametrize("selection_mode", ["", "unknown"])
def test_main_rejects_invalid_mode_before_constructing_backing_adapters(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_mode: str,
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("TRADVISOR_FINANCIALS_SELECTION_MODE", selection_mode)
    adapter_calls: list[bool] = []
    monkeypatch.setattr(
        fi1_job,
        "_default_adapters",
        lambda *args: adapter_calls.append(True),
    )

    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 1
    output = capsys.readouterr().out
    assert output.startswith("FI-1 configuration failed: ")
    assert "TRADVISOR_FINANCIALS_SELECTION_MODE" in output
    assert adapter_calls == []


def test_main_suppresses_raw_runtime_exception_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name, value in runtime_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OPENROUTER_API_KEY", "runtime-test-secret")
    monkeypatch.setattr(fi1_job, "_default_adapters", lambda *args: object())

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Bearer private-provider-body")

    monkeypatch.setattr(fi1_job, "run_batch", fail)
    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 1
    assert capsys.readouterr().out == ""


def test_full_batch_uses_only_injected_offline_adapters() -> None:
    fake = Harness()

    outcome = run(fake)

    assert outcome.inserted == 1
    assert outcome.failed == 0
    assert fake.fetches.count(SELECTOR_URL) == 1
    assert fake.state_reads == 1
    assert fake.downloads == ["https://www.richbourse.com/ABC-2024.pdf"]
    assert fake.writes[0][0][0]["symbol"] == "ABC"
    collected_at = fake.writes[0][0][0]["collected_at"]
    assert isinstance(collected_at, datetime)
    assert collected_at.tzinfo is timezone.utc
    assert tuple(key for key in fake.writes[0][0][0] if key in EXTRACTION_KEYS) == EXTRACTION_KEYS
    assert fake.actions == ["state_read", "staging_load", "merge_commit", "completion"]
    assert outcome.completion is not None


def test_each_processed_symbol_prints_one_terminal_outcome(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness()

    run(fake)

    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: succeeded",
        "FI-1 batch committed: inserted=1 updated=0",
    ]


def test_unchanged_candidate_prints_success_without_pdf_or_provider(
    capsys: pytest.CaptureFixture[str],
) -> None:
    link = "https://www.richbourse.com/ABC-2024.pdf"
    fake = Harness(existing={("ABC", 2024): link})

    run(fake)

    assert capsys.readouterr().out.splitlines() == ["FI-1 symbol ABC: succeeded"]
    assert fake.downloads == []
    assert fake.attempts == []


def test_multiple_candidates_print_one_terminal_symbol_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Harness(years=(2025, 2024))

    run(fake)

    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: succeeded",
        "FI-1 batch committed: inserted=2 updated=0",
    ]


def test_provider_http_status_is_sanitized_in_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*_args: object) -> object:
        raise ProviderHTTPError(503)

    fake = Harness(extract=fail)
    outcome = run(fake, model_order=(MODEL_ORDER[0],))
    assert capsys.readouterr().out.splitlines() == [
        "FI-1 symbol ABC: failed (ProviderHTTP503)"
    ]
    assert outcome.failed == 1
    assert fake.completions == []


def test_provider_http_error_rejects_invalid_status_codes() -> None:
    with pytest.raises(ValueError, match="provider HTTP status is invalid"):
        ProviderHTTPError(600)


def test_provider_http_response_body_is_not_carried_into_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "PRIVATE_PROVIDER_RESPONSE_BODY"

    class Response:
        status_code = 503
        text = sentinel

    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.CurlHttpVersion = SimpleNamespace(V1_1=object())  # type: ignore[attr-defined]
    curl_cffi.requests = SimpleNamespace(post=lambda *_args, **_kwargs: Response())  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", curl_cffi)

    with pytest.raises(ProviderHTTPError) as caught:
        fi1_job._provider_attempt("private text", MODEL_ORDER[0], "secret", 1)

    assert caught.value.status_code == 503
    assert str(caught.value) == "ProviderHTTP503"
    assert sentinel not in repr(caught.value)


def test_provider_sends_owner_prompt_and_document_separately_for_every_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"fiscal_year": 2024}'}}]}

    def post(*_args: object, **kwargs: object) -> Response:
        captured.append(kwargs)
        return Response()

    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.CurlHttpVersion = SimpleNamespace(V1_1=object())  # type: ignore[attr-defined]
    curl_cffi.requests = SimpleNamespace(post=post)  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", curl_cffi)

    for model in MODEL_ORDER:
        fi1_job._provider_attempt("synthetic document text", model, "secret", 1)

    assert [request["json"]["model"] for request in captured] == list(MODEL_ORDER)  # type: ignore[index]
    for request in captured:
        messages = request["json"]["messages"]  # type: ignore[index]
        assert messages == [
            {"role": "system", "content": fi1_job.OWNER_EXTRACTION_PROMPT},
            {"role": "user", "content": "synthetic document text"},
        ]
        assert sha256(messages[0]["content"].encode()).hexdigest() == (
            "dd961426d36af4c219e8aae0fca92264cc0869e777f21b17767b2879ed51185c"
        )


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

    adapters = _default_adapters("dev-project", "stocks", "development")
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


@pytest.mark.parametrize(
    ("first_mode", "second_mode"),
    [("historical", "previous_year"), ("previous_year", "historical")],
)
def test_overlapping_fi1_modes_can_insert_duplicate_logical_keys(
    first_mode: str, second_mode: str
) -> None:
    # Both invocations snapshot absence before either write. The fake storage
    # appends rows, showing that a logical key is not a global uniqueness rule.
    fake = Harness(years=(2025,))
    read_barrier = threading.Barrier(2)
    stored_rows: list[dict[str, Any]] = []
    adapters = []
    for mode in (first_mode, second_mode):
        run_adapters = fake.adapters()
        read_existing = run_adapters.read_existing
        write_rows = run_adapters.write_rows

        def synchronized_read(read=read_existing):
            snapshot = read()
            read_barrier.wait(timeout=2)
            return snapshot

        def append_rows(rows: list[dict[str, Any]], run_id: str, write=write_rows):
            receipt = write(rows, run_id)
            stored_rows.extend(dict(row) for row in rows)
            return receipt

        adapters.append(
            RuntimeAdapters(
                **{
                    **run_adapters.__dict__,
                    "read_existing": synchronized_read,
                    "write_rows": append_rows,
                }
            )
        )

    results: list[object] = []
    threads = [
        threading.Thread(
            target=lambda a=a, m=m: results.append(
                run_batch(a, api_key="runtime-secret", selection_mode=m)
            )
        )
        for a, m in zip(adapters, (first_mode, second_mode))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert len(results) == 2
    assert len(fake.writes) == 2
    assert len({run_id for _, run_id in fake.writes}) == 2
    assert [(row["symbol"], row["fiscal_year"]) for row in stored_rows] == [
        ("ABC", 2025),
        ("ABC", 2025),
    ]
    assert len(fake.completion_batches) == 2


def test_overlapping_changed_links_can_overwrite_each_other() -> None:
    old_link = "https://www.richbourse.com/ABC-old-2025.pdf"
    fake = Harness(
        years=(2025,), existing={("ABC", 2025): old_link}
    )
    read_barrier = threading.Barrier(2)
    commits: list[dict[str, Any]] = []
    final_state: dict[tuple[str, int], dict[str, Any]] = {}
    adapters = []
    for revenue in (11, 22):
        run_adapters = fake.adapters()
        read_existing = run_adapters.read_existing

        def synchronized_read(read=read_existing):
            snapshot = read()
            read_barrier.wait(timeout=2)
            return snapshot

        def last_write_wins(rows: list[dict[str, Any]], run_id: str):
            fake.writes.append((rows, run_id))
            for row in rows:
                committed = dict(row)
                commits.append(committed)
                final_state[(row["symbol"], row["fiscal_year"])] = committed
            return "a" * 64

        def extract(pdf: bytes, model: str, key: str, timeout: float, value=revenue):
            del model, key, timeout
            return {**VALID, "fiscal_year": int(pdf[-4:]), "revenue": value}

        adapters.append(
            RuntimeAdapters(
                **{
                    **run_adapters.__dict__,
                    "read_existing": synchronized_read,
                    "write_rows": last_write_wins,
                    "provider_attempt": extract,
                }
            )
        )

    threads = [
        threading.Thread(
            target=lambda a=a: run_batch(
                a, api_key="runtime-secret", selection_mode="previous_year"
            )
        )
        for a in adapters
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert len(commits) == 2
    assert {row["revenue"] for row in commits} == {11, 22}
    # A same-key replacement can be overwritten by either run; no winner is
    # inferred from the run-scoped receipts.
    assert final_state[("ABC", 2025)]["revenue"] in {11, 22}
    assert len(fake.completion_batches) == 2


def test_overlapping_writer_failure_has_run_scoped_completion() -> None:
    fake = Harness(years=(2025,))
    read_barrier = threading.Barrier(2)
    adapters = []
    for should_fail in (True, False):
        run_adapters = fake.adapters()
        read_existing = run_adapters.read_existing

        def synchronized_read(read=read_existing):
            snapshot = read()
            read_barrier.wait(timeout=2)
            return snapshot

        def write(rows: list[dict[str, Any]], run_id: str, fail=should_fail):
            if fail:
                raise RuntimeError("simulated run-local write failure")
            fake.writes.append((rows, run_id))
            return "a" * 64

        adapters.append(
            RuntimeAdapters(
                **{
                    **run_adapters.__dict__,
                    "read_existing": synchronized_read,
                    "write_rows": write,
                }
            )
        )

    outcomes: list[object] = []

    def execute(run_adapters: RuntimeAdapters) -> None:
        try:
            outcomes.append(run_batch(run_adapters, api_key="runtime-secret"))
        except RuntimeError as error:
            outcomes.append(error)

    threads = [threading.Thread(target=execute, args=(a,)) for a in adapters]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert sum(isinstance(outcome, RuntimeError) for outcome in outcomes) == 1
    assert sum(getattr(outcome, "completion", None) is not None for outcome in outcomes) == 1
    assert len(fake.completion_batches) == 1
    assert len(fake.writes) == 1


def test_new_retry_reads_committed_link_and_skips_completed_row() -> None:
    fake = Harness(years=(2025,))
    adapters = fake.adapters()
    write_rows = adapters.write_rows

    def commit_and_update_state(rows: list[dict[str, Any]], run_id: str) -> str:
        receipt = write_rows(rows, run_id)
        for row in rows:
            fake.existing[(row["symbol"], row["fiscal_year"])] = row["document_link"]
        return receipt

    adapters = RuntimeAdapters(**{**adapters.__dict__, "write_rows": commit_and_update_state})
    first = run_batch(adapters, api_key="runtime-secret")
    attempts_after_commit = len(fake.attempts)
    writes_after_commit = len(fake.writes)

    retry = run(fake)

    assert first.completion is not None
    assert retry.completion is None
    assert len(fake.attempts) == attempts_after_commit
    assert len(fake.writes) == writes_after_commit
    assert fake.state_reads == 2


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
