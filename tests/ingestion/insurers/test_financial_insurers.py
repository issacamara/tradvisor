from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from financial_insurers import assess_premium_comparability, normalize_insurer_report


def insurer_report(year: int = 2024) -> dict:
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    return {
        "company_id": "insurer-1",
        "source_ref": f"recorded://insurer-1/annual/{year}",
        "period": {"fiscal_year": year, "start": start, "end": end, "full_year": True},
        "publication": {"published_at": f"{year + 1}-03-01T00:00:00Z", "evidenced": True},
        "collected_at": f"{year + 1}-03-02T00:00:00Z",
        "currency": "XOF",
        "report_scope": "consolidated",
        "accounting_basis": "SYSCOHADA",
        "financial_category": "insurer",
        "gross_written_premiums": {"value": "250", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True, "premium_basis": "gross_written", "period_start": start, "period_end": end, "report_scope": "consolidated", "regulatory_basis": "SYSCOHADA"},
        "solvency": {
            "evidenced": True,
            "currency": "XOF",
            "period_end": end,
            "jurisdiction": "WAEMU",
            "report_scope": "consolidated",
            "regulatory_basis": "reported-solvency-framework",
            "eligible": {"value": "180", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True},
            "required": {"value": "120", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True},
        },
    }


def test_normalizes_gross_written_premiums_and_matched_solvency_amounts():
    result = normalize_insurer_report(insurer_report())

    assert result.gross_written_premiums.value == 250_000_000
    assert result.premium_basis == "gross_written"
    assert result.solvency_coverage == Decimal("1.5")
    assert result.eligible_solvency_amount.value == 180_000_000


def test_premium_period_scope_and_basis_must_match_before_comparison():
    first = normalize_insurer_report(insurer_report(2023))
    second_report = insurer_report(2024)
    second_report["gross_written_premiums"]["premium_basis"] = "net_written"
    second = normalize_insurer_report(second_report)

    assert not assess_premium_comparability([first, second]).comparable
    assert assess_premium_comparability([first, second]).reason == "premium_basis_or_scope_incomparable"

    unmatched = insurer_report(2024)
    unmatched["gross_written_premiums"]["report_scope"] = "standalone"
    result = normalize_insurer_report(unmatched)
    assert result.gross_written_premiums is None
    assert "premium_scope_mismatch" in result.unavailable_reasons

    shifted_period = insurer_report(2024)
    shifted_period["period"]["start"] = "2023-07-01"
    shifted_period["gross_written_premiums"]["period_start"] = "2023-07-01"
    shifted = normalize_insurer_report(shifted_period)
    assert not assess_premium_comparability([first, shifted]).comparable
    assert assess_premium_comparability([first, shifted]).reason == "premium_periods_incomparable"


def test_missing_or_invalid_required_solvency_stays_unavailable():
    missing = insurer_report()
    missing["solvency"]["required"] = None
    invalid = insurer_report()
    invalid["solvency"]["required"]["value"] = "0"

    for report in (missing, invalid):
        result = normalize_insurer_report(report)
        assert result.solvency_coverage is None
        assert result.required_solvency_amount is None


def test_solvency_date_scope_jurisdiction_and_basis_must_match():
    report = insurer_report()
    report["solvency"]["period_end"] = "2023-12-31"
    report["solvency"]["report_scope"] = "standalone"
    report["solvency"]["jurisdiction"] = None
    report["solvency"]["regulatory_basis"] = None

    result = normalize_insurer_report(report)

    assert result.solvency_coverage is None
    assert {"solvency_date_mismatch", "solvency_scope_mismatch", "solvency_jurisdiction_unavailable", "solvency_regulatory_basis_unavailable"} <= set(result.unavailable_reasons)


def test_no_industrial_revenue_debt_or_reserve_fallbacks_are_used():
    report = insurer_report()
    report.pop("gross_written_premiums")
    report.pop("solvency")
    report["revenue"] = {"value": "900", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True}
    report["technical_reserves"] = {"value": "800", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True}
    report["total_liabilities"] = {"value": "1000", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True}

    result = normalize_insurer_report(report)

    assert result.gross_written_premiums is None
    assert result.solvency_coverage is None
    assert result.eligible_solvency_amount is None
    assert result.required_solvency_amount is None
