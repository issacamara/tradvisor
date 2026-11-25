"""RichBourse listing parsing and document fetching for the FI-1 job."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlparse

from .richbourse_client import fetch as richbourse_fetch
from .richbourse_client import is_approved_url


SELECTOR_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
RICHBOURSE_ORIGIN = "https://www.richbourse.com"
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_INTERIM_TERMS = (
    "trimestre", "trimestriel", "semestr", "semester", "quarter", "half year",
    "six month", "mi-annee",
)
_ANNUAL_TERMS = (
    "annuel", "exercice", "etat financier", "etats financiers", "rapport annuel",
    "bilan annuel", "comptes annuels",
)
SOURCE_TIMEOUT_SECONDS = 30


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


def richbourse_symbol_page_url_for_page(symbol: str, page: int) -> str:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    return f"{richbourse_symbol_page_url(symbol)}&page={page}"


def is_approved_document_url(url: str) -> bool:
    return is_approved_url(url)


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
        "historical", "previous_year", "publication_year"
    }:
        raise ValueError("selection_mode must be historical, previous_year, or publication_year")

    soup = BeautifulSoup(html, "html.parser")
    by_year: dict[int, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    for row in soup.select("div.ligne_paire, div.ligne_impaire"):
        link = row.find("a", href=True)
        if link is None:
            continue
        title = link.get_text(" ", strip=True)
        document_link = urljoin(SELECTOR_URL, link["href"].strip())
        if not is_approved_document_url(document_link):
            continue

        slug = _plain_text(urlparse(document_link).path.replace("-", " ").replace("_", " "))
        normalized = _plain_text(title)
        identity = f"{normalized} {slug}"
        if any(term in identity for term in _INTERIM_TERMS):
            continue
        if not any(term in identity for term in _ANNUAL_TERMS):
            continue
        fiscal_year_match = _YEAR.search(normalized)
        if fiscal_year_match is None:
            fiscal_year_match = _YEAR.search(slug)
        if fiscal_year_match is None:
            continue

        fiscal_year = int(fiscal_year_match.group(1))
        publication_year = _publication_year(row)
        if selection_mode == "publication_year":
            if publication_year is None or publication_year != current_year:
                continue
            candidates.append(
                {"symbol": symbol, "fiscal_year": fiscal_year, "document_link": document_link}
            )
            continue

        year = fiscal_year
        if selection_mode == "previous_year":
            if year != current_year - 1:
                continue
        elif not current_year - 5 <= year < current_year:
            continue

        if year in by_year:
            continue
        by_year[year] = {"symbol": symbol, "fiscal_year": year, "document_link": document_link}

    if selection_mode == "publication_year":
        # Unlike historical selection, publication-year mode must be able to
        # try every eligible document in listing order until one validates.
        return tuple(candidates)
    return tuple(by_year[year] for year in sorted(by_year, reverse=True)[:limit])


_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})\Z")


def _publication_year(row: Any) -> int | None:
    for value in row.stripped_strings:
        match = _DATE.search(value)
        if match is None:
            continue
        try:
            return datetime.strptime(match.group(), "%d/%m/%Y").year
        except ValueError:
            continue
    return None


def _page_publication_years(html: str) -> tuple[int, ...]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    years = []
    for row in soup.select("div.ligne_paire, div.ligne_impaire"):
        year = _publication_year(row)
        if year is not None:
            years.append(year)
    return tuple(years)


def _page_fiscal_years(html: str) -> tuple[int, ...]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    years = []
    for row in soup.select("div.ligne_paire, div.ligne_impaire"):
        link = row.find("a", href=True)
        if link is None:
            continue
        source_text = _plain_text(link.get_text(" ", strip=True))
        year = _YEAR.search(source_text)
        if year is None:
            year = _YEAR.search(_plain_text(urlparse(link["href"]).path))
        if year:
            years.append(int(year.group(1)))
    return tuple(years)


def _page_signature(html: str) -> str:
    from bs4 import BeautifulSoup

    return " ".join(BeautifulSoup(html, "html.parser").stripped_strings)


def _get_response(url: str, *, accept: str, timeout: float) -> Any:
    """Fetch one RichBourse response through the shared client."""
    return richbourse_fetch(
        url,
        accept=accept,
        headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
        timeout=timeout,
    )


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
