from __future__ import annotations

import pytest

from backend.jobs.financial_precompute import build_financial_precompute_sql


def test_precompute_selects_only_latest_three_years_per_symbol() -> None:
    sql = build_financial_precompute_sql(
        "dev-tradvisor.stocks.financials",
        "dev-tradvisor.stocks.financials_analytical",
    )

    assert "PARTITION BY DATE(fiscal_year, 12, 31)" in sql
    assert "CLUSTER BY symbol" in sql
    assert "ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) <= 3" in sql
    assert "FROM `dev-tradvisor.stocks.financials`" in sql


@pytest.mark.parametrize("value", ["", "bad table", "bad;table", "`bad.table`"])
def test_precompute_rejects_untrusted_table_identifiers(value: str) -> None:
    with pytest.raises(ValueError):
        build_financial_precompute_sql(value, "dev-tradvisor.stocks.financials_analytical")
