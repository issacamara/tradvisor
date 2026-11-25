"""Bounded, in-memory runtime for the FI-1 financial ingestion job."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Real
from uuid import uuid4
from typing import Any, Callable, Mapping, Sequence

from .fi1_source import (
    SELECTOR_URL,
    SOURCE_TIMEOUT_SECONDS,
    _download_pdf,
    _fetch_text,
    _page_fiscal_years,
    _page_publication_years,
    _page_signature,
    parse_annual_candidates,
    parse_selector_symbols,
    richbourse_symbol_page_url_for_page,
)
from .fi1_source import (
    RICHBOURSE_ORIGIN,
    _ANNUAL_TERMS,
    _DATE,
    _INTERIM_TERMS,
    _YEAR,
    _get_response,
    _plain_text,
    _publication_year,
    is_approved_document_url,
    richbourse_symbol_page_url,
)
from .fi1_extraction import (
    MODEL_ORDER,
    PROVIDER_TIMEOUT_SECONDS,
    _FINANCIAL_VALUE_KEYS,
    _error_class,
    _pdf_text,
    _provider_attempt,
    validate_extraction,
)
from .fi1_extraction import (
    EXTRACTION_KEYS,
    OPENROUTER_URL,
    OWNER_EXTRACTION_PROMPT,
    ProviderHTTPError,
)
from .fi1_config import (
    MAX_ANNUAL_CANDIDATES,
    MAX_PAGE_CONCURRENCY,
    MAX_RUNTIME_SECONDS,
    RuntimeConfiguration,
    SOURCE_PACING_SECONDS,
)
from .fi1_config import RUNTIME_TARGET

# Names moved to the fi1_* modules; kept importable from here for callers and tests.
__all__ = [
    "EXTRACTION_KEYS",
    "OPENROUTER_URL",
    "OWNER_EXTRACTION_PROMPT",
    "ProviderHTTPError",
    "RICHBOURSE_ORIGIN",
    "RUNTIME_TARGET",
    "_ANNUAL_TERMS",
    "_DATE",
    "_INTERIM_TERMS",
    "_YEAR",
    "_get_response",
    "_plain_text",
    "_publication_year",
    "is_approved_document_url",
    "richbourse_symbol_page_url",
]


_LOG_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
_SENSITIVE_LOG_TOKEN = re.compile(
    r"authorization|bearer|token|password|secret|api[_-]?key|email|uid|identifier|body",
    re.IGNORECASE,
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
    completion: Callable[[Sequence[str]], Mapping[str, Any]]
    monotonic: Callable[[], float] = time.monotonic
    utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def _remaining(deadline: float, monotonic: Callable[[], float]) -> float:
    value = deadline - monotonic()
    if value <= 0:
        print("FI-1 execution deadline exceeded", flush=True)
        raise JobDeadlineExceeded("FI-1 runtime deadline exceeded")
    return value


def _safe_log_token(value: str) -> str:
    if (
        not value
        or _LOG_TOKEN.fullmatch(value) is None
        or _SENSITIVE_LOG_TOKEN.search(value)
    ):
        return "redacted"
    return value


def _log_stage_failure(stage: str, error: Exception) -> None:
    print(f"FI-1 {stage} failed ({_safe_log_token(_error_class(error))})", flush=True)


def _default_adapters(
    project_id: str, dataset: str, environment: str
) -> RuntimeAdapters:
    from google.cloud import bigquery
    from ingestion_observability import managed_import_completion

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

    return RuntimeAdapters(
        fetch_text=_fetch_text,
        download_pdf=_download_pdf,
        prepare_document=_pdf_text,
        provider_attempt=_provider_attempt,
        read_existing=read_existing,
        write_rows=write_rows,
        completion=lambda fingerprints: managed_import_completion("financials", fingerprints),
    )


def run_batch(
    adapters: RuntimeAdapters,
    *,
    api_key: str,
    max_duration_seconds: int = MAX_RUNTIME_SECONDS,
    model_order: Sequence[str] = MODEL_ORDER,
    max_page_concurrency: int = MAX_PAGE_CONCURRENCY,
    max_annual_candidates: int = MAX_ANNUAL_CANDIDATES,
    selection_mode: str = "historical",
) -> JobOutcome:
    """Run one FI-1 batch without persisting source or provider evidence."""
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required")
    if not isinstance(selection_mode, str) or selection_mode not in {
        "historical", "previous_year", "publication_year"
    }:
        raise ValueError("FI-1 selection mode must be historical, previous_year, or publication_year")
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

    return _run_batch(
        adapters,
        api_key=api_key,
        max_duration_seconds=max_duration_seconds,
        model_order=model_order,
        max_page_concurrency=max_page_concurrency,
        max_annual_candidates=max_annual_candidates,
        selection_mode=selection_mode,
    )


def _run_batch(
    adapters: RuntimeAdapters,
    *,
    api_key: str,
    max_duration_seconds: int,
    model_order: Sequence[str],
    max_page_concurrency: int,
    max_annual_candidates: int,
    selection_mode: str,
) -> JobOutcome:
    current_year = adapters.utcnow().astimezone(timezone.utc).year
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
    try:
        existing = dict(adapters.read_existing())
    except Exception as error:
        _log_stage_failure("state", error)
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
        _log_stage_failure("selector", error)
        raise RuntimeError("FI-1 selector discovery failed") from None
    _remaining(deadline, adapters.monotonic)
    counters["symbols"] = len(symbols)

    symbol_page_requests = 0

    def load_symbol_pages(symbol: str) -> tuple[dict[str, Any], ...]:
        nonlocal symbol_page_requests
        found: list[dict[str, Any]] = []
        seen_pages: set[str] = set()
        seen_years: set[int] = set()
        page = 1
        while True:
            if symbol_page_requests:
                time.sleep(SOURCE_PACING_SECONDS)
            timeout = _remaining(deadline, adapters.monotonic)
            html = adapters.fetch_text(
                richbourse_symbol_page_url_for_page(symbol, page),
                min(SOURCE_TIMEOUT_SECONDS, timeout),
            )
            symbol_page_requests += 1
            signature = _page_signature(html)
            if not signature or signature in seen_pages:
                break
            seen_pages.add(signature)
            page_candidates = parse_annual_candidates(
                html,
                symbol,
                current_year=current_year,
                limit=max_annual_candidates,
                selection_mode=selection_mode,
            )
            if selection_mode == "publication_year":
                for candidate in page_candidates:
                    if all(candidate["document_link"] != item["document_link"] for item in found):
                        found.append(candidate)
                years = _page_publication_years(html)
                if years and min(years) < current_year:
                    break
            else:
                for candidate in page_candidates:
                    year = int(candidate["fiscal_year"])
                    if year not in seen_years:
                        seen_years.add(year)
                        found.append(candidate)
                years = _page_fiscal_years(html)
                cutoff = current_year - (1 if selection_mode == "previous_year" else 5)
                if years and min(years) < cutoff:
                    break
                if len(found) >= max_annual_candidates:
                    break
            page += 1
        if selection_mode == "publication_year":
            return tuple(found)
        return tuple(
            sorted(found, key=lambda candidate: int(candidate["fiscal_year"]), reverse=True)[
                :max_annual_candidates
            ]
        )

    rows: list[dict[str, Any]] = []
    pending_counts = {"inserted": 0, "updated": 0}
    receipts: list[str] = []
    terminal_symbols = 0

    def flush() -> None:
        nonlocal rows
        if not rows:
            return
        try:
            _remaining(deadline, adapters.monotonic)
            run_id = "fi1_" + uuid4().hex
            fingerprint = adapters.write_rows(rows, run_id)
            _remaining(deadline, adapters.monotonic)
            if not isinstance(fingerprint, str) or re.fullmatch(r"[a-f0-9]{64}", fingerprint) is None:
                raise RuntimeError("FI-1 writer returned no managed commit receipt")
        except JobDeadlineExceeded:
            raise
        except Exception as error:
            _log_stage_failure("writer", error)
            raise
        receipts.append(fingerprint)
        print(
            "FI-1 batch committed: "
            f"inserted={pending_counts['inserted']} updated={pending_counts['updated']}",
            flush=True,
        )
        counters["inserted"] += pending_counts["inserted"]
        counters["updated"] += pending_counts["updated"]
        for row in rows:
            existing[(str(row["symbol"]), int(row["fiscal_year"]))] = str(row["document_link"])
        rows = []
        pending_counts["inserted"] = 0
        pending_counts["updated"] = 0

    for symbol in symbols:
        _remaining(deadline, adapters.monotonic)
        symbol_rows: list[dict[str, Any]] = []
        symbol_counts = {"inserted": 0, "updated": 0}
        symbol_failed = False
        candidate_failed = False
        symbol_error: Exception | None = None
        symbol_error_class: str | None = None
        failure_classes: list[str] = []
        try:
            candidates = load_symbol_pages(symbol)
            counters["candidates"] += len(candidates)
        except JobDeadlineExceeded:
            raise
        except Exception as error:
            counters["failed"] += 1
            candidates = ()
            symbol_failed = True
            symbol_error = error

        for candidate in candidates:
            _remaining(deadline, adapters.monotonic)
            symbol = candidate["symbol"]
            fiscal_year = candidate["fiscal_year"]
            document_link = candidate["document_link"]
            current_link = existing.get((symbol, fiscal_year))
            if current_link == document_link:
                counters["skipped"] += 1
                continue
            try:
                pdf = adapters.download_pdf(
                    document_link,
                    min(SOURCE_TIMEOUT_SECONDS, _remaining(deadline, adapters.monotonic)),
                )
                extraction = _extract_candidate(
                    candidate, pdf, adapters, api_key, deadline, counters, model_order,
                    failure_class=failure_classes,
                )
                if extraction is None:
                    candidate_failed = True
                    if selection_mode != "publication_year":
                        counters["failed"] += 1
                        symbol_failed = True
                    symbol_error_class = failure_classes[-1] if failure_classes else None
                    continue
                symbol_rows.append(
                    {
                        "symbol": symbol,
                        "fiscal_year": fiscal_year,
                        **{key: extraction[key] for key in _FINANCIAL_VALUE_KEYS},
                        "document_link": document_link,
                        "collected_at": adapters.utcnow().astimezone(timezone.utc),
                    }
                )
                symbol_counts["inserted" if current_link is None else "updated"] += 1
                if selection_mode == "publication_year":
                    symbol_error = None
                    symbol_error_class = None
                    break
            except JobDeadlineExceeded:
                raise
            except Exception as error:
                candidate_failed = True
                if selection_mode != "publication_year":
                    counters["failed"] += 1
                    symbol_failed = True
                symbol_error = error

        if selection_mode == "publication_year" and candidate_failed and not symbol_rows:
            counters["failed"] += 1
            symbol_failed = True

        if not symbol_failed:
            rows.extend(symbol_rows)
            pending_counts["inserted"] += symbol_counts["inserted"]
            pending_counts["updated"] += symbol_counts["updated"]
        outcome = "failed" if symbol_failed else "succeeded"
        error_class = symbol_error_class or (
            _error_class(symbol_error) if symbol_error is not None else None
        )
        suffix = f" ({_safe_log_token(error_class)})" if error_class else ""
        print(f"FI-1 symbol {_safe_log_token(symbol)}: {outcome}{suffix}", flush=True)
        terminal_symbols += 1
        if terminal_symbols % 10 == 0:
            flush()
    flush()

    completion: Mapping[str, Any] | None = None
    if receipts and counters["failed"] == 0:
        try:
            completion = adapters.completion(tuple(receipts))
        except Exception as error:
            _log_stage_failure("completion", error)
            raise
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
    candidate: Mapping[str, Any],
    pdf: bytes,
    adapters: RuntimeAdapters,
    api_key: str,
    deadline: float,
    counters: dict[str, int],
    model_order: Sequence[str] = MODEL_ORDER,
    failure_class: list[str] | None = None,
) -> dict[str, Real | int | None] | None:
    document_text = adapters.prepare_document(pdf)
    for model in model_order:
        timeout = min(PROVIDER_TIMEOUT_SECONDS, _remaining(deadline, adapters.monotonic))
        counters["attempts"] += 1
        try:
            payload = adapters.provider_attempt(document_text, model, api_key, timeout)
            extraction = validate_extraction(
                payload, source_fiscal_year=candidate["fiscal_year"]
            )
            if not any(extraction[key] is not None for key in _FINANCIAL_VALUE_KEYS):
                raise ValueError("provider result has no usable financial values")
            return extraction
        except JobDeadlineExceeded:
            raise
        except Exception as error:
            if failure_class is not None:
                failure_class.append(_error_class(error))
            continue
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
    try:
        configuration = RuntimeConfiguration.from_environment()
    except ValueError as error:
        # Configuration validation errors use fixed, non-secret messages that
        # identify the rejected setting. Keep the detail bounded for job logs.
        detail = str(error).replace("\n", " ").replace("\r", " ")[:160]
        print(f"FI-1 configuration failed: {detail}")
        raise SystemExit(1) from None
    except Exception:
        print("FI-1 configuration failed")
        raise SystemExit(1) from None
    if args.check_config:
        print(json.dumps(configuration.public_summary(), separators=(",", ":"), sort_keys=True))
        return
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("FI-1 configuration failed")
        raise SystemExit(1)
    try:
        adapters = _default_adapters(
            configuration.project_id, configuration.dataset, configuration.environment
        )
    except Exception:
        print("FI-1 runtime initialization failed")
        raise SystemExit(1) from None
    try:
        run_batch(
            adapters,
            api_key=api_key,
            model_order=configuration.model_order,
            max_page_concurrency=configuration.max_concurrent_requests,
            max_annual_candidates=configuration.max_reports_per_symbol,
            selection_mode=configuration.selection_mode,
        )
    except Exception:
        # Stage-specific, sanitized messages are emitted inside run_batch.
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
