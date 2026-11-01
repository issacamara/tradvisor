"""Bounded, in-memory runtime for the FI-1 financial ingestion job."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
import time
from typing import Any, Callable, Mapping
from urllib.parse import urljoin
from uuid import uuid4

from functions.financials.fi1_contracts import (
    AnnualCandidate,
    RowDecision,
    ValidatedExtraction,
    decide_row_state,
    is_approved_document_url,
    parse_annual_candidates,
    parse_selector_symbols,
    richbourse_symbol_page_url,
    validate_extraction,
)


SELECTOR_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ORDER = (
    "gemma-4-31b-it",
    "nvidia/nemotron-3.5-lightning:free",
    "openai/gpt-4o-mini",
)
MAX_RUNTIME_SECONDS = 60 * 60
MAX_PAGE_CONCURRENCY = 4
MAX_ANNUAL_CANDIDATES = 5
SOURCE_TIMEOUT_SECONDS = 30
SOURCE_ATTEMPTS = 3
_RETRYABLE_SOURCE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
MAX_REDIRECTS = 5
PROVIDER_TIMEOUT_SECONDS = 120
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_FINANCIAL_VALUE_KEYS = (
    "revenue",
    "net_income",
    "total_debt",
    "cash_and_cash_equivalents",
    "total_equity",
)


class JobDeadlineExceeded(TimeoutError):
    """The configured job time budget was exhausted."""


@dataclass(frozen=True)
class JobOutcome:
    discovered_symbols: int
    annual_candidates: int
    skipped: int
    inserted: int
    updated: int
    failed: int
    model_attempts: int
    completion: Mapping[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "discovered_symbols": self.discovered_symbols,
            "annual_candidates": self.annual_candidates,
            "skipped": self.skipped,
            "inserted": self.inserted,
            "updated": self.updated,
            "failed": self.failed,
            "model_attempts": self.model_attempts,
            "completion": dict(self.completion) if self.completion is not None else None,
        }


@dataclass(frozen=True)
class RuntimeAdapters:
    """Injectable external effects; tests supply offline fakes for every adapter."""

    fetch_text: Callable[[str, float], str]
    download_pdf: Callable[[str, float], bytes]
    prepare_document: Callable[[bytes], str]
    provider_attempt: Callable[[str, str, str, float], Mapping[str, object]]
    read_existing: Callable[[], Mapping[tuple[str, int], str | None]]
    write_rows: Callable[[list[dict[str, Any]], str], str]
    completion: Callable[[str], Mapping[str, Any]]
    emit_event: Callable[..., None]
    monotonic: Callable[[], float] = time.monotonic
    utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def _remaining(deadline: float, monotonic: Callable[[], float]) -> float:
    value = deadline - monotonic()
    if value <= 0:
        raise JobDeadlineExceeded("FI-1 runtime deadline exceeded")
    return value


def _get_response(url: str, *, accept: str, timeout: float) -> Any:
    """Fetch one RichBourse response, checking each redirect before following it."""
    from curl_cffi import CurlHttpVersion, requests

    request_deadline = time.monotonic() + timeout
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        if not is_approved_document_url(current_url):
            raise ValueError("RichBourse URL is outside the approved origin")
        last_error: Exception | None = None
        response = None
        for attempt in range(SOURCE_ATTEMPTS):
            remaining = request_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("RichBourse request deadline exceeded")
            try:
                response = requests.get(
                    current_url,
                    headers={"Accept": accept, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
                    timeout=remaining,
                    impersonate="chrome",
                    http_version=CurlHttpVersion.V1_1,
                    allow_redirects=False,
                )
                if response.status_code in _RETRYABLE_SOURCE_STATUSES or (
                    response.status_code == 200 and not response.content
                ):
                    if attempt + 1 == SOURCE_ATTEMPTS:
                        raise RuntimeError("RichBourse response remained unavailable")
                    time.sleep(min((1, 2)[attempt], max(0.0, request_deadline - time.monotonic())))
                    continue
                break
            except RuntimeError:
                raise
            except Exception as error:
                last_error = error
                if attempt + 1 == SOURCE_ATTEMPTS:
                    raise RuntimeError("RichBourse transport failed") from error
                time.sleep(min((1, 2)[attempt], max(0.0, request_deadline - time.monotonic())))
        if response is None:
            raise RuntimeError("RichBourse transport failed") from last_error
        if response.status_code in _REDIRECT_STATUSES:
            location = response.headers.get("Location")
            if not location or redirect_count == MAX_REDIRECTS:
                raise RuntimeError("RichBourse redirect limit exceeded")
            target = urljoin(current_url, location)
            if not is_approved_document_url(target):
                raise ValueError("RichBourse redirect is outside the approved origin")
            current_url = target
            continue
        if response.status_code != 200 or not response.content:
            raise RuntimeError(f"RichBourse HTTP {response.status_code}")
        return response
    raise RuntimeError("RichBourse redirect limit exceeded")


def _fetch_text(url: str, timeout: float) -> str:
    response = _get_response(
        url,
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        timeout=timeout,
    )
    return response.content.decode("utf-8", errors="replace")


def _download_pdf(url: str, timeout: float) -> bytes:
    response = _get_response(url, accept="application/pdf,*/*;q=0.8", timeout=timeout)
    content = bytes(response.content)
    if not content.startswith(b"%PDF-"):
        raise ValueError("RichBourse response is not a PDF")
    return content


def _pdf_text(pdf_bytes: bytes) -> str:
    """Reuse the existing PDF text adapter without retaining its output."""
    from insert_financials import extract_text_from_pdf

    text = extract_text_from_pdf(pdf_bytes)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("PDF contains no extractable text")
    return text


def _provider_attempt(
    document_text: str, model: str, api_key: str, timeout: float
) -> Mapping[str, object]:
    from curl_cffi import CurlHttpVersion, requests

    prompt = (
        "Extract annual financial values from this BRVM statement. Return only a JSON object "
        "with exactly these keys: fiscal_year, revenue, net_income, total_debt, "
        "cash_and_cash_equivalents, total_equity. Values must be finite numbers or null. "
        "Use full XOF units; never guess missing values. The document text follows.\n\n"
        f"{document_text}"
    )
    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tradvisor.app",
            "X-Title": "TRADVISOR BRVM",
        },
        json={
            "model": model,
            "provider": {"allow_fallbacks": False},
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
        impersonate="chrome",
        http_version=CurlHttpVersion.V1_1,
    )
    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter HTTP {response.status_code}")
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("provider result is not JSON text")
    result = json.loads(content)
    if not isinstance(result, Mapping):
        raise ValueError("provider result is not an object")
    return result


def _default_adapters(project_id: str, dataset: str) -> RuntimeAdapters:
    from google.cloud import bigquery
    from ingestion_observability import emit_event, managed_import_completion

    if re.fullmatch(r"[A-Za-z0-9_-]+", project_id) is None:
        raise ValueError("invalid Google Cloud project configuration")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", dataset) is None:
        raise ValueError("invalid financial dataset configuration")
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.financials"

    def read_existing() -> Mapping[tuple[str, int], str | None]:
        query = (
            "SELECT symbol, fiscal_year, document_link "
            f"FROM `{table_id}`"
        )
        return {
            (str(row.symbol), int(row.fiscal_year)):
            str(row.document_link) if row.document_link is not None else None
            for row in client.query(query).result()
        }

    def write_rows(rows: list[dict[str, Any]], run_id: str) -> str:
        import pandas as pd
        from helper import upsert_financials_and_archive

        frame = pd.DataFrame(
            rows,
            columns=[
                "symbol",
                "fiscal_year",
                "revenue",
                "net_income",
                "total_debt",
                "cash_and_cash_equivalents",
                "total_equity",
                "document_link",
                "collected_at",
            ],
        )
        return upsert_financials_and_archive(
            frame,
            project_id,
            dataset,
            lambda: None,
            run_id=run_id,
        )

    return RuntimeAdapters(
        fetch_text=_fetch_text,
        download_pdf=_download_pdf,
        prepare_document=_pdf_text,
        provider_attempt=_provider_attempt,
        read_existing=read_existing,
        write_rows=write_rows,
        completion=lambda fingerprint: managed_import_completion(
            "financials", [fingerprint]
        ),
        emit_event=emit_event,
    )


def run_batch(
    adapters: RuntimeAdapters,
    *,
    api_key: str,
    max_duration_seconds: int = MAX_RUNTIME_SECONDS,
) -> JobOutcome:
    """Run one FI-1 batch without persisting source or provider evidence."""
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required")
    if (
        isinstance(max_duration_seconds, bool)
        or not isinstance(max_duration_seconds, int)
        or not 1 <= max_duration_seconds <= MAX_RUNTIME_SECONDS
    ):
        raise ValueError("FI-1 runtime must be between 1 and 3600 seconds")

    started = adapters.monotonic()
    deadline = started + max_duration_seconds
    counters = {
        "symbols": 0,
        "candidates": 0,
        "skipped": 0,
        "inserted": 0,
        "updated": 0,
        "failed": 0,
        "attempts": 0,
    }
    adapters.emit_event("ingestion.fi1", "started")
    try:
        existing = adapters.read_existing()
    except Exception as error:
        adapters.emit_event(
            "ingestion.fi1.state", "failed", error_class=type(error).__name__
        )
        raise RuntimeError("FI-1 state read failed") from None
    _remaining(deadline, adapters.monotonic)
    try:
        selector_html = adapters.fetch_text(
            SELECTOR_URL,
            min(SOURCE_TIMEOUT_SECONDS, _remaining(deadline, adapters.monotonic)),
        )
        symbols = parse_selector_symbols(selector_html)
    except JobDeadlineExceeded:
        raise
    except Exception as error:
        adapters.emit_event(
            "ingestion.fi1.selector", "failed", error_class=type(error).__name__
        )
        raise RuntimeError("FI-1 selector discovery failed") from None
    _remaining(deadline, adapters.monotonic)
    counters["symbols"] = len(symbols)

    def load_symbol_page(symbol: str) -> tuple[AnnualCandidate, ...]:
        timeout = _remaining(deadline, adapters.monotonic)
        html = adapters.fetch_text(
            richbourse_symbol_page_url(symbol), min(SOURCE_TIMEOUT_SECONDS, timeout)
        )
        return parse_annual_candidates(html, symbol, limit=MAX_ANNUAL_CANDIDATES)

    candidates_by_symbol: dict[str, tuple[AnnualCandidate, ...]] = {}
    with ThreadPoolExecutor(max_workers=MAX_PAGE_CONCURRENCY) as executor:
        futures = {executor.submit(load_symbol_page, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                candidates_by_symbol[symbol] = future.result()
            except JobDeadlineExceeded:
                raise
            except Exception as error:
                counters["failed"] += 1
                adapters.emit_event(
                    "ingestion.fi1.symbol_page", "failed", error_class=type(error).__name__
                )
    candidates = [
        candidate
        for symbol in symbols
        for candidate in candidates_by_symbol.get(symbol, ())
    ]
    _remaining(deadline, adapters.monotonic)
    counters["candidates"] = len(candidates)

    rows: list[dict[str, Any]] = []
    run_id = "fi1_" + uuid4().hex
    for candidate in candidates:
        _remaining(deadline, adapters.monotonic)
        current_link = existing.get((candidate.symbol, candidate.fiscal_year))
        state = decide_row_state(
            existing_document_link=current_link,
            candidate_document_link=candidate.document_link,
            extraction_succeeded=True,
        )
        if state is RowDecision.SKIP:
            counters["skipped"] += 1
            continue
        try:
            pdf = adapters.download_pdf(
                candidate.document_link,
                min(SOURCE_TIMEOUT_SECONDS, _remaining(deadline, adapters.monotonic)),
            )
            extraction = _extract_candidate(
                candidate, pdf, adapters, api_key, deadline, counters
            )
            if extraction is None:
                counters["failed"] += 1
                continue
            decision = decide_row_state(
                existing_document_link=current_link,
                candidate_document_link=candidate.document_link,
                extraction_succeeded=True,
            )
            if decision in {RowDecision.INSERT, RowDecision.REPLACE}:
                values = extraction.as_dict()
                rows.append(
                    {
                        "symbol": candidate.symbol,
                        "fiscal_year": candidate.fiscal_year,
                        **{key: values[key] for key in _FINANCIAL_VALUE_KEYS},
                        "document_link": candidate.document_link,
                        "collected_at": adapters.utcnow().astimezone(timezone.utc).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    }
                )
                counters["inserted" if decision is RowDecision.INSERT else "updated"] += 1
        except JobDeadlineExceeded:
            raise
        except Exception as error:
            counters["failed"] += 1
            adapters.emit_event(
                "ingestion.fi1.report", "failed", error_class=type(error).__name__
            )

    completion: Mapping[str, Any] | None = None
    if rows:
        _remaining(deadline, adapters.monotonic)
        fingerprint = adapters.write_rows(rows, run_id)
        _remaining(deadline, adapters.monotonic)
        if (
            not isinstance(fingerprint, str)
            or re.fullmatch(r"[a-f0-9]{64}", fingerprint) is None
        ):
            raise RuntimeError("FI-1 writer returned no managed commit receipt")
        if counters["failed"] == 0:
            completion = adapters.completion(fingerprint)
    adapters.emit_event("ingestion.fi1.batch", "completed", count=len(rows))
    adapters.emit_event("ingestion.fi1.skipped", "completed", count=counters["skipped"])
    adapters.emit_event("ingestion.fi1.failed", "completed", count=counters["failed"])
    if completion is not None:
        adapters.emit_event("ingestion.fi1.completion", "succeeded")
    return JobOutcome(
        discovered_symbols=counters["symbols"],
        annual_candidates=counters["candidates"],
        skipped=counters["skipped"],
        inserted=counters["inserted"],
        updated=counters["updated"],
        failed=counters["failed"],
        model_attempts=counters["attempts"],
        completion=completion,
    )


def _extract_candidate(
    candidate: AnnualCandidate,
    pdf: bytes,
    adapters: RuntimeAdapters,
    api_key: str,
    deadline: float,
    counters: dict[str, int],
) -> ValidatedExtraction | None:
    document_text = adapters.prepare_document(pdf)
    for model in MODEL_ORDER:
        timeout = min(PROVIDER_TIMEOUT_SECONDS, _remaining(deadline, adapters.monotonic))
        counters["attempts"] += 1
        try:
            payload = adapters.provider_attempt(document_text, model, api_key, timeout)
            extraction = validate_extraction(
                payload, source_fiscal_year=candidate.fiscal_year
            )
            if not any(getattr(extraction, key) is not None for key in _FINANCIAL_VALUE_KEYS):
                raise ValueError("provider result has no usable financial values")
            adapters.emit_event("ingestion.fi1.provider", "succeeded")
            return extraction
        except JobDeadlineExceeded:
            raise
        except Exception as error:
            adapters.emit_event(
                "ingestion.fi1.provider",
                "failed",
                error_class=type(error).__name__,
            )
    return None


def main() -> None:
    """Cloud Run Job command entrypoint."""
    import google.auth

    credentials, project_id = google.auth.default()
    del credentials
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", project_id)
    if not project_id:
        raise ValueError("Google Cloud project configuration is required")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required")
    adapters = _default_adapters(project_id, os.environ.get("FINANCIALS_DATASET", "stocks"))
    outcome = run_batch(
        adapters,
        api_key=api_key,
    )
    print(json.dumps(outcome.as_dict(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
