"""Bounded, in-memory runtime for the FI-1 financial ingestion job."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence, TypeVar
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
EXECUTION_LEASE_SECONDS = 300
EXECUTION_LEASE_RENEW_SECONDS = 60
MAX_PAGE_CONCURRENCY = 4
MAX_ANNUAL_CANDIDATES = 5
RUNTIME_TARGET = "financial_ingestion_job"
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


class ActiveExecutionError(RuntimeError):
    """Another FI-1 process currently owns the bounded execution lease."""


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Validated non-secret settings supplied by the Terraform-managed job."""

    project_id: str
    dataset: str
    financials_table: str
    staging_table: str
    model_order: tuple[str, ...]
    max_concurrent_requests: int
    max_reports_per_symbol: int

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "RuntimeConfiguration":
        values = os.environ if environ is None else environ
        if values.get("TRADVISOR_RUNTIME_TARGET") != RUNTIME_TARGET:
            raise ValueError("TRADVISOR_RUNTIME_TARGET must select the FI-1 job")
        project_id = values.get("TRADVISOR_TARGET_PROJECT_ID", "")
        if not project_id or values.get("TRADVISOR_ENVIRONMENT_PROJECT_ID") != project_id:
            raise ValueError("FI-1 target and environment projects must match")
        if values.get("GOOGLE_CLOUD_PROJECT") != project_id:
            raise ValueError("Google Cloud project must match the FI-1 target project")
        dataset = values.get("TRADVISOR_INGESTION_DATASET", "")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", dataset) is None:
            raise ValueError("invalid financial dataset configuration")

        prefix = f"{project_id}.{dataset}."
        if values.get("TRADVISOR_INGESTION_COMPANIES_TABLE") != prefix + "brvm_companies":
            raise ValueError("FI-1 company table does not match its managed dataset")
        financials_table = values.get("TRADVISOR_INGESTION_FINANCIALS_TABLE", "")
        staging_table = values.get("TRADVISOR_INGESTION_FINANCIALS_STAGING_TABLE", "")
        if financials_table != prefix + "financials":
            raise ValueError("FI-1 financial table does not match its managed dataset")
        if staging_table != prefix + "financials_staging":
            raise ValueError("FI-1 staging table does not match its managed dataset")

        primary = values.get("TRADVISOR_FINANCIALS_MODEL_PRIMARY", "")
        fallbacks = tuple(
            item.strip()
            for item in values.get("TRADVISOR_FINANCIALS_MODEL_FALLBACKS", "").split(",")
            if item.strip()
        )
        model_order = (primary, *fallbacks)
        if not primary or len(set(model_order)) != len(model_order):
            raise ValueError("FI-1 model configuration must contain unique ordered models")

        def bounded_integer(name: str, *, minimum: int, maximum: int) -> int:
            value = values.get(name, "")
            if not value.isdecimal():
                raise ValueError(f"{name} must be an integer")
            parsed = int(value)
            if not minimum <= parsed <= maximum:
                raise ValueError(f"{name} is outside its approved bounds")
            return parsed

        bounded_integer("TRADVISOR_FINANCIALS_MAX_ATTEMPTS_PER_MODEL", minimum=1, maximum=1)
        return cls(
            project_id=project_id,
            dataset=dataset,
            financials_table=financials_table,
            staging_table=staging_table,
            model_order=model_order,
            max_concurrent_requests=bounded_integer(
                "TRADVISOR_FINANCIALS_MAX_CONCURRENT_REQUESTS",
                minimum=1,
                maximum=MAX_PAGE_CONCURRENCY,
            ),
            max_reports_per_symbol=bounded_integer(
                "TRADVISOR_FINANCIALS_MAX_REPORTS_PER_SYMBOL",
                minimum=1,
                maximum=MAX_ANNUAL_CANDIDATES,
            ),
        )

    def public_summary(self) -> dict[str, Any]:
        """Return non-secret settings for container configuration smoke checks."""
        return {
            "runtime_target": RUNTIME_TARGET,
            "project_id": self.project_id,
            "dataset": self.dataset,
            "financials_table": self.financials_table,
            "staging_table": self.staging_table,
            "model_order": list(self.model_order),
            "max_concurrent_requests": self.max_concurrent_requests,
            "max_reports_per_symbol": self.max_reports_per_symbol,
        }


T = TypeVar("T")


