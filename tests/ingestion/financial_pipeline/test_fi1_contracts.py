from __future__ import annotations

import builtins
import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest

from functions.financials.fi1_contracts import (
    EXTRACTION_KEYS,
    AnnualCandidate,
    FinancialIdentity,
    RowDecision,
    decide_row_state,
    is_approved_document_url,
    parse_annual_candidates,
    parse_selector_symbols,
    richbourse_symbol_page_url,
    validate_extraction,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_selector_fixture_returns_distinct_symbols() -> None:
    html = (FIXTURES / "fi1_selector.html").read_text()

    assert parse_selector_symbols(html) == ("ABC", "XYZ")


def test_html_contract_is_independent_of_global_beautifulsoup_stubs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bs4_stub = ModuleType("bs4")
    bs4_stub.BeautifulSoup = object  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bs4", bs4_stub)

    assert parse_selector_symbols(
        '<select id="symbole"><option value="ABC">ABC</option></select>'
    ) == ("ABC",)


def test_symbol_filter_url_and_page_fixture_select_newest_five_annual_years() -> None:
    html = (FIXTURES / "fi1_symbol_page.html").read_text()

    assert richbourse_symbol_page_url(" ABC ").endswith("?symbole=ABC")
    candidates = parse_annual_candidates(html, "ABC", current_year=2026)

    assert [candidate.fiscal_year for candidate in candidates] == [
        2025,
        2024,
        2023,
        2022,
        2021,
    ]
    assert candidates[0].document_link == "https://www.richbourse.com/documents/abc-2025.pdf"
    assert candidates[0].announcement_title == "Rapport annuel Exercice 2025"
    assert all(candidate.symbol == "ABC" for candidate in candidates)
    assert len({candidate.fiscal_year for candidate in candidates}) == 5
    assert candidates[1].document_link.endswith("abc-2024.pdf")


def test_off_origin_annual_links_and_redirect_targets_are_rejected() -> None:
    html = (
        '<div class="ligne_paire"><a href="https://files.invalid/annual-2026.pdf">'
        "Rapport annuel Exercice 2026</a></div>"
    )

    assert parse_annual_candidates(html, "ABC", current_year=2027) == ()
    assert is_approved_document_url("https://www.richbourse.com/documents/report.pdf")
    assert not is_approved_document_url("https://files.invalid/report.pdf")
    assert not is_approved_document_url("http://www.richbourse.com/report.pdf")
    with pytest.raises(ValueError, match="approved RichBourse origin"):
        AnnualCandidate("ABC", 2026, "https://files.invalid/annual-2026.pdf", "Annual 2026")


@pytest.mark.parametrize(
    "payload",
    [
        {
            "fiscal_year": 2024,
            "revenue": 1,
            "net_income": 2,
            "total_debt": 3,
            "cash_and_cash_equivalents": 4,
            "total_equity": 5,
            "evidence": "unexpected",
        },
        {
            "fiscal_year": 2024,
            "revenue": 1,
            "net_income": 2,
            "total_debt": 3,
            "cash_and_cash_equivalents": 4,
        },
    ],
)
def test_extraction_requires_exact_key_set(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="exactly the FI-1 keys"):
        validate_extraction(payload, source_fiscal_year=2024)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "12", object()])
def test_extraction_values_must_be_finite_numbers_or_null(value: object) -> None:
    payload: dict[str, object] = {
        "fiscal_year": 2024,
        "revenue": value,
        "net_income": None,
        "total_debt": 0,
        "cash_and_cash_equivalents": -1.5,
        "total_equity": 5,
    }

    with pytest.raises(ValueError, match="finite numbers or null"):
        validate_extraction(payload, source_fiscal_year=2024)


def test_extraction_requires_source_year_and_returns_only_six_contract_fields() -> None:
    payload: dict[str, object] = {
        "fiscal_year": 2024,
        "revenue": 1,
        "net_income": None,
        "total_debt": 3.25,
        "cash_and_cash_equivalents": 4,
        "total_equity": 5,
    }

    validated = validate_extraction(payload, source_fiscal_year=2024)

    assert tuple(validated.as_dict()) == EXTRACTION_KEYS
    assert validated.as_dict() == payload
    assert not any(
        "pdf" in name or "prompt" in name or "response" in name
        for name in vars(validated)
    )
    with pytest.raises(ValueError, match="does not match source metadata"):
        validate_extraction(payload, source_fiscal_year=2023)
    payload["fiscal_year"] = None
    with pytest.raises(ValueError, match="does not match source metadata"):
        validate_extraction(payload, source_fiscal_year=2024)
    with pytest.raises(ValueError, match="finite numbers or null"):
        type(validated)(2024, float("nan"), None, None, None, None)


