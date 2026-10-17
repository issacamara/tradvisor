from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts" / "ordinary_capital.py"
SPEC = importlib.util.spec_from_file_location("ordinary_capital", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ordinary_capital = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ordinary_capital
SPEC.loader.exec_module(ordinary_capital)


def record(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "symbol": "ABC",
        "ordinary_shares": "1000000",
        "market_cap": {
            "value": "2500",
            "currency": "XOF",
            "unit": "million XOF",
            "scale_to_xof": "1000000",
        },
        "ownership_basis": "ordinary issued",
        "matching_basis": "issued",
        "share_class": "ordinary",
        "class_count": 1,
        "source_url": "https://source.example/abc",
        "source_date": "2024-12-31",
        "known_at": "2025-01-02T10:00:00+00:00",
    }
    result.update(overrides)
    return result


def test_normalizes_evidenced_ordinary_capital() -> None:
    result = ordinary_capital.normalize_ordinary_capitalization(
        record(treasury_shares="1000", share_class="ordinary")
    )

    assert result.symbol == "ABC"
    assert result.ordinary_shares == Decimal("1000000")
    assert result.market_cap == Decimal("2500000000")
    assert result.market_cap_source_value == Decimal("2500")
    assert result.market_cap_source_unit == "million XOF"
    assert result.market_cap_scale_to_xof == Decimal("1000000")
    assert result.ownership_basis == "issued"
    assert result.source_ownership_basis == "ordinary issued"
    assert result.treasury_shares == Decimal("1000")
    assert result.valuation_eligible is True
    assert result.unavailable_reasons == ()


def test_unknown_matching_basis_withholds_only_valuation() -> None:
    result = ordinary_capital.normalize_ordinary_capitalization(record(matching_basis=None))

    assert result.ordinary_shares == Decimal("1000000")
    assert result.market_cap == Decimal("2500000000")
    assert result.valuation_eligible is False
    assert result.unavailable_reasons == ("matching_basis_unknown",)


def test_rejects_unsupported_share_bases_and_multiclass_capital() -> None:
    with pytest.raises(ordinary_capital.CapitalizationError, match="ordinary-share ownership basis"):
        ordinary_capital.normalize_ordinary_capitalization(record(ownership_basis="free_float"))
    with pytest.raises(ordinary_capital.CapitalizationError, match="multiclass"):
        ordinary_capital.normalize_ordinary_capitalization(record(class_count=2))


def test_missing_class_evidence_and_non_positive_values_are_not_eligible() -> None:
    result = ordinary_capital.normalize_ordinary_capitalization(
        record(share_class=None, ordinary_shares="0", market_cap={"value": "0", "currency": "XOF", "unit": "XOF", "scale_to_xof": "1"})
    )

    assert result.valuation_eligible is False
    assert {
        "share_class_unknown",
        "ordinary_shares_non_positive",
        "market_cap_non_positive",
    }.issubset(result.unavailable_reasons)


def test_ordinary_label_without_class_cardinality_is_not_eligible() -> None:
    result = ordinary_capital.normalize_ordinary_capitalization(
        record(share_class="ordinary", class_count=None)
    )

    assert result.valuation_eligible is False
    assert "share_class_unknown" in result.unavailable_reasons


@pytest.mark.parametrize("basis", ["weighted average EPS", "eps shares"])
def test_rejects_weighted_average_and_eps_bases(basis: str) -> None:
    with pytest.raises(ordinary_capital.CapitalizationError, match="ordinary-share ownership basis"):
        ordinary_capital.normalize_ordinary_capitalization(record(ownership_basis=basis))


def test_basis_mismatch_keeps_metrics_but_withholds_valuation() -> None:
    result = ordinary_capital.normalize_ordinary_capitalization(
        record(ownership_basis="outstanding", matching_basis="issued")
    )

    assert result.market_cap == Decimal("2500000000")
    assert result.valuation_eligible is False
    assert result.unavailable_reasons == ("share_basis_mismatch",)


def test_scalar_market_cap_applies_declared_xof_scale() -> None:
    result = ordinary_capital.normalize_ordinary_capitalization(
        record(
            market_cap="2500",
            market_cap_currency="XOF",
            market_cap_unit="million XOF",
            market_cap_scale_to_xof="1000000",
        )
    )

    assert result.market_cap == Decimal("2500000000")
    assert result.valuation_eligible is True
