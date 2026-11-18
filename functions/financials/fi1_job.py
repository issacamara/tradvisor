"""Bounded, in-memory runtime for the FI-1 financial ingestion job."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import json
import os
import re
import time
from typing import Any, Callable, Mapping, Sequence
import unicodedata
from numbers import Real
from urllib.parse import quote, urljoin, urlparse
from uuid import uuid4

SELECTOR_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
RICHBOURSE_ORIGIN = "https://www.richbourse.com"
EXTRACTION_KEYS = (
    "fiscal_year",
    "revenue",
    "net_income",
    "total_debt",
    "cash_and_cash_equivalents",
    "total_equity",
)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_INTERIM_TERMS = (
    "trimestre", "trimestriel", "semestr", "semester", "quarter", "half year",
    "six month", "mi-annee",
)
_ANNUAL_TERMS = (
    "annuel", "exercice", "etat financier", "etats financiers", "rapport annuel",
    "bilan annuel", "comptes annuels",
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ORDER = (
    "gemma-4-31b-it",
    "nvidia/nemotron-3.5-lightning:free",
    "openai/gpt-4o-mini",
)
OWNER_EXTRACTION_PROMPT = """You are a financial data extraction expert. Extract structured financial data from a BRVM annual financial statement PDF.

For each document, extract the following fields:

fiscal_year: The fiscal year of the report (e.g., 2024). Use the most recent year covered by the statement, not the publication date.

revenue: Generic operating revenue or "chiffre d'affaires" only. Never put bank net banking income ("produit net bancaire" / PNB), insurer premiums, interest income, or any category-specific activity measure in this field. Extract PNB separately as pnb. In local currency (XOF/FCFA), expressed in full units.

