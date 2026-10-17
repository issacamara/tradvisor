from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from financial_banks import assess_bank_capital_history, normalize_bank_report


def bank_report() -> dict:
    return {
        "company_id": "bank-1",
        "source_ref": "recorded://bank-1/annual/2024",
        "period": {"fiscal_year": 2024, "start": "2024-01-01", "end": "2024-12-31", "full_year": True},
        "publication": {"published_at": "2025-03-01T00:00:00Z", "evidenced": True},
        "collected_at": "2025-03-02T00:00:00Z",
        "currency": "XOF",
        "report_scope": "consolidated",
        "accounting_basis": "BCEAO-PCB",
        "financial_category": "bank",
        "pnb": {"value": "125", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True, "period_end": "2024-12-31", "report_scope": "consolidated"},
        "regulatory_jurisdiction": "WAEMU",
        "applicable_constraints_complete": True,
        "capital_constraints": [
            {"constraint_id": "total-capital", "disclosed": {"value": "14", "unit": "percent", "evidenced": True}, "required": {"value": "8", "unit": "percent", "evidenced": True}, "period_end": "2024-12-31", "jurisdiction": "WAEMU", "report_scope": "consolidated", "applicable": True},
            {"constraint_id": "tier-1", "disclosed": {"value": "11", "unit": "percent", "evidenced": True}, "required": {"value": "7", "unit": "percent", "evidenced": True}, "period_end": "2024-12-31", "jurisdiction": "WAEMU", "report_scope": "consolidated", "applicable": True},
            {"constraint_id": "local-buffer", "period_end": "2024-12-31", "jurisdiction": "WAEMU", "report_scope": "consolidated", "applicable": False},
        ],
    }


def test_normalizes_pnb_and_uses_minimum_of_matched_applicable_constraints():
    result = normalize_bank_report(bank_report())

    assert result.net_banking_income.value == 125_000_000
    assert result.minimum_capital_coverage == Decimal("1.571428571428571428571428571")
    assert result.capital_constraints[0].coverage == Decimal("1.75")
    assert result.capital_constraints[1].coverage == Decimal("1.571428571428571428571428571")


def test_missing_or_incomplete_required_constraints_remain_unknown():
    report = bank_report()
    report["capital_constraints"][1]["required"] = None

    result = normalize_bank_report(report)

    assert result.minimum_capital_coverage is None
    assert "required_capital_ratio_unavailable" in result.unavailable_reasons
    assert not assess_bank_capital_history([result])


def test_date_scope_and_jurisdiction_mismatches_withhold_coverage():
    report = bank_report()
    report["capital_constraints"][0]["period_end"] = "2023-12-31"
    report["capital_constraints"][1]["report_scope"] = "standalone"

    result = normalize_bank_report(report)

    assert result.minimum_capital_coverage is None
    assert {"capital_constraint_date_mismatch", "capital_constraint_scope_mismatch"} <= set(result.unavailable_reasons)


def test_explicitly_inapplicable_constraint_is_excluded_from_minimum():
    result = normalize_bank_report(bank_report())

    assert result.minimum_capital_coverage == Decimal("1.571428571428571428571428571")
    assert result.capital_constraints[-1].applicable is False
    assert "capital_constraint_applicability_unknown" not in result.unavailable_reasons


def test_deposits_leverage_and_ratings_are_never_fallbacks_for_pnb_or_capital():
    report = bank_report()
    report.pop("pnb")
    report["deposits"] = {"value": "500", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True}
    report.pop("capital_constraints")
    report["industrial_leverage"] = "0.2"
    report["rating"] = "AAA"

    result = normalize_bank_report(report)

    assert result.net_banking_income is None
    assert result.minimum_capital_coverage is None
    assert "missing_pnb" in result.unavailable_reasons
    assert "applicable_capital_constraints_missing" in result.unavailable_reasons


def test_non_bank_category_does_not_expose_bank_fields():
    report = bank_report()
    report["financial_category"] = "non_financial"

    result = normalize_bank_report(report)

    assert result.net_banking_income is None
    assert result.minimum_capital_coverage is None
    assert not assess_bank_capital_history([result])
