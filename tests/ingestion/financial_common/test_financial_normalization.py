from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "archive" / "legacy-ingestion" / "scripts" / "financial_normalization.py"
SPEC = importlib.util.spec_from_file_location("financial_normalization", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
financial_normalization = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = financial_normalization
SPEC.loader.exec_module(financial_normalization)

FIXTURE = Path(__file__).parent / "fixtures" / "annual_reports.json"
REPORTS = json.loads(FIXTURE.read_text(encoding="utf-8"))


def normalized_reports(reports=REPORTS):
    return [financial_normalization.normalize_annual_report(report) for report in reports]


def test_five_consecutive_comparable_years_and_six_equity_dates_are_verifiable():
    records = normalized_reports()

    assessment = financial_normalization.assess_five_year_history(records)

    assert assessment.comparable is True
    assert assessment.years == (2020, 2021, 2022, 2023, 2024)
    assert assessment.equity_dates == (
        date(2019, 6, 30),
        date(2020, 6, 30),
        date(2021, 6, 30),
        date(2022, 6, 30),
        date(2023, 6, 30),
        date(2024, 6, 30),
    )
    assert records[0].ordinary_owner_earnings.value == -2_500_000
    assert records[1].ordinary_owner_earnings.value == 4_000


def test_missing_year_and_missing_opening_equity_are_not_synthesized():
    missing_year = [REPORTS[0], REPORTS[1], REPORTS[3], REPORTS[4]]
    assert financial_normalization.assess_five_year_history(normalized_reports(missing_year)).reason == "five_consecutive_completed_years_required"

    without_opening = deepcopy(REPORTS)
    without_opening[0].pop("opening_equity")
    assessment = financial_normalization.assess_five_year_history(normalized_reports(without_opening))
    assert assessment.comparable is False
    assert assessment.reason == "six_evidenced_equity_dates_required"
    assert normalized_reports(without_opening)[0].opening_equity is None


def test_missing_and_partial_fields_remain_unavailable():
    partial = deepcopy(REPORTS[0])
    partial.pop("current_assets")
    partial.pop("current_liabilities")
    partial.pop("interest_bearing_debt")
    partial.pop("unrestricted_cash")

    record = financial_normalization.normalize_annual_report(partial)

    assert record.interest_bearing_debt is None
    assert record.unrestricted_cash is None
    assert record.current_assets is None
    assert record.current_liabilities is None
    assert "missing_current_assets" in record.unavailable_reasons
    assert record.ordinary_owner_earnings.value == -2_500_000


def test_explicit_units_and_scales_are_preserved_without_magnitude_guessing():
    report = deepcopy(REPORTS[0])
    report["equity"]["value"] = "0.00012"

    record = financial_normalization.normalize_annual_report(report)

    assert record.equity.value == 120
    assert record.equity.source_value == Decimal("0.00012")
    assert record.equity.source_unit == "million XOF"
    assert record.equity.scale_to_xof == 1_000_000
    assert record.equity.value != 120_000_000


def test_debt_is_not_inferred_from_total_liabilities():
    report = deepcopy(REPORTS[0])
    report["total_liabilities"] = {"value": "75", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True}
    report.pop("interest_bearing_debt")

    record = financial_normalization.normalize_annual_report(report)

    assert record.interest_bearing_debt is None
    assert "missing_interest_bearing_debt" in record.unavailable_reasons


@pytest.mark.parametrize("restricted", [True, None])
def test_restricted_or_unknown_cash_is_not_unrestricted_cash(restricted):
    report = deepcopy(REPORTS[0])
    if restricted is None:
        report["unrestricted_cash"].pop("restricted")
    else:
        report["unrestricted_cash"]["restricted"] = restricted

    record = financial_normalization.normalize_annual_report(report)

    assert record.unrestricted_cash is None
    assert "cash_restriction_unknown_or_restricted" in record.unavailable_reasons


def test_owner_and_scope_are_checked_independently_for_available_fields():
    report = deepcopy(REPORTS[0])
    report.pop("ordinary_owner_earnings")
    report.pop("earnings_basis")
    report.pop("earnings_scope")
    report["equity_scope"] = "standalone"

    record = financial_normalization.normalize_annual_report(report)

    assert record.ordinary_owner_earnings is None
    assert record.equity is None
    assert "equity_owner_or_scope_unverified" in record.unavailable_reasons


def test_valid_owner_earnings_survives_missing_equity_counterpart():
    report = deepcopy(REPORTS[0])
    report.pop("equity")
    report.pop("equity_basis")
    report.pop("equity_scope")

    record = financial_normalization.normalize_annual_report(report)

    assert record.ordinary_owner_earnings.value == -2_500_000
    assert record.equity is None


def test_valid_equity_survives_missing_earnings_counterpart():
    report = deepcopy(REPORTS[0])
    report.pop("ordinary_owner_earnings")
    report.pop("earnings_basis")
    report.pop("earnings_scope")

    record = financial_normalization.normalize_annual_report(report)

    assert record.equity.value == 120_000_000
    assert record.ordinary_owner_earnings is None


@pytest.mark.parametrize(
    ("unit", "scale"),
    [("million XOF", "1000"), ("thousand XOF", "1000000"), ("XOF", "1000")],
)
def test_unsupported_unit_and_scale_pairs_are_unavailable(unit, scale):
    report = deepcopy(REPORTS[0])
    report["equity"]["unit"] = unit
    report["equity"]["scale_to_xof"] = scale

    record = financial_normalization.normalize_annual_report(report)

    assert record.equity is None
    assert "unsupported_equity_unit_scale" in record.unavailable_reasons


@pytest.mark.parametrize("opening_scope", [None, "unknown"])
def test_opening_equity_requires_known_matching_scope(opening_scope):
    report = deepcopy(REPORTS[0])
    if opening_scope is None:
        report["opening_equity"].pop("scope")
    else:
        report["opening_equity"]["scope"] = opening_scope

    record = financial_normalization.normalize_annual_report(report)

    assert record.opening_equity is None
    assert "opening_equity_basis_or_date_unverified" in record.unavailable_reasons


def test_unknown_publication_time_does_not_become_available_at_collection_time():
    report = deepcopy(REPORTS[0])
    report["publication"] = {"published_at": None, "evidenced": False}

    record = financial_normalization.normalize_annual_report(report)

    assert record.publication_status == "unknown"
    assert record.published_at is None
    assert record.collected_at == datetime(2025, 8, 1, 9, tzinfo=timezone.utc)
    assert financial_normalization.available_as_of(record, datetime(2025, 9, 1, tzinfo=timezone.utc)) is False


def test_published_at_is_distinct_from_collected_at_and_point_in_time_cutoff():
    record = normalized_reports()[0]

    assert record.published_at != record.collected_at
    assert financial_normalization.available_as_of(record, datetime(2020, 10, 14, tzinfo=timezone.utc)) is False
    assert financial_normalization.available_as_of(record, datetime(2020, 10, 15, 12, tzinfo=timezone.utc)) is False
    assert financial_normalization.available_as_of(record, datetime(2025, 8, 1, 9, tzinfo=timezone.utc)) is True


def test_nonpositive_equity_is_preserved_as_an_observation():
    report = deepcopy(REPORTS[0])
    report["equity"]["value"] = "-1"

    record = financial_normalization.normalize_annual_report(report)

    assert record.equity.value == -1_000_000
    assert record.equity.source_value == -1


def test_non_financial_fields_are_unavailable_for_financial_entities():
    report = deepcopy(REPORTS[0])
    report["financial_category"] = "bank"
    report["pnb"] = {"value": "900", "currency": "XOF", "unit": "million XOF", "scale_to_xof": "1000000", "evidenced": True}

    record = financial_normalization.normalize_annual_report(report)

    assert record.interest_bearing_debt is None
    assert record.unrestricted_cash is None
    assert record.current_assets is None
    assert record.current_liabilities is None
    assert "non_financial_inputs_not_applicable" in record.unavailable_reasons
    assert record.revenue is None


def test_bank_pnb_cannot_become_generic_revenue():
    report = deepcopy(REPORTS[0])
    report["financial_category"] = "bank"
    report["revenue"] = {
        "value": "900",
        "currency": "XOF",
        "unit": "million XOF",
        "scale_to_xof": "1000000",
        "evidenced": True,
    }
    report["pnb"] = report["revenue"]

    record = financial_normalization.normalize_annual_report(report)

    assert record.revenue is None
    assert "revenue_not_applicable_for_financial_entity" in record.unavailable_reasons