net_income: Net income or "résultat net" (résultat net de l'exercice). Use the net result attributable to the company (résultat net part du groupe if consolidated accounts are shown alongside company-only accounts, otherwise résultat net). In local currency, expressed in full units.

total_debt: Definition depends on company type:
  - For NON-FINANCIAL companies (industrial, commercial, services, utilities): use total financial/interest-bearing debt — "dettes financières", "emprunts et dettes financières", or total dettes (excluding trade payables/fournisseurs and other non-financial liabilities when itemized separately). If only "total passif" is available with no breakdown, use total passif minus capitaux propres.
  - For BANKS and financial institutions: "total_debt" does not follow the standard corporate definition. Instead, use the sum of interest-bearing liabilities to third parties, typically composed of: "dettes envers les établissements de crédit" (interbank borrowings), "dettes envers la clientèle" (customer deposits), and "emprunts obligataires et dettes rattachées" (bonds and related debt), if separately reported. If these line items are not individually broken out, use "total dettes" or "total passif" (excluding "capitaux propres" and "provisions techniques" for insurers) as a fallback. Do not include "capitaux propres", "provisions pour risques et charges", or off-balance-sheet commitments in this figure.
  - For INSURANCE companies: use total technical and financial liabilities excluding equity — primarily "provisions techniques" plus any interest-bearing debt, if the breakdown is available; otherwise use total passif minus capitaux propres.
  In local currency, expressed in full units.

cash_and_cash_equivalents: Cash and cash equivalents — "trésorerie", "trésorerie et équivalents de trésorerie", or "disponibilités". For banks, this may appear as "caisse, banques centrales" or "trésorerie active" — use that if the standard line is absent. In local currency, expressed in full units.

total_equity: Total equity — "capitaux propres" or "capitaux propres part du groupe" (total, including reserves, capital, and retained earnings — "report à nouveau"). In local currency, expressed in full units.

symbol: The first 4 or 5 letters of the document name (before the "_" character).

CRITICAL — DETECT COMPANY TYPE FIRST:
Before extracting total_debt, determine whether the document is a bank/financial institution, an insurance company, or a non-financial (corporate) company, based on the statement structure, sector references, or company name (e.g., BOA, SGBCI, NSIA, SONIBANK are banks/insurers; industrial or commercial names like SONATEL, NESTLE, SOLIBRA are non-financial). Apply the matching total_debt definition above.

CRITICAL — UNIT NORMALIZATION:
Financial statements often present figures in thousands, millions, or billions of XOF, with the unit noted near the table header or in a footnote (e.g., "en milliers de FCFA", "en millions de FCFA", "montants exprimés en milliers d'unités monétaires"). You MUST detect this unit and convert every extracted monetary value into full base units (i.e., the actual FCFA amount) before returning it. Examples:
- If the statement says "en milliers de FCFA" and shows 12 345, the actual value is 12345000.
- If the statement says "en millions de FCFA" and shows 12, the actual value is 12000000.
- If the statement says "en milliards de FCFA" and shows 1.2, the actual value is 1200000000.
- If no unit is specified, assume the figures are already in full units (do not scale).
Apply the detected scale factor consistently to ALL five monetary fields (revenue, net_income, total_debt, cash_and_cash_equivalents, total_equity) — do not mix scales within the same document. Double-check that the final numbers are plausible in magnitude for a BRVM-listed company (typically hundreds of millions to hundreds of billions of FCFA).

Instructions for each document:
- The documents are from companies listed on the BRVM (Bourse Régionale des Valeurs Mobilières), West Africa, and prepared under SYSCOHADA révisé / BCEAO-PCB norms.
- The documents may be in French — look for: "chiffre d'affaires", "résultat net", "trésorerie", "capitaux propres", "dettes", "passifs", along with the unit disclosure (milliers/millions/milliards).
- Extract the most recent fiscal year's data (usually the first/leftmost column in the balance sheet and income statement).
- If a field is not found, use null — do not guess or estimate.
- Do not include any explanation or text outside the output.

Output format:\x20
{
  "fiscal_year": <integer or null>,
  "revenue": <number or null>,
  "net_income": <number or null>,
  "total_debt": <number or null>,
  "cash_and_cash_equivalents": <number or null>,
  "total_equity": <number or null>
}

"""
MAX_RUNTIME_SECONDS = 60 * 60
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
_LOG_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
_SENSITIVE_LOG_TOKEN = re.compile(
    r"authorization|bearer|token|password|secret|api[_-]?key|email|uid|identifier|body",
    re.IGNORECASE,
)


def _plain_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def parse_selector_symbols(html: str) -> tuple[str, ...]:
    from bs4 import BeautifulSoup

    selector = BeautifulSoup(html, "html.parser").find("select", id="symbole")
    if selector is None:
        raise ValueError("RichBourse symbol selector is missing")
    return tuple(
        dict.fromkeys(
            value
            for option in selector.find_all("option")
            if (value := (option.get("value") or "").strip())
        )
    )


def richbourse_symbol_page_url(symbol: str) -> str:
    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol is required")
    return f"{SELECTOR_URL}?symbole={quote(symbol, safe='')}"


def is_approved_document_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.casefold() == "https"
            and parsed.hostname is not None
            and parsed.hostname.casefold() == "www.richbourse.com"
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def parse_annual_candidates(
    html: str,
    symbol: str,
    *,
    current_year: int,
    limit: int = 5,
    selection_mode: str = "historical",
) -> tuple[dict[str, Any], ...]:
    from bs4 import BeautifulSoup

    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol is required")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if not isinstance(selection_mode, str) or selection_mode not in {
        "historical", "previous_year"
    }:
        raise ValueError("selection_mode must be 'historical' or 'previous_year'")

    soup = BeautifulSoup(html, "html.parser")
    by_year: dict[int, dict[str, Any]] = {}
    for row in soup.select("div.ligne_paire, div.ligne_impaire"):
        link = row.find("a", href=True)
        if link is None:
            continue
        title = link.get_text(" ", strip=True)
        normalized = _plain_text(title)
        if any(term in normalized for term in _INTERIM_TERMS):
            continue
        if not any(term in normalized for term in _ANNUAL_TERMS):
            continue
        year_match = _YEAR.search(normalized)
        if year_match is None:
            continue

        document_link = urljoin(SELECTOR_URL, link["href"].strip())
        if not is_approved_document_url(document_link):
            continue
        year = int(year_match.group(1))
        if selection_mode == "previous_year":
            if year != current_year - 1:
                continue
        elif not current_year - 5 <= year < current_year:
            continue
        by_year.setdefault(
            year,
            {"symbol": symbol, "fiscal_year": year, "document_link": document_link},
        )

    return tuple(by_year[year] for year in sorted(by_year, reverse=True)[:limit])


def validate_extraction(
    payload: Mapping[str, object], *, source_fiscal_year: int
) -> dict[str, Real | int | None]:
    if not isinstance(payload, Mapping) or set(payload) != set(EXTRACTION_KEYS):
        raise ValueError("extraction must contain exactly the FI-1 keys")
    if (
        isinstance(source_fiscal_year, bool)
        or not isinstance(source_fiscal_year, int)
        or isinstance(payload["fiscal_year"], bool)
        or not isinstance(payload["fiscal_year"], int)
        or payload["fiscal_year"] != source_fiscal_year
    ):
        raise ValueError("extracted fiscal year does not match source metadata")

    values: dict[str, Real | int | None] = {"fiscal_year": source_fiscal_year}
    for key in EXTRACTION_KEYS[1:]:
        value = payload[key]
        if value is not None:
            try:
                finite = math.isfinite(value)
            except (OverflowError, TypeError, ValueError):
                finite = False
            if isinstance(value, bool) or not isinstance(value, Real) or not finite:
                raise ValueError("extraction values must be finite numbers or null")
        values[key] = value
    return values


class JobDeadlineExceeded(TimeoutError):
    """The configured job time budget was exhausted."""


class ProviderHTTPError(RuntimeError):
    """OpenRouter returned an HTTP failure with a safe status-only code."""

    def __init__(self, status_code: int) -> None:
        if not 100 <= status_code <= 599:
            raise ValueError("provider HTTP status is invalid")
        self.status_code = status_code
        super().__init__(f"ProviderHTTP{status_code}")


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Validated non-secret settings supplied by the Terraform-managed job."""

    project_id: str
    environment: str
    dataset: str
    financials_table: str
    staging_table: str
    model_order: tuple[str, ...]
    max_concurrent_requests: int
    max_reports_per_symbol: int
    selection_mode: str

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "RuntimeConfiguration":
        values = os.environ if environ is None else environ
        selection_mode = values.get("TRADVISOR_FINANCIALS_SELECTION_MODE", "historical")
        if not isinstance(selection_mode, str) or selection_mode not in {
            "historical",
            "previous_year",
        }:
            raise ValueError(
                "TRADVISOR_FINANCIALS_SELECTION_MODE must be historical or previous_year"
            )
        if values.get("TRADVISOR_RUNTIME_TARGET") != RUNTIME_TARGET:
            raise ValueError("TRADVISOR_RUNTIME_TARGET must select the FI-1 job")
        environment = values.get("TRADVISOR_ENVIRONMENT", "")
        if environment not in {"development", "production"}:
            raise ValueError("TRADVISOR_ENVIRONMENT must be development or production")
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
            environment=environment,
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
            selection_mode=selection_mode,
        )

    def public_summary(self) -> dict[str, Any]:
        """Return non-secret settings for container configuration smoke checks."""
        return {
            "runtime_target": RUNTIME_TARGET,
            "environment": self.environment,
            "project_id": self.project_id,
            "dataset": self.dataset,
            "financials_table": self.financials_table,
            "staging_table": self.staging_table,
            "model_order": list(self.model_order),
            "max_concurrent_requests": self.max_concurrent_requests,
            "max_reports_per_symbol": self.max_reports_per_symbol,
            "selection_mode": self.selection_mode,
        }


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
            "messages": [
                {"role": "system", "content": OWNER_EXTRACTION_PROMPT},
                {"role": "user", "content": document_text},
            ],
        },
        timeout=timeout,
        impersonate="chrome",
        http_version=CurlHttpVersion.V1_1,
    )
    if response.status_code != 200:
        raise ProviderHTTPError(response.status_code)
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("provider result is not JSON text")
    result = json.loads(content)
    if not isinstance(result, Mapping):
        raise ValueError("provider result is not an object")
    return result


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
        "historical",
        "previous_year",
    }:
        raise ValueError("FI-1 selection mode must be historical or previous_year")
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

    def load_symbol_page(symbol: str) -> tuple[dict[str, Any], ...]:
        timeout = _remaining(deadline, adapters.monotonic)
        html = adapters.fetch_text(
            richbourse_symbol_page_url(symbol), min(SOURCE_TIMEOUT_SECONDS, timeout)
        )
        return parse_annual_candidates(
            html,
            symbol,
            current_year=current_year,
            limit=max_annual_candidates,
            selection_mode=selection_mode,
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
        symbol_error: Exception | None = None
        symbol_error_class: str | None = None
        failure_classes: list[str] = []
        try:
            candidates = load_symbol_page(symbol)
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
            except JobDeadlineExceeded:
                raise
            except Exception as error:
                counters["failed"] += 1
                symbol_failed = True
                symbol_error = error

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


def _error_class(error: Exception) -> str:
    if isinstance(error, ProviderHTTPError):
        return f"ProviderHTTP{error.status_code}"
    return type(error).__name__


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