class FirestoreExecutionLease(AbstractContextManager):
    """Short Firestore transaction lease; only a random owner and expiry persist."""

    def __init__(
        self,
        transact: Callable[[Callable[[Any], T]], T],
        document: Any,
        *,
        lease_seconds: int = EXECUTION_LEASE_SECONDS,
        renew_seconds: int = EXECUTION_LEASE_RENEW_SECONDS,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        token: str | None = None,
    ) -> None:
        if not 1 <= lease_seconds <= 600 or not 1 <= renew_seconds < lease_seconds:
            raise ValueError("FI-1 lease bounds are invalid")
        self._transact = transact
        self._document = document
        self._lease_seconds = lease_seconds
        self._renew_seconds = renew_seconds
        self._utcnow = utcnow
        self._token = token or uuid4().hex
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._heartbeat: threading.Thread | None = None

    def _transition(self, *, acquire: bool = False, release: bool = False) -> bool:
        now = self._utcnow().astimezone(timezone.utc)

        def update(transaction: Any) -> bool:
            snapshot = self._document.get(transaction=transaction)
            current = snapshot.to_dict() if snapshot.exists else None
            owner = current.get("owner") if isinstance(current, Mapping) else None
            expiry = current.get("expires_at") if isinstance(current, Mapping) else None
            if release:
                if owner != self._token:
                    return False
                transaction.delete(self._document)
                return True
            if acquire and owner not in (None, self._token):
                if not isinstance(expiry, datetime) or expiry > now:
                    return False
            if not acquire and owner != self._token:
                return False
            transaction.set(
                self._document,
                {"owner": self._token, "expires_at": now + timedelta(seconds=self._lease_seconds)},
            )
            return True

        return self._transact(update)

    def __enter__(self) -> "FirestoreExecutionLease":
        if not self._transition(acquire=True):
            raise ActiveExecutionError("another FI-1 execution is active")
        self._heartbeat = threading.Thread(
            target=self._renew_loop, name="fi1-lease-renewal", daemon=True
        )
        self._heartbeat.start()
        return self

    def _renew_loop(self) -> None:
        while not self._stop.wait(self._renew_seconds):
            try:
                if not self._transition():
                    self._lost.set()
                    return
            except Exception:
                self._lost.set()
                return

    def assert_owned(self) -> None:
        if self._lost.is_set() or not self._transition():
            self._lost.set()
            raise ActiveExecutionError("FI-1 execution lease was lost")

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._stop.set()
        if self._heartbeat is not None:
            self._heartbeat.join(timeout=self._renew_seconds + 1)
        try:
            self._transition(release=True)
        except Exception:
            if exc is None:
                raise


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
    execution_lease: Callable[[], AbstractContextManager[Any]] | None = None
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
        revision_frame = None
        archive = lambda: None
        return upsert_financials_and_archive(
            frame,
            revision_frame,
            project_id,
            dataset,
            archive,
            run_id=run_id,
        )

    def execution_lease() -> FirestoreExecutionLease:
        from google.cloud import firestore

        client = firestore.Client(project=project_id)
        document = client.document("pipeline_control/fi1_financial_ingestion")

        def transact(callback: Callable[[Any], T]) -> T:
            transaction = client.transaction()

            @firestore.transactional
            def run(active_transaction: Any) -> T:
                return callback(active_transaction)

            return run(transaction)

        return FirestoreExecutionLease(transact, document)

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
        execution_lease=execution_lease,
    )


def run_batch(
    adapters: RuntimeAdapters,
    *,
    api_key: str,
    max_duration_seconds: int = MAX_RUNTIME_SECONDS,
    model_order: Sequence[str] = MODEL_ORDER,
    max_page_concurrency: int = MAX_PAGE_CONCURRENCY,
    max_annual_candidates: int = MAX_ANNUAL_CANDIDATES,
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
    if not 1 <= max_page_concurrency <= MAX_PAGE_CONCURRENCY:
        raise ValueError("FI-1 request concurrency must be between 1 and 4")
    if not 1 <= max_annual_candidates <= MAX_ANNUAL_CANDIDATES:
        raise ValueError("FI-1 reports per symbol must be between 1 and 5")
    if not model_order or len(set(model_order)) != len(model_order):
        raise ValueError("FI-1 model order must contain unique models")

    lease = adapters.execution_lease() if adapters.execution_lease is not None else None
    if lease is not None:
        with lease:
            return _run_batch(
                adapters,
                api_key=api_key,
                max_duration_seconds=max_duration_seconds,
                model_order=model_order,
                max_page_concurrency=max_page_concurrency,
                max_annual_candidates=max_annual_candidates,
                lease=lease,
            )
    return _run_batch(
        adapters,
        api_key=api_key,
        max_duration_seconds=max_duration_seconds,
        model_order=model_order,
        max_page_concurrency=max_page_concurrency,
        max_annual_candidates=max_annual_candidates,
        lease=None,
    )


def _run_batch(
    adapters: RuntimeAdapters,
    *,
    api_key: str,
    max_duration_seconds: int,
    model_order: Sequence[str],
    max_page_concurrency: int,
    max_annual_candidates: int,
    lease: FirestoreExecutionLease | None,
) -> JobOutcome:
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
        return parse_annual_candidates(html, symbol, limit=max_annual_candidates)

    candidates_by_symbol: dict[str, tuple[AnnualCandidate, ...]] = {}
    with ThreadPoolExecutor(max_workers=max_page_concurrency) as executor:
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
        if lease is not None:
            lease.assert_owned()
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
                candidate, pdf, adapters, api_key, deadline, counters, model_order
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
        if lease is not None:
            lease.assert_owned()
        _remaining(deadline, adapters.monotonic)
        fingerprint = adapters.write_rows(rows, run_id)
        _remaining(deadline, adapters.monotonic)
        if (
            not isinstance(fingerprint, str)
            or re.fullmatch(r"[a-f0-9]{64}", fingerprint) is None
        ):
            raise RuntimeError("FI-1 writer returned no managed commit receipt")
        if counters["failed"] == 0:
            if lease is not None:
                lease.assert_owned()
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
    model_order: Sequence[str] = MODEL_ORDER,
) -> ValidatedExtraction | None:
    document_text = adapters.prepare_document(pdf)
    for model in model_order:
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


def main(argv: Sequence[str] | None = None) -> None:
    """Cloud Run Job command entrypoint."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate injected non-secret runtime settings without starting the job",
    )
    args = parser.parse_args(argv)
    configuration = RuntimeConfiguration.from_environment()
    if args.check_config:
        print(json.dumps(configuration.public_summary(), separators=(",", ":"), sort_keys=True))
        return
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required")
    adapters = _default_adapters(configuration.project_id, configuration.dataset)
    outcome = run_batch(
        adapters,
        api_key=api_key,
        model_order=configuration.model_order,
        max_page_concurrency=configuration.max_concurrent_requests,
        max_annual_candidates=configuration.max_reports_per_symbol,
    )
    print(json.dumps(outcome.as_dict(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
