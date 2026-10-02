from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json

import pytest

from backend.analysis.batch import CalculationOutput
from backend.analysis.batch import StockCalculation
from backend.analysis.batch import build_analytical_batch
from backend.jobs.daily import AnalyticalInputSnapshot
from backend.jobs.runtime import BigQueryOutputCalculator, BigQuerySnapshotReader
from backend.openapi import LongTermRankedCompany, SwingRecommendation


def snapshot() -> AnalyticalInputSnapshot:
    return AnalyticalInputSnapshot(
        name="analysis/2026-09-27",
        catalog_id="brvm",
        effective_session="2026-09-27",
        input_snapshot_id="inputs:1",
        rule_version="rules:v1",
        expected_symbols=("NTLC",),
        expected_output_names=("atr", "ema", "rsi", "traded_value"),
        payload={
            "calculations": {
                "NTLC": {
                    "ema": {"status": "available", "value": {"ema20": 10.5}},
                    "rsi": {"status": "unavailable", "reason_codes": ["warming_up"]},
                    "atr": {"status": "available", "value": {"atr14": 1.2}},
                    "traded_value": {"status": "available", "value": {"median_xof": 5000000}},
                }
            }
        },
    )


def test_bigquery_output_calculator_preserves_precomputed_contract() -> None:
    result = BigQueryOutputCalculator().calculate(snapshot(), symbol="NTLC")

    assert isinstance(result, StockCalculation)
    assert result.outputs[:4] == (
        CalculationOutput("ema", "available", {"ema20": 10.5}),
        CalculationOutput("rsi", "unavailable", reason_codes=("warming_up",)),
        CalculationOutput("atr", "available", {"atr14": 1.2}),
        CalculationOutput("traded_value", "available", {"median_xof": 5000000}),
    )


def test_bigquery_output_calculator_marks_missing_symbol_outputs_unavailable() -> None:
    result = BigQueryOutputCalculator().calculate(snapshot(), symbol="ORGT")

    assert all(output.status == "unavailable" for output in result.outputs if output.name != "long_term")
    assert next(output for output in result.outputs if output.name == "long_term").status == "available"
    assert {output.name for output in result.outputs} == {"ema", "rsi", "atr", "traded_value", "long_term"}


def test_bigquery_output_calculator_rejects_unknown_status() -> None:
    invalid = snapshot()
    invalid.payload["calculations"]["NTLC"]["ema"]["status"] = "partial"  # type: ignore[index]

    with pytest.raises(ValueError, match="status must be available or unavailable"):
        BigQueryOutputCalculator().calculate(invalid, symbol="NTLC")


def test_bigquery_output_calculator_serializes_chart_prices_as_xof_money() -> None:
    source = snapshot()
    source.payload["market_data"] = [{
        "symbol": "NTLC", "session_date": "2026-09-27", "open": 100,
        "high": 110, "low": 90, "close": 105, "volume": 12,
    }]

    chart = next(output for output in BigQueryOutputCalculator().calculate(source, symbol="NTLC").outputs if output.name == "chart")
    point = chart.value["points"][0]
    assert point["close"] == {"amount": "105", "currency": "XOF"}
    assert point["last_traded_close"] == {"amount": "105", "currency": "XOF"}


def test_bigquery_output_calculator_derives_swing_recommendation_from_shares() -> None:
    source = snapshot()
    source.payload["market_data"] = [
        {
            "symbol": "NTLC",
            "session_date": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
            "open": 100 + index,
            "high": 102 + index,
            "low": 98 + index,
            "close": 100 + index,
            "volume": 100000,
        }
        for index in range(260)
    ]

    swing = next(
        output for output in BigQueryOutputCalculator().calculate(source, symbol="NTLC").outputs
        if output.name == "swing"
    )

    assert swing.status == "available"
    assert swing.value["symbol"] == "NTLC"
    assert swing.value["buy_strength"]["status"] == "assessable"
    assert swing.value["indicators"]["ema20"]["status"] == "assessable"
    assert swing.value["indicators"]["traded_value20"]["value"] == 34950000.0


def test_development_long_term_publishes_partial_financial_evidence() -> None:
    source = snapshot()
    source = replace(source, payload={
        **source.payload,
        "financial_data": [
            {"symbol": "NTLC", "fiscal_year": year, "revenue": 1000 + year,
             "net_income": 100 + (year - 2023) * 20, "total_equity": 900,
            "collected_at": "2026-09-22T00:00:00+00:00", "document_link": "gs://archive/rapport - Exercice 2023.pdf"}
            for year in (2023, 2024, 2025)
        ],
    })

    long_term = next(
        output for output in BigQueryOutputCalculator().calculate(source, symbol="NTLC").outputs
        if output.name == "long_term"
    )

    assert long_term.value["growth"]["advisory_state"] == "low_score"
    assert set(long_term.value["growth"]["dimension_contributions"]) == {"earnings_growth", "profitability"}
    assert long_term.value["growth"]["overall_score"]["status"] == "warming_up"


