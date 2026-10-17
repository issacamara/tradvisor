from backend.analysis.warmup import required_indicator_observations, required_market_days


def test_current_indicator_configuration_requires_100_observations() -> None:
    assert required_indicator_observations(20, 50, 14, 14) == 100
    assert required_market_days(20, 50, 14, 14) == 300


def test_history_requirement_grows_when_a_period_changes() -> None:
    assert required_indicator_observations(20, 120, 14, 14) == 121
    assert required_market_days(20, 120, 14, 14) == 363
