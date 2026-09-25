from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel

from backend.analysis.batch import (
    BatchValidationError,
    CalculationOutput,
    InputNotReadyError,
    StockCalculation,
    build_analytical_batch,
)


class SampleCalculation(BaseModel):
    score: Decimal
    observed_at: datetime


def _build(**overrides: object):
    values: dict[str, object] = {
        "catalog_id": "casablanca",
        "effective_session": date(2026, 9, 24),
        "input_snapshot_id": "catalog-input-01",
        "rule_version": "v1",
        "expected_symbols": ["AAA", "BBB"],
        "expected_output_names": ["growth", "swing"],
        "stocks": [
            StockCalculation(
                "BBB",
                (
                    CalculationOutput(
                        "growth",
                        "available",
                        SampleCalculation(
                            score=Decimal("12.50"),
                            observed_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
                        ),
                    ),
                    CalculationOutput("swing", "unavailable", reason_codes=("warming_up",)),
                ),
            ),
            StockCalculation(
                "AAA",
                (
                    CalculationOutput("growth", "unavailable", reason_codes=("missing_report",)),
                    CalculationOutput("swing", "unavailable", reason_codes=("missing_prices",)),
                ),
            ),
        ],
        "inputs_ready": True,
    }
    values.update(overrides)
    return build_analytical_batch(**values)  # type: ignore[arg-type]


def test_identical_retry_is_canonical_and_order_independent() -> None:
    first = _build()
    retry = _build()

    assert first == retry
    assert first.batch_id == retry.batch_id
    assert first.manifest.content_sha256 == retry.manifest.content_sha256
    assert tuple(stock.symbol for stock in first.stocks) == ("AAA", "BBB")
    assert first.manifest.symbols[1].availability[0].name == "growth"


def test_correction_creates_new_revision_and_keeps_old_batch_reference() -> None:
    original = _build()
    corrected = _build(
        input_snapshot_id="catalog-input-02",
        revision=2,
        supersedes_batch_id=original.batch_id,
    )

    assert corrected.batch_id != original.batch_id
    assert corrected.revision == 2
    assert corrected.supersedes_batch_id == original.batch_id
    assert original.revision == 1
    assert original.manifest.batch_id == original.batch_id


@pytest.mark.parametrize(
    "kwargs",
    [
        {"inputs_ready": False},
        {"pending_inputs": ("prices:AAA",)},
    ],
)
def test_input_readiness_gates_batch(kwargs: dict[str, object]) -> None:
    with pytest.raises(InputNotReadyError):
        _build(**kwargs)


def test_partial_per_stock_availability_is_manifested_explicitly() -> None:
    batch = _build()

    aaa = batch.manifest.symbols[0]
    bbb = batch.manifest.symbols[1]
    assert len(aaa.availability) == 2
    assert aaa.availability[0].status == "unavailable"
    assert aaa.availability[0].reason_codes == ("missing_report",)
    assert {item.name: item.status for item in bbb.availability} == {
        "growth": "available",
        "swing": "unavailable",
    }


def test_incomplete_catalog_is_rejected_before_batch_is_returned() -> None:
    with pytest.raises(BatchValidationError, match="complete declared catalog"):
        _build(stocks=[])


def test_available_output_requires_value_and_unavailable_requires_reason() -> None:
    invalid_stocks = [
        StockCalculation(
            "AAA",
            (
                CalculationOutput("growth", "available"),
                CalculationOutput("swing", "unavailable", reason_codes=("warming_up",)),
            ),
        ),
        StockCalculation(
            "BBB",
            (
                CalculationOutput("growth", "unavailable"),
                CalculationOutput("swing", "unavailable", reason_codes=("warming_up",)),
            ),
        ),
    ]
    with pytest.raises(BatchValidationError):
        _build(stocks=invalid_stocks)


def test_every_catalog_stock_must_declare_each_output_family() -> None:
    with pytest.raises(BatchValidationError, match="every catalog output family"):
        _build(
            stocks=[
                StockCalculation(
                    "AAA",
                    (CalculationOutput("growth", "unavailable", reason_codes=("missing_report",)),),
                ),
                StockCalculation(
                    "BBB",
                    (
                        CalculationOutput("growth", "unavailable", reason_codes=("missing_report",)),
                        CalculationOutput("swing", "unavailable", reason_codes=("warming_up",)),
                    ),
                ),
            ]
        )
