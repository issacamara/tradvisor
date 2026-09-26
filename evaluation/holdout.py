"""Deterministic evaluation metrics for known-at evidence only."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class Observation:
    session: str
    symbol: str
    action: str
    next_close_return: Decimal | None
    fee: Decimal
    eligible: bool


@dataclass(frozen=True, slots=True)
class HoldoutReport:
    observations: int
    eligible_observations: int
    return_total: Decimal
    max_drawdown: Decimal
    turnover: int
    coverage: Decimal
    concentration: Decimal
    look_ahead_blocked: bool


def evaluate(rows: Sequence[Observation], *, holdout_sessions: Iterable[str]) -> HoldoutReport:
    """Evaluate fixed actions; a row without a known next close is excluded."""

    holdout = set(holdout_sessions)
    if not holdout:
        raise ValueError("a predeclared holdout is required")
    selected = [row for row in rows if row.session in holdout]
    if any(row.next_close_return is None and row.action in {"buy", "sell"} for row in selected):
        raise ValueError("actionable rows require known-at next-close evidence")
    eligible = [row for row in selected if row.eligible and row.next_close_return is not None]
    returns = [row.next_close_return - row.fee for row in eligible if row.action == "buy"]
    total = sum(returns, Decimal("0"))
    running = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")
    for value in returns:
        running += value
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
    symbols = {row.symbol for row in eligible}
    return HoldoutReport(len(selected), len(eligible), total, drawdown, sum(row.action in {"buy", "sell"} for row in eligible), Decimal(len(eligible)) / Decimal(len(selected) or 1), Decimal(1) / Decimal(len(symbols) or 1), True)
