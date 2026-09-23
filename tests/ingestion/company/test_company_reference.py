from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
import pytest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "archive"
    / "legacy-ingestion"
    / "scripts"
    / "company_reference.py"
)
SPEC = importlib.util.spec_from_file_location("company_reference", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
company_reference = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = company_reference
SPEC.loader.exec_module(company_reference)


def evidence(symbol: str, category: str, start: str = "2020-01-01") -> dict[str, str]:
    return {
        "symbol": symbol,
        "emetteur": "",
        "issuer_id": f"issuer-{symbol}",
        "share_class": "ordinary",
        "valid_from": start,
        "valid_to": "",
        "market_sector": "Financials" if category in {"bank", "insurer"} else "Industry",
        "financial_category": category,
        "source_url": f"https://issuer.example/{symbol}/report",
        "source_date": "2024-06-30",
        "correction_reason": "verified issuer report",
    }


def test_supported_categories_and_unsupported_do_not_depend_on_names() -> None:
    catalog = [
        {"symbol": "BANK", "name": "Ordinary name"},
        {"symbol": "INSR", "name": "Another name"},
        {"symbol": "CORP", "name": "Bank of Something"},
        {"symbol": "UNKN", "name": "Unknown Holdings"},
    ]
    corrections = [
        evidence("BANK", "bank"),
        evidence("INSR", "insurer"),
        evidence("CORP", "non_financial"),
    ]

    records = company_reference.build_company_records(catalog, corrections)

    assert {record.symbol: record.financial_category for record in records} == {
        "BANK": "bank",
        "INSR": "insurer",
        "CORP": "non_financial",
        "UNKN": "unsupported",
    }
    assert next(record for record in records if record.symbol == "UNKN").source_url is None


@pytest.mark.parametrize("missing_field", ["issuer_id", "share_class"])
def test_classification_without_complete_identity_stays_unsupported(
    missing_field: str,
) -> None:
    correction = evidence("PART", "bank")
    correction[missing_field] = ""

    records = company_reference.build_company_records(
        [{"symbol": "PART", "name": "Catalog issuer"}], [correction]
    )

    assert len(records) == 1
    assert records[0].financial_category == "unsupported"
    assert records[0].market_sector is None
    assert records[0].issuer_id == (None if missing_field == "issuer_id" else "issuer-PART")
    assert records[0].share_class == (None if missing_field == "share_class" else "ordinary")
    assert records[0].source_url == correction["source_url"]
    assert records[0].source_date == date(2024, 6, 30)


def test_symbol_history_keeps_validity_provenance_and_old_symbols_reachable() -> None:
    catalog = [{"symbol": "NEW", "name": "Current issuer"}]
    old = evidence("OLD", "non_financial", "2015-01-01")
    old["valid_to"] = "2021-12-31"
    new = evidence("NEW", "non_financial", "2022-01-01")

    records = company_reference.build_company_records(catalog, [old, new])

    assert [(record.symbol, record.valid_from, record.valid_to) for record in records] == [
        ("NEW", date(2022, 1, 1), None),
        ("OLD", date(2015, 1, 1), date(2021, 12, 31)),
    ]
    assert all(record.source_url and record.source_date == date(2024, 6, 30) for record in records)
    assert records[1].name == ""


def test_manual_corrections_must_be_sourced_and_non_overlapping() -> None:
    sourced = evidence("BANK", "bank")
    corrected = evidence("BANK", "insurer", "2023-01-01")
    sourced["valid_to"] = "2022-12-31"
    corrected["correction_reason"] = "issuer reorganization"

    result = company_reference.build_company_records(
        [{"symbol": "BANK", "name": "Catalog label"}], [sourced, corrected]
    )
    assert [row.financial_category for row in result] == ["bank", "insurer"]
    assert result[1].correction_reason == "issuer reorganization"

    missing_source = evidence("BAD", "bank")
    missing_source["source_url"] = ""
    with pytest.raises(ValueError, match="source_url and source_date"):
        company_reference.build_company_records([], [missing_source])

    overlap = evidence("BANK", "insurer", "2022-12-31")
    with pytest.raises(ValueError, match="overlapping symbol validity"):
        company_reference.build_company_records([], [sourced, overlap])


def test_catalog_symbols_without_reference_are_retained_and_unclassified() -> None:
    catalog = [
        {"symbol": "AAA", "name": "First"},
        {"symbol": "BBB", "name": "Second", "sector": "Unverified catalog sector"},
    ]

    records = company_reference.build_company_records(catalog, [])

    assert [record.symbol for record in records] == ["AAA", "BBB"]
    assert all(record.financial_category == "unsupported" for record in records)
    assert all(record.market_sector is None for record in records)


def test_unmapped_discovered_listing_uses_source_slug_without_inventing_symbol() -> None:
    records = company_reference.build_company_records(
        [{"symbol": None, "name": "Mystery Bank", "source_slug": "mystery-bank"}],
        [],
    )

    assert len(records) == 1
    assert records[0].symbol is None
    assert records[0].name == "Mystery Bank"
    assert records[0].source_slug == "mystery-bank"
    assert records[0].financial_category == "unsupported"
    assert records[0].market_sector is None


def test_legacy_mapping_still_loads_with_optional_reference_columns(tmp_path: Path) -> None:
    path = tmp_path / "mapping.csv"
    path.write_text(
        "symbol;emetteur;financial_category\nABC;Issuer ABC;bank\n",
        encoding="latin1",
    )

    assert company_reference.read_mapping(path) == [
        {
            field: (
                "ABC"
                if field == "symbol"
                else "Issuer ABC"
                if field == "emetteur"
                else "bank"
                if field == "financial_category"
                else ""
            )
            for field in company_reference.MAPPING_FIELDS
        }
    ]
