from __future__ import annotations

import pytest

from backend.analysis.batch import CalculationOutput
from backend.analysis.batch import StockCalculation
from backend.jobs.daily import AnalyticalInputSnapshot
from backend.jobs.runtime import BigQueryOutputCalculator, BigQuerySnapshotReader


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
    assert result.outputs == (
        CalculationOutput("ema", "available", {"ema20": 10.5}),
        CalculationOutput("rsi", "unavailable", reason_codes=("warming_up",)),
        CalculationOutput("atr", "available", {"atr14": 1.2}),
        CalculationOutput("traded_value", "available", {"median_xof": 5000000}),
    )


def test_bigquery_output_calculator_requires_complete_symbol_output() -> None:
    with pytest.raises(ValueError, match="no calculations"):
        BigQueryOutputCalculator().calculate(snapshot(), symbol="ORGT")


def test_snapshot_reader_rejects_identifier_injection() -> None:
    with pytest.raises(ValueError, match="plain project.dataset.table"):
        BigQuerySnapshotReader(object(), "dev.dataset.table; DROP TABLE x")
