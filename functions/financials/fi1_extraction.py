"""Extraction prompt, provider call and result validation for the FI-1 job."""

from __future__ import annotations

import json
import math
from numbers import Real
from typing import Mapping


EXTRACTION_KEYS = (
    "fiscal_year",
    "revenue",
    "net_income",
    "total_debt",
    "cash_and_cash_equivalents",
    "total_equity",
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
PROVIDER_TIMEOUT_SECONDS = 120
_FINANCIAL_VALUE_KEYS = (
    "revenue",
    "net_income",
    "total_debt",
    "cash_and_cash_equivalents",
    "total_equity",
)


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


class ProviderHTTPError(RuntimeError):
    """OpenRouter returned an HTTP failure with a safe status-only code."""

    def __init__(self, status_code: int) -> None:
        if not 100 <= status_code <= 599:
            raise ValueError("provider HTTP status is invalid")
        self.status_code = status_code
        super().__init__(f"ProviderHTTP{status_code}")


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


def _error_class(error: Exception) -> str:
    if isinstance(error, ProviderHTTPError):
        return f"ProviderHTTP{error.status_code}"
    return type(error).__name__
