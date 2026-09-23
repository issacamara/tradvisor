"""
Implementation of Wilder's RSI (Relative Strength Index) with 14-period default.
The module exposes a single function `rsi_series` that accepts a list of
closing prices and returns a list of unrounded RSI values.  The function
handles edge cases such as insufficient data, None/NaN values, and
unknown inputs by returning an empty list.

The RSI calculation follows the Wilder smoothing method:
    - For the first RSI value, use the simple average of gains and losses
      over the first `period` periods.
    - For subsequent values, use the recursive smoothing formula:
        avg_gain = (prev_avg_gain * (period - 1) + current_gain) / period
        avg_loss = (prev_avg_loss * (period - 1) + current_loss) / period
    - RSI = 100 - (100 / (1 + avg_gain / avg_loss))
      with special handling for avg_loss == 0 (RSI = 100) and
      avg_gain == 0 (RSI = 0).

The function returns RSI values for each close after the initial
`period` data points.  No rounding is performed; callers can round
as needed.

Example:
    >>> closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10,
    ...           45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
    ...           46.28]
    >>> rsi_series(closes)
    [70.464, ...]  # first RSI value after 14 periods
"""

from __future__ import annotations

from math import isfinite
from typing import Iterable, List, Sequence

__all__ = ["rsi_series"]


def _is_valid_price(value: float) -> bool:
    """Return True if value is a finite float."""
    return isinstance(value, (float, int)) and isfinite(value)


def rsi_series(
    closes: Sequence[float] | None, period: int = 14
) -> List[float]:
    """
    Compute Wilder's RSI series for a sequence of closing prices.

    Parameters
    ----------
    closes : Sequence[float] | None
        Sequence of closing prices.  If None or contains any non-finite
        values, an empty list is returned.
    period : int, default 14
        The lookback period for RSI calculation.

    Returns
    -------
    List[float]
        List of RSI values, one per close after the initial `period`
        data points.  The list length is ``max(0, len(closes) - period)``.
    """
    # Validate input
    if closes is None:
        return []

    try:
        closes_iter = list(closes)
    except Exception:
        return []

    if len(closes_iter) < period + 1:
        # Not enough data to compute even the first RSI
        return []

    # Ensure all values are finite numbers
    if not all(_is_valid_price(v) for v in closes_iter):
        return []

    rsi_values: List[float] = []

    # Compute initial average gain and loss over the first `period` periods
    gains: List[float] = []
    losses: List[float] = []

    for i in range(1, period + 1):
        change = closes_iter[i] - closes_iter[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-change)

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    # Helper to compute RSI from avg_gain and avg_loss
    def _calc_rsi(g: float, l: float) -> float:
        if l == 0.0:
            return 100.0
        if g == 0.0:
            return 0.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    # First RSI value corresponds to the close at index `period`
    rsi_values.append(_calc_rsi(avg_gain, avg_loss))

    # Iterate over remaining closes
    for i in range(period + 1, len(closes_iter)):
        change = closes_iter[i] - closes_iter[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        # Wilder smoothing
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        rsi_values.append(_calc_rsi(avg_gain, avg_loss))

    return rsi_values
