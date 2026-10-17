"""Derived history requirements for the V1 technical indicator chain."""

MIN_WARM_UP_OBSERVATIONS = 100


def required_indicator_observations(*periods: int) -> int:
    """Return the minimum dated observations needed for configured indicators."""

    if not periods or any(period < 1 for period in periods):
        raise ValueError("indicator periods must be positive")
    return max(MIN_WARM_UP_OBSERVATIONS, *(period + 1 for period in periods))


def required_market_days(*periods: int) -> int:
    """Convert the observation requirement into a bounded calendar-day fetch window."""

    return required_indicator_observations(*periods) * 3