def test_contract_processing_is_offline_and_does_not_log_or_write_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sentinel = "PRIVATE_PDF_TEXT_PROMPT_PROVIDER_RESPONSE"
    html = f'<select id="symbole"><option value="ABC">{sentinel}</option></select>'
    payload: dict[str, object] = {
        "fiscal_year": 2024,
        "revenue": 1,
        "net_income": None,
        "total_debt": None,
        "cash_and_cash_equivalents": None,
        "total_equity": None,
    }
    writes: list[str] = []
    original_open = builtins.open
    original_path_open = Path.open

    def tracks_write(file: object, mode: str) -> None:
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            writes.append(str(file))

    def tracked_open(file, mode="r", *args, **kwargs):
        tracks_write(file, mode)
        return original_open(file, *args, **kwargs)

    def tracked_path_open(path, mode="r", *args, **kwargs):
        tracks_write(path, mode)
        return original_path_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", tracked_open)
    monkeypatch.setattr(Path, "open", tracked_path_open)
    caplog.set_level(logging.DEBUG)
    assert parse_selector_symbols(html) == ("ABC",)
    assert validate_extraction(payload, source_fiscal_year=2024).fiscal_year == 2024

    assert writes == []
    assert sentinel not in caplog.text
    assert list(tmp_path.iterdir()) == []
    assert not any(path.suffix.lower() == ".pdf" for path in FIXTURES.iterdir())
    assert all(sentinel not in path.read_text() for path in FIXTURES.iterdir())


@pytest.mark.parametrize(
    ("existing", "candidate", "succeeded", "expected"),
    [
        (None, "https://source.invalid/new.pdf", True, RowDecision.INSERT),
        (
            "https://source.invalid/same.pdf",
            "https://source.invalid/same.pdf",
            True,
            RowDecision.SKIP,
        ),
        (
            "https://source.invalid/old.pdf",
            "https://source.invalid/new.pdf",
            True,
            RowDecision.REPLACE,
        ),
        (
            "https://source.invalid/old.pdf",
            "https://source.invalid/new.pdf",
            False,
            RowDecision.PRESERVE,
        ),
        (None, "https://source.invalid/new.pdf", False, RowDecision.PRESERVE),
    ],
)
def test_retry_safe_row_decisions(
    existing: str | None,
    candidate: str,
    succeeded: bool,
    expected: RowDecision,
) -> None:
    assert decide_row_state(
        existing_document_link=existing,
        candidate_document_link=candidate,
        extraction_succeeded=succeeded,
    ) is expected


def test_candidate_exposes_logical_identity_and_only_source_reference_metadata() -> None:
    candidate = AnnualCandidate(
        "ABC", 2024, "https://www.richbourse.com/report.pdf", "Annual report 2024"
    )

    assert candidate.identity == FinancialIdentity("ABC", 2024)
    assert set(vars(candidate)) == {
        "symbol", "fiscal_year", "document_link", "announcement_title"
    }


@pytest.mark.parametrize("limit", range(1, 6))
def test_annual_window_filters_before_limit_and_preserves_order(limit: int) -> None:
    html = "".join(
        f'<div class="ligne_paire"><a href="/{year}.pdf">Rapport annuel Exercice {year}</a></div>'
        for year in (2027, 2026, 2025, 2025, 2024, 2023, 2022, 2021, 2020)
    )
    candidates = parse_annual_candidates(html, "ABC", current_year=2026, limit=limit)
    assert [candidate.fiscal_year for candidate in candidates] == [
        2025, 2024, 2023, 2022, 2021
    ][:limit]


def test_annual_window_missing_years_and_rollover() -> None:
    html = "".join(
        f'<div class="ligne_paire"><a href="/{year}.pdf">Rapport annuel Exercice {year}</a></div>'
        for year in (2026, 2025, 2021, 2020)
    )
    assert [c.fiscal_year for c in parse_annual_candidates(html, "ABC", current_year=2026)] == [
        2025, 2021
    ]
    assert [c.fiscal_year for c in parse_annual_candidates(html, "ABC", current_year=2027)] == [
        2026, 2025
    ]
