"""Regression tests for approved paper-accounting rules."""

from __future__ import annotations

import pytest

from backend.contracts.scalars import INT64_MAX, MICROS_PER_XOF
from backend.paper.accounting import (
    AccountingError,
    PositionAccounting,
    apply_buy,
    apply_sell,
    calculate_execution_fee_micros,
    calculate_valuation,
)


def xof(amount: int) -> int:
    return amount * MICROS_PER_XOF


def test_published_weighted_cost_fixture_realizes_880_xof_net_pnl() -> None:
    position = PositionAccounting(quantity=0, gross_cost_micros=0, purchase_fee_micros=0)
    first_buy = apply_buy(position, quantity=10, closing_price_micros=xof(1_000), purchase_fee_micros=xof(100))
    second_buy = apply_buy(
        first_buy.position, quantity=10, closing_price_micros=xof(1_200), purchase_fee_micros=xof(120)
    )

    sale = apply_sell(
        second_buy.position, quantity=5, closing_price_micros=xof(1_300), sell_fee_micros=xof(65)
    )

    assert second_buy.position == PositionAccounting(20, xof(22_000), xof(220))
    assert sale.allocated_gross_cost_micros == xof(5_500)
    assert sale.allocated_purchase_fee_micros == xof(55)
    assert sale.gross_realized_pnl_micros == xof(1_000)
    assert sale.net_realized_pnl_micros == xof(880)
    assert sale.position == PositionAccounting(15, xof(16_500), xof(165))


def test_execution_fee_rounds_half_up_once_to_whole_xof() -> None:
    assert calculate_execution_fee_micros(
        quantity=1, closing_price_micros=xof(1_005), fee_rate_pct="0.05"
    ) == xof(1)
    assert calculate_execution_fee_micros(
        quantity=1, closing_price_micros=xof(1_004), fee_rate_pct="0.05"
    ) == xof(1)
    assert calculate_execution_fee_micros(
        quantity=1, closing_price_micros=xof(1_000), fee_rate_pct="0.049"
    ) == 0


def test_partial_allocations_round_to_micro_and_final_sale_consumes_residuals() -> None:
    position = PositionAccounting(quantity=3, gross_cost_micros=5, purchase_fee_micros=2)
    first_sale = apply_sell(position, quantity=1, closing_price_micros=10, sell_fee_micros=0)
    final_sale = apply_sell(first_sale.position, quantity=2, closing_price_micros=10, sell_fee_micros=0)

    assert first_sale.allocated_gross_cost_micros == 2
    assert first_sale.allocated_purchase_fee_micros == 1
    assert first_sale.position == PositionAccounting(2, 3, 1)
    assert final_sale.allocated_gross_cost_micros == 3
    assert final_sale.allocated_purchase_fee_micros == 1
    assert final_sale.position == PositionAccounting(0, 0, 0)


def test_high_sell_fee_can_exceed_proceeds_without_double_counting_purchase_fee() -> None:
    position = PositionAccounting(quantity=1, gross_cost_micros=xof(100), purchase_fee_micros=xof(10))
    sale = apply_sell(position, quantity=1, closing_price_micros=xof(50), sell_fee_micros=xof(75))

    assert sale.gross_realized_pnl_micros == -xof(50)
    assert sale.net_realized_pnl_micros == -xof(135)
    assert sale.net_cash_credit_micros == -xof(25)


def test_valuation_does_not_subtract_hypothetical_future_fee_or_allocated_purchase_fee_twice() -> None:
    position = PositionAccounting(quantity=2, gross_cost_micros=xof(200), purchase_fee_micros=xof(20))
    valuation = calculate_valuation(position, valuation_price_micros=xof(120))

    assert valuation.market_value_micros == xof(240)
    assert valuation.gross_unrealized_pnl_micros == xof(40)
    assert valuation.net_unrealized_pnl_micros == xof(20)


def test_checked_results_reject_overflow_and_overselling() -> None:
    with pytest.raises(AccountingError, match="gross_amount_micros"):
        calculate_execution_fee_micros(
            quantity=2, closing_price_micros=INT64_MAX, fee_rate_pct="0"
        )
    with pytest.raises(AccountingError, match="remaining_gross_cost_micros"):
        apply_buy(
            PositionAccounting(quantity=1, gross_cost_micros=INT64_MAX, purchase_fee_micros=0),
            quantity=1,
            closing_price_micros=1,
            purchase_fee_micros=0,
        )
    with pytest.raises(AccountingError, match="sell quantity"):
        apply_sell(
            PositionAccounting(quantity=1, gross_cost_micros=xof(1), purchase_fee_micros=0),
            quantity=2,
            closing_price_micros=xof(1),
            sell_fee_micros=0,
        )
