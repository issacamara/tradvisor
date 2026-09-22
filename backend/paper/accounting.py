"""Exact, side-effect-free paper-trading accounting primitives.

All monetary values are signed 64-bit micro-XOF integers. Fee calculation is
the sole whole-XOF rounding boundary; allocation retains micro-XOF precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Final

from backend.contracts.scalars import INT64_MAX, INT64_MIN, MICROS_PER_XOF

_HUNDRED: Final = Decimal("100")


class AccountingError(ValueError):
    """Raised when an accounting input or checked monetary result is invalid."""


def _checked_micros(value: int, *, name: str) -> int:
    if not INT64_MIN <= value <= INT64_MAX:
        raise AccountingError(f"{name} exceeds the supported signed 64-bit range")
    return value


def _nonnegative_micros(value: int, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AccountingError(f"{name} must be a nonnegative micro-XOF integer")
    return _checked_micros(value, name=name)


def _positive_quantity(value: int, *, name: str = "quantity") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AccountingError(f"{name} must be a positive whole-share integer")
    return value


def _checked_product(left: int, right: int, *, name: str) -> int:
    return _checked_micros(left * right, name=name)


def _half_up_ratio(numerator: int, denominator: int, *, name: str) -> int:
    """Round a nonnegative integer ratio half-up without floating-point arithmetic."""

    if numerator < 0 or denominator <= 0:
        raise AccountingError(f"{name} requires a nonnegative numerator and positive denominator")
    return _checked_micros((numerator * 2 + denominator) // (denominator * 2), name=name)


def _fee_rate(value: Decimal | str) -> Decimal:
    try:
        rate = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise AccountingError("fee_rate_pct must be a finite nonnegative decimal") from error
    if not rate.is_finite() or rate < 0:
        raise AccountingError("fee_rate_pct must be a finite nonnegative decimal")
    return rate


def calculate_execution_fee_micros(
    *, quantity: int, closing_price_micros: int, fee_rate_pct: Decimal | str
) -> int:
    """Calculate an executed fee, rounded half-up once to a whole XOF."""

    quantity = _positive_quantity(quantity)
    price = _nonnegative_micros(closing_price_micros, name="closing_price_micros")
    rate = _fee_rate(fee_rate_pct)
    gross_amount = _checked_product(quantity, price, name="gross_amount_micros")
    fee_xof = (Decimal(gross_amount) / MICROS_PER_XOF * rate / _HUNDRED).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return _checked_micros(int(fee_xof) * MICROS_PER_XOF, name="execution_fee_micros")


@dataclass(frozen=True, slots=True)
class PositionAccounting:
    """The cost basis remaining for one long-only paper position."""

    quantity: int
    gross_cost_micros: int
    purchase_fee_micros: int

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity < 0:
            raise AccountingError("quantity must be a nonnegative whole-share integer")
        _nonnegative_micros(self.gross_cost_micros, name="gross_cost_micros")
        _nonnegative_micros(self.purchase_fee_micros, name="purchase_fee_micros")
        if self.quantity == 0 and (self.gross_cost_micros or self.purchase_fee_micros):
            raise AccountingError("an empty position cannot retain cost or purchase-fee residuals")

    @property
    def gross_average_entry_numerator_micros(self) -> int:
        if self.quantity == 0:
            raise AccountingError("an empty position has no average entry price")
        return self.gross_cost_micros


@dataclass(frozen=True, slots=True)
class BuyAccounting:
    position: PositionAccounting
    gross_purchase_cost_micros: int
    purchase_fee_micros: int
    cash_debit_micros: int


@dataclass(frozen=True, slots=True)
class SellAccounting:
    position: PositionAccounting
    gross_proceeds_micros: int
    sell_fee_micros: int
    allocated_gross_cost_micros: int
    allocated_purchase_fee_micros: int
    gross_realized_pnl_micros: int
    net_realized_pnl_micros: int
    net_cash_credit_micros: int


@dataclass(frozen=True, slots=True)
class ValuationAccounting:
    market_value_micros: int
    gross_unrealized_pnl_micros: int
    net_unrealized_pnl_micros: int


def apply_buy(
    position: PositionAccounting,
    *,
    quantity: int,
    closing_price_micros: int,
    purchase_fee_micros: int,
) -> BuyAccounting:
    """Add an executed purchase to the weighted gross-cost position basis."""

    quantity = _positive_quantity(quantity)
    price = _nonnegative_micros(closing_price_micros, name="closing_price_micros")
    fee = _nonnegative_micros(purchase_fee_micros, name="purchase_fee_micros")
    gross_cost = _checked_product(quantity, price, name="gross_purchase_cost_micros")
    next_position = PositionAccounting(
        quantity=position.quantity + quantity,
        gross_cost_micros=_checked_micros(
            position.gross_cost_micros + gross_cost, name="remaining_gross_cost_micros"
        ),
        purchase_fee_micros=_checked_micros(
            position.purchase_fee_micros + fee, name="remaining_purchase_fee_micros"
        ),
    )
    cash_debit = _checked_micros(gross_cost + fee, name="cash_debit_micros")
    return BuyAccounting(next_position, gross_cost, fee, cash_debit)


def apply_sell(
    position: PositionAccounting,
    *,
    quantity: int,
    closing_price_micros: int,
    sell_fee_micros: int,
) -> SellAccounting:
    """Allocate pre-sale basis, consuming all residuals when a position closes."""

    quantity = _positive_quantity(quantity)
    if position.quantity == 0 or quantity > position.quantity:
        raise AccountingError("sell quantity exceeds the executed position quantity")
    price = _nonnegative_micros(closing_price_micros, name="closing_price_micros")
    fee = _nonnegative_micros(sell_fee_micros, name="sell_fee_micros")
    final_sale = quantity == position.quantity
    allocated_cost = (
        position.gross_cost_micros
        if final_sale
        else _half_up_ratio(
            position.gross_cost_micros * quantity,
            position.quantity,
            name="allocated_gross_cost_micros",
        )
    )
    allocated_purchase_fee = (
        position.purchase_fee_micros
        if final_sale
        else _half_up_ratio(
            position.purchase_fee_micros * quantity,
            position.quantity,
            name="allocated_purchase_fee_micros",
        )
    )
    proceeds = _checked_product(quantity, price, name="gross_proceeds_micros")
    remaining_quantity = position.quantity - quantity
    next_position = PositionAccounting(
        quantity=remaining_quantity,
        gross_cost_micros=_checked_micros(
            position.gross_cost_micros - allocated_cost, name="remaining_gross_cost_micros"
        ),
        purchase_fee_micros=_checked_micros(
            position.purchase_fee_micros - allocated_purchase_fee,
            name="remaining_purchase_fee_micros",
        ),
    )
    gross_realized = _checked_micros(proceeds - allocated_cost, name="gross_realized_pnl_micros")
    net_realized = _checked_micros(
        gross_realized - allocated_purchase_fee - fee, name="net_realized_pnl_micros"
    )
    return SellAccounting(
        position=next_position,
        gross_proceeds_micros=proceeds,
        sell_fee_micros=fee,
        allocated_gross_cost_micros=allocated_cost,
        allocated_purchase_fee_micros=allocated_purchase_fee,
        gross_realized_pnl_micros=gross_realized,
        net_realized_pnl_micros=net_realized,
        net_cash_credit_micros=_checked_micros(proceeds - fee, name="net_cash_credit_micros"),
    )


def calculate_valuation(
    position: PositionAccounting, *, valuation_price_micros: int
) -> ValuationAccounting:
    """Value a position without estimating or subtracting any future sell fee."""

    price = _nonnegative_micros(valuation_price_micros, name="valuation_price_micros")
    market_value = _checked_product(position.quantity, price, name="market_value_micros")
    gross_unrealized = _checked_micros(
        market_value - position.gross_cost_micros, name="gross_unrealized_pnl_micros"
    )
    return ValuationAccounting(
        market_value_micros=market_value,
        gross_unrealized_pnl_micros=gross_unrealized,
        net_unrealized_pnl_micros=_checked_micros(
            gross_unrealized - position.purchase_fee_micros, name="net_unrealized_pnl_micros"
        ),
    )
