"""Retry-safe staging and loading tests for shares and financials."""

from __future__ import annotations

from types import ModuleType
import pandas as pd
import pytest

from loads_support import (
    _FakeBigQueryClient,
    loader,
    _rows,
)  # noqa: F401 (imported fixtures)


def test_retries_and_revision_batches_use_isolated_staging(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    source_keys = ["symbol", "fiscal_year", "document_link"]
    first = _rows()
    load_id = helper.upsert_into_bigquery(
        first, "project", "stocks", "financials", source_keys, run_id="run-one"
    )
    retry_id = helper.upsert_into_bigquery(
        first, "project", "stocks", "financials", source_keys, run_id="run-two"
    )

    assert retry_id == load_id
    assert [call[0] for call in client.load_calls] == [
        "project.stocks.financials__stage_run-one",
        "project.stocks.financials__stage_run-two",
    ]
    assert all(
        "ON target.`symbol` = source.`symbol`" in query
        and "target.`fiscal_year` = source.`fiscal_year`" in query
        and "target.`document_link` = source.`document_link`" in query
        for query in client.merge_queries
    )
    assert len(client.tables["project.stocks.financials"]) == 1

    revised = first.iloc[[0]].copy()
    revised["document_link"] = "gs://archive/report-2.pdf"
    revised["net_income"] = 125
    overlap = pd.concat([first.iloc[[0]], revised], ignore_index=True)
    helper.upsert_into_bigquery(
        overlap, "project", "stocks", "financials", source_keys, run_id="run-three"
    )

    stored = client.tables["project.stocks.financials"]
    assert len(stored) == 2
    assert {row["document_link"] for row in stored} == {
        "gs://archive/report-1.pdf",
        "gs://archive/report-2.pdf",
    }
    assert len(set(client.deleted_tables)) == 3
    assert all("DELETE FROM" not in query.upper() for query in client.merge_queries)


def _share_rows(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "name": f"{symbol} SA",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 100.0,
                "date": "2026-10-16",
            }
        ]
    )


def test_share_runs_use_managed_staging_without_cross_contamination(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    staging_id = "project.stocks.shares_staging"
    client.stages[staging_id] = [{"run_id": "other-run", **_share_rows("OTHER").iloc[0]}]

    helper.upsert_shares_and_archive(
        _share_rows("ABC"), "project", "stocks", lambda: None, run_id="run-one"
    )
    helper.upsert_shares_and_archive(
        _share_rows("XYZ"), "project", "stocks", lambda: None, run_id="run-two"
    )

    assert [call[0] for call in client.load_calls] == [staging_id, staging_id]
    assert all(call[1].write_disposition == "WRITE_APPEND" for call in client.load_calls)
    assert {row["symbol"] for row in client.tables["project.stocks.shares"]} == {
        "ABC",
        "XYZ",
    }
    assert client.stages[staging_id] == [
        {"run_id": "other-run", **_share_rows("OTHER").iloc[0]}
    ]
    assert all("WHERE `run_id` = @run_id" in query for query in client.merge_queries)
    assert client.cleanup_run_ids == ["run-one", "run-one", "run-two", "run-two"]
    assert client.deleted_tables == []


def test_missing_managed_share_staging_fails_before_archive(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    client.load_error = RuntimeError("Not found: project.stocks.shares_staging")
    archived: list[bool] = []

    with pytest.raises(RuntimeError, match="Not found"):
        helper.upsert_shares_and_archive(
            _share_rows("ABC"),
            "project",
            "stocks",
            lambda: archived.append(True),
            run_id="missing-stage",
        )

    assert archived == []
    assert client.merge_queries == []
    assert client.deleted_tables == []


def _financial_rows(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "fiscal_year": 2025,
                "revenue": 100.0,
                "net_income": 20.0,
                "total_debt": 30.0,
                "cash_and_cash_equivalents": 40.0,
                "total_equity": 50.0,
                "document_link": f"gs://archive/{symbol}.pdf",
                "collected_at": "2026-10-16 00:00:00",
            }
        ]
    )


def test_financial_runs_use_managed_staging_without_cross_contamination(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    staging_id = "project.stocks.financials_staging"
    client.stages[staging_id] = [
        {"run_id": "other-run", **_financial_rows("OTHER").iloc[0].to_dict()}
    ]

    helper.upsert_financials_and_archive(
        _financial_rows("ABC"), None, "project", "stocks", lambda: None, run_id="run-one"
    )
    helper.upsert_financials_and_archive(
        _financial_rows("XYZ"), None, "project", "stocks", lambda: None, run_id="run-two"
    )

    assert [call[0] for call in client.load_calls] == [staging_id, staging_id]
    assert all(call[1].write_disposition == "WRITE_APPEND" for call in client.load_calls)
    assert {row["symbol"] for row in client.tables["project.stocks.financials"]} == {
        "ABC",
        "XYZ",
    }
    assert client.stages[staging_id] == [
        {"run_id": "other-run", **_financial_rows("OTHER").iloc[0].to_dict()}
    ]
    assert all("WHERE `run_id` = @run_id" in query for query in client.merge_queries)
    assert client.cleanup_run_ids[-4:] == ["run-one", "run-one", "run-two", "run-two"]
    assert client.deleted_tables == []


def test_financial_collected_at_is_loaded_as_a_utc_timestamp(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader

    helper.upsert_financials_and_archive(
        _financial_rows("ABC"), None, "project", "stocks", lambda: None, run_id="timestamp"
    )

    loaded = client.loaded_dataframes[0]
    assert str(loaded["collected_at"].dtype) == "datetime64[ns, UTC]"
    assert loaded["collected_at"].iloc[0] == pd.Timestamp("2026-10-16T00:00:00Z")


def test_financial_fiscal_year_string_is_normalized_before_dataframe_load(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    rows = _financial_rows("ABC")
    rows["fiscal_year"] = "2025"

    helper.upsert_financials_and_archive(
        rows, None, "project", "stocks", lambda: None, run_id="string-year"
    )

    loaded_year = client.loaded_dataframes[0]["fiscal_year"].iloc[0]
    assert loaded_year == 2025
    assert pd.api.types.is_integer_dtype(
        client.loaded_dataframes[0]["fiscal_year"].dtype
    )


@pytest.mark.parametrize(
    "fiscal_year", ["year", "2025.0", None, 0, 10000, 2025.5, True]
)
def test_invalid_financial_fiscal_year_fails_before_bigquery_load(
    loader: tuple[ModuleType, _FakeBigQueryClient], fiscal_year: object
) -> None:
    helper, client = loader
    rows = _financial_rows("ABC")
    rows["fiscal_year"] = fiscal_year

    with pytest.raises(ValueError, match="fiscal_year must be an integer year"):
        helper.upsert_financials_and_archive(
            rows, None, "project", "stocks", lambda: None, run_id="invalid-year"
        )

    assert client.load_calls == []
    assert client.cleanup_queries == []


def test_missing_managed_financial_staging_fails_before_archive(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    client.load_error = RuntimeError("Not found: project.stocks.financials_staging")
    archived: list[bool] = []

    with pytest.raises(RuntimeError, match="Not found"):
        helper.upsert_financials_and_archive(
            _financial_rows("ABC"), None, "project", "stocks", lambda: archived.append(True), run_id="missing-stage"
        )

    assert archived == []
    assert client.merge_queries == []
    assert client.deleted_tables == []
