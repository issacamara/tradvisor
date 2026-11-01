"""Pure, offline contracts shared by the FI-1 financial ingestion waves."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
import unicodedata
from collections.abc import Mapping
from numbers import Real
from urllib.parse import quote, urljoin, urlparse


RICHBOURSE_FINANCIALS_URL = (
    "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
)
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
    "trimestre",
    "trimestriel",
    "semestr",
    "semester",
    "quarter",
    "half year",
    "six month",
    "mi-annee",
)
_ANNUAL_TERMS = (
    "annuel",
    "exercice",
    "etat financier",
    "etats financiers",
    "rapport annuel",
    "bilan annuel",
    "comptes annuels",
)


@dataclass(frozen=True)
class AnnualCandidate:
    """The only source metadata that crosses into the FI-1 runtime contract."""

    symbol: str
    fiscal_year: int
    document_link: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if isinstance(self.fiscal_year, bool) or not isinstance(self.fiscal_year, int):
            raise ValueError("fiscal_year must be an integer")
        parsed = urlparse(self.document_link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("document_link must be an absolute HTTP(S) URL")

    @property
    def identity(self) -> "FinancialIdentity":
        return FinancialIdentity(self.symbol, self.fiscal_year)


@dataclass(frozen=True)
class FinancialIdentity:
    symbol: str
    fiscal_year: int

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if isinstance(self.fiscal_year, bool) or not isinstance(self.fiscal_year, int):
            raise ValueError("fiscal_year must be an integer")


@dataclass(frozen=True)
class ValidatedExtraction:
    """Validated six-field result; it carries no document or provider evidence."""

    fiscal_year: int
    revenue: Real | None
    net_income: Real | None
    total_debt: Real | None
    cash_and_cash_equivalents: Real | None
    total_equity: Real | None

    def __post_init__(self) -> None:
        if isinstance(self.fiscal_year, bool) or not isinstance(self.fiscal_year, int):
            raise ValueError("fiscal_year must be an integer")
        for key in EXTRACTION_KEYS[1:]:
            value = getattr(self, key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError("extraction values must be finite numbers or null")
            try:
                finite = math.isfinite(value)
            except (OverflowError, TypeError, ValueError):
                finite = False
            if not finite:
                raise ValueError("extraction values must be finite numbers or null")

    def as_dict(self) -> dict[str, Real | int | None]:
        return {key: getattr(self, key) for key in EXTRACTION_KEYS}


class RowDecision(str, Enum):
    INSERT = "insert"
    SKIP = "skip"
    REPLACE = "replace"
    PRESERVE = "preserve"


def _plain_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def parse_selector_symbols(html: str) -> tuple[str, ...]:
    """Read non-empty RichBourse options from its ``select#symbole`` selector."""
    from bs4 import BeautifulSoup

    select = BeautifulSoup(html, "html.parser").find("select", id="symbole")
    if select is None:
        raise ValueError("RichBourse symbol selector is missing")
    symbols: list[str] = []
    for option in select.find_all("option"):
        value = (option.get("value") or "").strip()
        if value and value not in symbols:
            symbols.append(value)
    return tuple(symbols)


def richbourse_symbol_page_url(symbol: str) -> str:
    """Build the documented symbol-filtered RichBourse page URL."""
    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol is required")
    return f"{RICHBOURSE_FINANCIALS_URL}?symbole={quote(symbol, safe='')}"


def parse_annual_candidates(
    html: str, symbol: str, *, limit: int = 5
) -> tuple[AnnualCandidate, ...]:
    """Parse annual reports from one symbol-filtered page, newest fiscal years first."""
    from bs4 import BeautifulSoup

    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol is required")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all(
        "div",
        class_=lambda classes: classes
        and ("ligne_paire" in classes or "ligne_impaire" in classes),
    )
    by_year: dict[int, AnnualCandidate] = {}
    for row in rows:
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

        document_link = urljoin(RICHBOURSE_FINANCIALS_URL, link["href"].strip())
        parsed = urlparse(document_link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        year = int(year_match.group(1))
        # RichBourse pages are newest-first; keep the first link if a year repeats.
        by_year.setdefault(year, AnnualCandidate(symbol, year, document_link))

    return tuple(by_year[year] for year in sorted(by_year, reverse=True)[:limit])


def validate_extraction(
    payload: Mapping[str, object], *, source_fiscal_year: int
) -> ValidatedExtraction:
    """Validate the exact FI-1 extraction object without retaining evidence."""
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

    values: dict[str, Real | None] = {}
    for key in EXTRACTION_KEYS[1:]:
        value = payload[key]
        if value is None:
            values[key] = None
            continue
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError("extraction values must be finite numbers or null")
        values[key] = value

    return ValidatedExtraction(fiscal_year=source_fiscal_year, **values)


def decide_row_state(
    *,
    existing_document_link: str | None,
    candidate_document_link: str,
    extraction_succeeded: bool,
) -> RowDecision:
    """Choose a retry-safe action for identity ``(symbol, fiscal_year)``."""
    if not isinstance(extraction_succeeded, bool):
        raise ValueError("extraction_succeeded must be a boolean")
    if not extraction_succeeded:
        return RowDecision.PRESERVE
    if existing_document_link is None:
        return RowDecision.INSERT
    if existing_document_link == candidate_document_link:
        return RowDecision.SKIP
    return RowDecision.REPLACE