def test_development_swing_output_replaces_placeholder_and_builds_complete_batch() -> None:
    source = snapshot()
    source = replace(
        source,
        expected_output_names=("atr", "chart", "ema", "long_term", "rsi", "swing", "traded_value"),
        payload={
            **source.payload,
            "market_data": [
                {
                    "symbol": "NTLC",
                    "session_date": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
                    "open": 100 + index,
                    "high": 102 + index,
                    "low": 98 + index,
                    "close": 100 + index,
                    "volume": 100000,
                }
                for index in range(260)
            ],
        },
    )

    result = BigQueryOutputCalculator().calculate(source, symbol="NTLC")
    swing_outputs = [output for output in result.outputs if output.name == "swing"]

    assert len(swing_outputs) == 1
    assert swing_outputs[0].status == "available"
    SwingRecommendation.model_validate_json(json.dumps(swing_outputs[0].value))
    build_analytical_batch(
        catalog_id=source.catalog_id,
        effective_session=source.effective_session,
        input_snapshot_id=source.input_snapshot_id,
        rule_version=source.rule_version,
        expected_symbols=source.expected_symbols,
        expected_output_names=source.expected_output_names,
        stocks=(result,),
        inputs_ready=source.inputs_ready,
        pending_inputs=source.pending_inputs,
        revision=source.revision,
        supersedes_batch_id=source.supersedes_batch_id,
        published_at=source.published_at,
        strategy_id=source.strategy_id,
    )


def test_development_swing_requires_warmup_history() -> None:
    source = snapshot()
    source = replace(
        source,
        expected_output_names=("atr", "chart", "ema", "rsi", "swing", "traded_value"),
        payload={
            **source.payload,
            "market_data": [
                {
                    "symbol": "NTLC",
                    "session_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
                    "open": 100,
                    "high": 102,
                    "low": 98,
                    "close": 100,
                    "volume": 100000,
                }
                for index in range(100)
            ],
        },
    )

    swing = next(
        output for output in BigQueryOutputCalculator().calculate(source, symbol="NTLC").outputs
        if output.name == "swing"
    )

    assert swing.status == "available"
    assert swing.value["entry_action"] == "insufficient_data"
    assert swing.value["buy_strength"]["value"] is None


def test_development_publication_exposes_long_term_company_with_explicit_missing_evidence() -> None:
    source = snapshot()

    long_term = next(
        output
        for output in BigQueryOutputCalculator().calculate(source, symbol="NTLC").outputs
        if output.name == "long_term"
    )

    assert long_term.status == "available"
    company = LongTermRankedCompany.model_validate_json(json.dumps(long_term.value))
    assert company.symbol == "NTLC"
    assert company.growth.advisory_state == "insufficient_evidence"
    assert company.growth.overall_score.status == "missing_inputs"
    assert company.growth.overall_score.value is None
    assert company.dividend_research.dividend_score.status == "deferred_scope"


def test_precomputed_long_term_output_is_preserved() -> None:
    source = snapshot()
    expected = {
        "company_id": "brvm:NTLC",
        "symbol": "NTLC",
        "result": {
            "company_id": "brvm:NTLC",
            "growth": {"objective": "growth", "overall_score": {"status": "missing_inputs", "value": None, "unit": "score", "reason_codes": ["annual_financial_history_incomplete"]}},
            "dividend": {"objective": "dividend", "overall_score": {"status": "deferred_scope", "value": None, "unit": "score", "reason_codes": ["dividend_scoring_deferred_v1"]}},
            "balanced": {"objective": "balanced", "overall_score": {"status": "deferred_scope", "value": None, "unit": "score", "reason_codes": ["balanced_scoring_deferred_v1"]}},
            "revision": {"revision": 1, "known_at": "1970-01-01T00:00:00Z", "provenance": {"source_id": "development-publication", "collected_at": "1970-01-01T00:00:00Z", "basis": "modeled"}},
        },
        "growth": {"growth_score": {"status": "missing_inputs", "value": None, "unit": "score", "reason_codes": ["annual_financial_history_incomplete"]}, "overall_score": {"status": "missing_inputs", "value": None, "unit": "score", "reason_codes": ["annual_financial_history_incomplete"]}, "dimension_contributions": {}, "advisory_state": "insufficient_evidence", "reasons": [{"code": "annual_financial_history_incomplete", "message": "Three consecutive comparable annual reports are not available."}]},
        "dividend_research": {"payments": [], "coverage": [], "trailing_ordinary_yield": None, "dividend_score": {"status": "deferred_scope", "value": None, "unit": "score", "reason_codes": ["dividend_scoring_deferred_v1"]}},
    }
    source.payload["calculations"]["NTLC"]["long_term"] = {"status": "available", "value": expected}

    result = BigQueryOutputCalculator().calculate(source, symbol="NTLC")
    actual = next(output for output in result.outputs if output.name == "long_term")

    assert actual.value == expected


def test_snapshot_reader_rejects_identifier_injection() -> None:
    with pytest.raises(ValueError, match="plain project.dataset.table"):
        BigQuerySnapshotReader(object(), "dev.dataset.table; DROP TABLE x")
