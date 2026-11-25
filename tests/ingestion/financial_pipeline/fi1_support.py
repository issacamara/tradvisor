"""Shared harness, fixtures and sample data for the FI-1 runtime tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import parse_qs, urlparse
import pytest
from functions.financials import fi1_job
from functions.financials.fi1_job import MODEL_ORDER, SELECTOR_URL, RuntimeAdapters, run_batch


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
