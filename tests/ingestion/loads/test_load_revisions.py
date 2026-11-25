"""Revision identity and insert-only revision tests."""

from __future__ import annotations

from types import ModuleType
import pandas as pd
import pytest

from loads_support import (
    _FakeBigQueryClient,
    loader,
    _rows,
)  # noqa: F401 (imported fixtures)


def test_conflicting_duplicate_source_keys_are_rejected_before_bigquery(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    rows = _rows().iloc[[0]].copy()
    conflict = rows.copy()
    conflict["net_income"] = 101

    with pytest.raises(ValueError, match="conflicting values for the same source key"):
        helper.upsert_into_bigquery(
            pd.concat([rows, conflict], ignore_index=True),
            "project",
            "stocks",
            "financials",
            ["symbol", "fiscal_year", "document_link"],
            run_id="conflicting-run",
        )

    assert client.load_calls == []
    assert client.merge_queries == []


def test_archive_failure_can_retry_without_duplicate_or_history_deletion(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    source_keys = ["symbol", "fiscal_year", "document_link"]
    archive_calls = 0

    def fail_once() -> None:
        nonlocal archive_calls
        archive_calls += 1
        if archive_calls == 1:
            raise OSError("archive temporarily unavailable")

    with pytest.raises(OSError, match="archive temporarily unavailable"):
        helper.upsert_and_archive(
            _rows(),
            "project",
            "stocks",
            "financials",
            source_keys,
            fail_once,
            run_id="archive-retry-one",
        )

    retry_id = helper.upsert_and_archive(
        _rows(),
        "project",
        "stocks",
        "financials",
        source_keys,
        fail_once,
        run_id="archive-retry-two",
    )

    assert len(client.tables["project.stocks.financials"]) == 1
    assert retry_id[:63] == client.load_calls[0][1].labels["tradvisor_load_id"]
    assert len(client.load_calls) == 2
    assert len(set(call[0] for call in client.load_calls)) == 2


def test_manifest_identity_is_stable_for_replay_and_distinguishes_snapshots(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    source_keys = ["symbol", "fiscal_year", "document_link"]
    first_manifest = {
        "source": "financial-report",
        "run_id": "snapshot-001",
        "payload_sha256": "a" * 64,
        "parser_manifest": {
            "parser_name": "financials",
            "parser_version": "1.0",
            "configuration_sha256": "b" * 64,
        },
    }
    replay_id = helper.upsert_into_bigquery(
        _rows(),
        "project",
        "stocks",
        "financials",
        source_keys,
        run_id="manifest-replay-one",
        snapshot_manifest=first_manifest,
    )
    repeated_id = helper.upsert_into_bigquery(
        _rows(),
        "project",
        "stocks",
        "financials",
        source_keys,
        run_id="manifest-replay-two",
        snapshot_manifest=first_manifest,
    )
    next_snapshot = dict(first_manifest, run_id="snapshot-002")
    next_id = helper.upsert_into_bigquery(
        _rows(),
        "project",
        "stocks",
        "financials",
        source_keys,
        run_id="manifest-next",
        snapshot_manifest=next_snapshot,
    )

    assert replay_id == repeated_id
    assert replay_id != next_id
    assert len(client.tables["project.stocks.financials"]) == 1

    reordered = pd.concat([_rows().iloc[[0]], _rows().iloc[[0]].assign(symbol="XYZ")])
    assert helper._load_identity(
        reordered,
        "project",
        "stocks",
        "financials",
        source_keys,
        first_manifest,
    ) == helper._load_identity(
        reordered.iloc[::-1],
        "project",
        "stocks",
        "financials",
        source_keys,
        first_manifest,
    )


def test_changed_row_is_revision_only_when_revision_identity_is_a_source_key(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    original = _rows().iloc[[0]].copy()
    corrected = original.copy()
    corrected["net_income"] = 125
    base_keys = ["symbol", "fiscal_year"]

    helper.upsert_into_bigquery(
        original, "project", "stocks", "financials", base_keys, run_id="current-one"
    )
    helper.upsert_into_bigquery(
        corrected, "project", "stocks", "financials", base_keys, run_id="current-two"
    )
    assert len(client.tables["project.stocks.financials"]) == 1
    assert client.tables["project.stocks.financials"][0]["net_income"] == 125

    client.tables["project.stocks.financials"].clear()
    revision_keys = ["symbol", "fiscal_year", "document_link"]
    helper.upsert_into_bigquery(
        original,
        "project",
        "stocks",
        "financials",
        revision_keys,
        run_id="revision-one",
    )
    corrected["document_link"] = "gs://archive/report-2.pdf"
    helper.upsert_into_bigquery(
        corrected,
        "project",
        "stocks",
        "financials",
        revision_keys,
        run_id="revision-two",
    )

    history = client.tables["project.stocks.financials"]
    assert len(history) == 2
    assert {row["net_income"] for row in history} == {100, 125}


def test_financial_revision_is_insert_only_and_requires_provisioned_schema(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    first = pd.DataFrame([{
        "symbol": "ABC",
        "fiscal_year": 2025,
        "document_link": "https://reports.example/annual.pdf",
        "net_income": 100,
        "document_revision": "a" * 64,
    }])
    same_revision_retry = first.assign(net_income=999)
    corrected = first.assign(net_income=125, document_revision="b" * 64)

    helper.upsert_financial_report_revision(first, "project")
    helper.upsert_financial_report_revision(same_revision_retry, "project")
    helper.upsert_financial_report_revision(corrected, "project")

    revisions = client.tables["project.stocks.financial_report_revisions"]
    assert len(revisions) == 2
    assert next(
        row for row in revisions if row["document_revision"] == "a" * 64
    )["net_income"] == 100
    revision_queries = [
        query
        for query in client.merge_queries
        if "financial_report_revisions`" in query
    ]
    assert all("WHEN MATCHED THEN UPDATE SET" not in query for query in revision_queries)
