import pytest

from functions.financials import monthly_financials as mf
from functions.financials.fi1_job import MODEL_ORDER, parse_model_order


def test_monthly_default_is_the_shared_chain():
    assert mf.MODELS is MODEL_ORDER


def test_parse_model_order_accepts_provider_prefixed_unique_ids():
    assert parse_model_order("google/gemma-4-31b-it:free", "openai/gpt-4o-mini, ") == (
        "google/gemma-4-31b-it:free",
        "openai/gpt-4o-mini",
    )


@pytest.mark.parametrize(
    ("primary", "fallbacks"),
    [
        ("", ""),
        ("gemma-4-31b-it", ""),  # no provider prefix
        ("openai/gpt-4o-mini", "openai/gpt-4o-mini"),  # duplicate
        ("openai/gpt 4", ""),
    ],
)
def test_parse_model_order_rejects_bad_chains(primary, fallbacks):
    with pytest.raises(ValueError):
        parse_model_order(primary, fallbacks)


def test_monthly_config_rejects_unprefixed_model():
    with pytest.raises(ValueError):
        mf.config(
            {
                "TRADVISOR_TARGET_PROJECT_ID": "fixture-project",
                "TRADVISOR_FINANCIALS_MODEL_PRIMARY": "gemma-4-31b-it",
            }
        )
