import math
import pytest

from backend.analysis.rsi import rsi_series


def test_gain_only_returns_100():
    # 15 increasing prices
    closes = [i for i in range(1, 16)]
    rsi = rsi_series(closes)
    # After 14 periods, we have 1 RSI value
    assert len(rsi) == 1
    assert rsi[0] == 100.0


def test_loss_only_returns_0():
    # 15 decreasing prices
    closes = [i for i in range(15, 0, -1)]
    rsi = rsi_series(closes)
    assert len(rsi) == 1
    assert rsi[0] == 0.0


def test_flat_returns_50():
    # 15 identical prices
    closes = [100.0] * 15
    rsi = rsi_series(closes)
    assert len(rsi) == 1
    assert rsi[0] == 50.0


def test_unknown_input_interruption():
    # None input
    assert rsi_series(None) == []

    # Input with non-finite value
    assert rsi_series([1.0, 2.0, float("nan")]) == []

    # Input too short
    assert rsi_series([1.0, 2.0]) == []


def test_15_close_seed_known_value():
    # Common example from Wilder's original paper
    closes = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
    ]
    rsi = rsi_series(closes)
    # Only one RSI value after 14 periods
    assert len(rsi) == 1
    # Expected RSI from Wilder's example: 70.464
    assert math.isclose(rsi[0], 70.464, rel_tol=1e-3, abs_tol=1e-3)


def test_mature_chain_and_correction_replay():
    # Start with 15 points (same as previous test)
    closes = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
    ]
    rsi_initial = rsi_series(closes)
    assert len(rsi_initial) == 1
    assert math.isclose(rsi_initial[0], 70.464, rel_tol=1e-3, abs_tol=1e-3)

    # Append a new close and recompute
    new_close = 46.00
    closes.append(new_close)
    rsi_updated = rsi_series(closes)
    # Now we have two RSI values
    assert len(rsi_updated) == 2
    # The second RSI should be close to the known value from Wilder's example
    # (computed manually or using a trusted library).  We use a tolerance.
    assert math.isclose(rsi_updated[1], 66.348, rel_tol=1e-3, abs_tol=1e-3)
