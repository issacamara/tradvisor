"""Pure, offline contracts shared by the FI-1 financial ingestion waves."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from html.parser import HTMLParser
import math
import re
import unicodedata
from collections.abc import Mapping
from numbers import Real
from urllib.parse import quote, urljoin, urlparse


RICHBOURSE_ORIGIN = "https://www.richbourse.com"
RICHBOURSE_FINANCIALS_URL = (
    f"{RICHBOURSE_ORIGIN}/common/actualite-categorie/index/etats-financiers"
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
    announcement_title: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if isinstance(self.fiscal_year, bool) or not isinstance(self.fiscal_year, int):
            raise ValueError("fiscal_year must be an integer")
        if not is_approved_document_url(self.document_link):
            raise ValueError("document_link must use the approved RichBourse origin")
        if not self.announcement_title or len(self.announcement_title) > 256:
            raise ValueError("announcement_title must be a bounded non-empty string")

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


class _RichBoursePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.selector_found = False
        self.in_selector = False
        self.option_value: str | None = None
        self.symbols: list[str] = []
        self.div_depth = 0
        self.row_depth: int | None = None
        self.current_link: tuple[str, list[str]] | None = None
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "select":
            if attributes.get("id") == "symbole":
                self.selector_found = True
                self.in_selector = True
        elif tag == "option" and self.in_selector:
            self.option_value = (attributes.get("value") or "").strip()
        elif tag == "div":
            self.div_depth += 1
            classes = set((attributes.get("class") or "").split())
            if self.row_depth is None and classes.intersection(
                {"ligne_paire", "ligne_impaire"}
            ):
                self.row_depth = self.div_depth
        elif tag == "a" and self.row_depth is not None and self.current_link is None:
            href = (attributes.get("href") or "").strip()
            if href:
                self.current_link = (href, [])

    def handle_data(self, data: str) -> None:
        if self.current_link is not None:
            self.current_link[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.in_selector:
            if self.option_value:
                self.symbols.append(self.option_value)
            self.option_value = None
        elif tag == "select" and self.in_selector:
            self.in_selector = False
        elif tag == "a" and self.current_link is not None:
            href, text_parts = self.current_link
            self.links.append((href, " ".join(" ".join(text_parts).split())))
            self.current_link = None
        elif tag == "div":
            if self.row_depth == self.div_depth:
                self.row_depth = None
            self.div_depth = max(0, self.div_depth - 1)


def parse_selector_symbols(html: str) -> tuple[str, ...]:
    """Read non-empty RichBourse options from its ``select#symbole`` selector."""
    parser = _RichBoursePageParser()
    parser.feed(html)
    if not parser.selector_found:
        raise ValueError("RichBourse symbol selector is missing")
    return tuple(dict.fromkeys(parser.symbols))


def richbourse_symbol_page_url(symbol: str) -> str:
    """Build the documented symbol-filtered RichBourse page URL."""
    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol is required")
    return f"{RICHBOURSE_FINANCIALS_URL}?symbole={quote(symbol, safe='')}"


def is_approved_document_url(url: str) -> bool:
    """Allow only the RichBourse HTTPS origin for candidates and redirect targets.

    Runtime fetchers must apply this check before each request and after every
    redirect; they must stop when a redirect target does not pass this check.
    """
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
) -> tuple[AnnualCandidate, ...]:
    """Parse annual reports from one symbol-filtered page, newest fiscal years first."""
    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol is required")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if not isinstance(selection_mode, str) or selection_mode not in (
        "historical",
        "previous_year",
    ):
        raise ValueError("selection_mode must be 'historical' or 'previous_year'")

    parser = _RichBoursePageParser()
    parser.feed(html)
    by_year: dict[int, AnnualCandidate] = {}
    for href, title in parser.links:
        normalized = _plain_text(title)
        if any(term in normalized for term in _INTERIM_TERMS):
            continue
        if not any(term in normalized for term in _ANNUAL_TERMS):
            continue
        year_match = _YEAR.search(normalized)
        if year_match is None:
            continue

        document_link = urljoin(RICHBOURSE_FINANCIALS_URL, href)
        if not is_approved_document_url(document_link):
            continue
        year = int(year_match.group(1))
        if selection_mode == "previous_year":
            if year != current_year - 1:
                continue
        elif not current_year - 5 <= year < current_year:
            continue
        # RichBourse pages are newest-first; keep the first link if a year repeats.
        by_year.setdefault(year, AnnualCandidate(symbol, year, document_link, title[:256]))

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
