"""Validated scalar types for API v0.13 transport contracts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

INT64_MIN: Final = -(2**63)
INT64_MAX: Final = 2**63 - 1
MAX_SAFE_INTEGER: Final = 2**53 - 1
MAX_COMMAND_BYTES: Final = 16 * 1024
MICROS_PER_XOF: Final = 1_000_000
STARTING_CASH_MIN_XOF: Final = 100_000
STARTING_CASH_MAX_XOF: Final = 100_000_000
MAX_WHOLE_SHARES: Final = 1_000_000_000
FEE_RATE_PCT_MAX_INTEGER_DIGITS: Final = 12

OpaqueIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[\x21-\x7e]+$",
        strict=True,
    ),
]
WholeShares = Annotated[int, Field(strict=True, ge=1, le=MAX_WHOLE_SHARES)]
NonNegativeVersion = Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)]
Score = Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]

_NONNEGATIVE_DECIMAL = r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?$"
_SIGNED_DECIMAL = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?$"
_FEE_RATE_PCT_DECIMAL = r"^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?$"


def _canonical_fee_rate_pct(value: object) -> str:
    """Normalize an explicitly supplied API v0.13 fee percentage string."""

    import re

    if not isinstance(value, str) or re.fullmatch(_FEE_RATE_PCT_DECIMAL, value) is None:
        raise ValueError(
            "fee_rate_pct must be a nonnegative decimal string with at most "
            "twelve integer and six fractional digits"
        )
    decimal_value = Decimal(value)
    normalized = format(decimal_value.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


FeeRatePct = Annotated[str, BeforeValidator(_canonical_fee_rate_pct)]


def _decimal_to_micros(value: str, *, signed: bool) -> int:
    pattern = _SIGNED_DECIMAL if signed else _NONNEGATIVE_DECIMAL
    import re

    if re.fullmatch(pattern, value) is None:
        raise ValueError("amount must be a plain decimal string with at most six places")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("amount must be a valid decimal string") from error

    micros = decimal_value * MICROS_PER_XOF
    if micros != micros.to_integral_value():
        raise ValueError("amount precision exceeds six fractional digits")
    as_int = int(micros)
    if not INT64_MIN <= as_int <= INT64_MAX:
        raise ValueError("amount exceeds the supported signed 64-bit range")
    return as_int


def _canonical_money(value: str, *, signed: bool) -> str:
    micros = _decimal_to_micros(value, signed=signed)
    sign = "-" if micros < 0 else ""
    magnitude = abs(micros)
    return f"{sign}{magnitude // MICROS_PER_XOF}.{magnitude % MICROS_PER_XOF:06d}"


class Money(BaseModel):
    """An exact XOF transport value backed by checked micro-XOF units."""

    model_config = ConfigDict(extra="forbid", strict=True)

    amount: str
    currency: Literal["XOF"]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("amount must be a decimal string")
        return _canonical_money(value, signed=True)

    @property
    def micros(self) -> int:
        return _decimal_to_micros(self.amount, signed=True)


class NonNegativeMoney(Money):
    """Exact XOF value for request fields that cannot be negative."""

    @field_validator("amount")
    @classmethod
    def validate_nonnegative_amount(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("amount must be a decimal string")
        return _canonical_money(value, signed=False)


class SignedMoney(Money):
    """Exact XOF value for cash movements and P&L that may be negative."""


class StartingCash(NonNegativeMoney):
    """Whole-XOF setup/reset cash within the approved inclusive bounds."""

    @field_validator("amount")
    @classmethod
    def validate_starting_cash(cls, value: str) -> str:
        canonical = _canonical_money(value, signed=False)
        micros = _decimal_to_micros(canonical, signed=False)
        if micros % MICROS_PER_XOF != 0:
            raise ValueError("starting cash must be whole XOF")
        whole_xof = micros // MICROS_PER_XOF
        if not STARTING_CASH_MIN_XOF <= whole_xof <= STARTING_CASH_MAX_XOF:
            raise ValueError("starting cash is outside the approved range")
        return canonical
