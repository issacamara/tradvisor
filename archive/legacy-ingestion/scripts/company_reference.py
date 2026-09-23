"""Build source-backed issuer reference records from catalog and corrections."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping


FINANCIAL_CATEGORIES = {"bank", "insurer", "non_financial", "unsupported"}
MAPPING_FIELDS = (
    "symbol",
    "emetteur",
    "issuer_id",
    "share_class",
    "valid_from",
    "valid_to",
    "market_sector",
    "financial_category",
    "source_url",
    "source_date",
    "correction_reason",
)


@dataclass(frozen=True)
class CompanyRecord:
    symbol: str
    name: str
    issuer_id: str | None
    share_class: str | None
    valid_from: date | None
    valid_to: date | None
    market_sector: str | None
    financial_category: str
    source_url: str | None
    source_date: date | None
    correction_reason: str | None


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD: {value!r}") from error


def read_mapping(path: str | Path) -> list[dict[str, str]]:
    """Read the legacy semicolon map and optional evidence/correction columns."""
    with Path(path).open(encoding="latin1", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        if not {"symbol", "emetteur"}.issubset(reader.fieldnames or ()):
            raise ValueError("mapping.csv must contain symbol and emetteur columns")
        rows = []
        for row in reader:
            normalized = {field: (row.get(field) or "").strip() for field in MAPPING_FIELDS}
            normalized["symbol"] = normalized["symbol"].upper()
            rows.append(normalized)
        return rows


def build_company_records(
    catalog: Iterable[Mapping[str, object]],
    corrections: Iterable[Mapping[str, str]],
) -> list[CompanyRecord]:
    """Overlay dated, cited corrections while keeping every catalog symbol reachable."""
    by_symbol: dict[str, list[Mapping[str, str]]] = {}
    for correction in corrections:
        symbol = (correction.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("company mapping rows require a symbol")
        category = (correction.get("financial_category") or "unsupported").strip()
        if category not in FINANCIAL_CATEGORIES:
            raise ValueError(f"unsupported financial category for {symbol}: {category!r}")
        evidence_fields = (
            "issuer_id",
            "share_class",
            "valid_from",
            "valid_to",
            "market_sector",
            "source_url",
            "source_date",
        )
        if category != "unsupported" or any(correction.get(key) for key in evidence_fields):
            if not correction.get("source_url") or not correction.get("source_date"):
                raise ValueError(f"source_url and source_date are required for evidenced mapping {symbol}")
        start = _parse_date(correction.get("valid_from"), "valid_from")
        end = _parse_date(correction.get("valid_to"), "valid_to")
        if start and end and end < start:
            raise ValueError(f"valid_to precedes valid_from for {symbol}")
        if (
            correction.get("issuer_id")
            or correction.get("share_class")
            or correction.get("market_sector")
            or category != "unsupported"
        ) and not start:
            raise ValueError(f"valid_from is required for evidenced identity/classification {symbol}")
        _parse_date(correction.get("source_date"), "source_date")
        by_symbol.setdefault(symbol, []).append(correction)

    for symbol, entries in by_symbol.items():
        dated = sorted(
            (
                _parse_date(row.get("valid_from"), "valid_from") or date.min,
                _parse_date(row.get("valid_to"), "valid_to") or date.max,
            )
            for row in entries
        )
        if any(next_start <= previous_end for (_, previous_end), (next_start, _) in zip(dated, dated[1:])):
            raise ValueError(f"overlapping symbol validity periods for {symbol}")

    records = []
    seen = set()
    for company in catalog:
        symbol = str(company.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("catalog companies require a symbol")
        if symbol in seen:
            raise ValueError(f"duplicate catalog symbol: {symbol}")
        seen.add(symbol)
        name = str(company.get("name") or "").strip()
        for correction in by_symbol.get(symbol, ()):
            category = correction.get("financial_category") or "unsupported"
            records.append(
                CompanyRecord(
                    symbol=symbol,
                    name=name,
                    issuer_id=correction.get("issuer_id") or None,
                    share_class=correction.get("share_class") or None,
                    valid_from=_parse_date(correction.get("valid_from"), "valid_from"),
                    valid_to=_parse_date(correction.get("valid_to"), "valid_to"),
                    market_sector=correction.get("market_sector") or None,
                    financial_category=category,
                    source_url=correction.get("source_url") or None,
                    source_date=_parse_date(correction.get("source_date"), "source_date"),
                    correction_reason=correction.get("correction_reason") or None,
                )
            )
        if not by_symbol.get(symbol):
            records.append(
                CompanyRecord(
                    symbol=symbol,
                    name=name,
                    issuer_id=None,
                    share_class=None,
                    valid_from=None,
                    valid_to=None,
                    market_sector=None,
                    financial_category="unsupported",
                    source_url=None,
                    source_date=None,
                    correction_reason=None,
                )
            )
    catalog_symbols = {record.symbol for record in records}
    for symbol, entries in by_symbol.items():
        if symbol in catalog_symbols:
            continue
        for correction in entries:
            records.append(
                CompanyRecord(
                    symbol=symbol,
                    name=correction.get("emetteur") or "",
                    issuer_id=correction.get("issuer_id") or None,
                    share_class=correction.get("share_class") or None,
                    valid_from=_parse_date(correction.get("valid_from"), "valid_from"),
                    valid_to=_parse_date(correction.get("valid_to"), "valid_to"),
                    market_sector=correction.get("market_sector") or None,
                    financial_category=correction.get("financial_category") or "unsupported",
                    source_url=correction.get("source_url") or None,
                    source_date=_parse_date(correction.get("source_date"), "source_date"),
                    correction_reason=correction.get("correction_reason") or None,
                )
            )
    return records
