"""Focused tests for retry-safe BigQuery loads without cloud access."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pandas as pd
import pytest


def _load_helper() -> ModuleType:
    helper_path = (
        Path(__file__).resolve().parents[3]
        / "archive"
        / "legacy-ingestion"
        / "scripts"
        / "helper.py"
    )
    specification = importlib.util.spec_from_file_location("ingestion_helper_loads", helper_path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


class _Job:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def result(self) -> Any:
        if self._error:
            raise self._error
        return self._result


class _FakeBigQueryClient:
    def __init__(self) -> None:
        self.stages: dict[str, list[dict[str, Any]]] = {}
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.load_calls: list[tuple[str, Any]] = []
        self.merge_queries: list[str] = []
        self.deleted_tables: list[str] = []
        self.load_error: Exception | None = None
        self.merge_error: Exception | None = None

    def get_table(self, table_id: str) -> Any:
        return SimpleNamespace(
            schema=[
                SimpleNamespace(name=name)
                for name in ("symbol", "fiscal_year", "document_link", "net_income")
            ]
        )

    def create_table(self, table: Any, *, exists_ok: bool) -> Any:
        self.created_table = table
        return table

    def load_table_from_dataframe(
        self, dataframe: pd.DataFrame, table_id: str, *, job_config: Any
    ) -> _Job:
        self.load_calls.append((table_id, job_config))
        self.stages[table_id] = dataframe.to_dict(orient="records")
        return _Job(error=self.load_error)

    def query(self, sql: str, *, job_config: Any) -> _Job:
        self.merge_queries.append(sql)
        staging_id = re.search(r"USING `([^`]+)`", sql)
        target_id = re.search(r"MERGE `([^`]+)`", sql)
        assert staging_id is not None and target_id is not None
        if self.merge_error:
            return _Job(error=self.merge_error)

        target_rows = self.tables.setdefault(target_id.group(1), [])
        on_clause = sql.split("WHEN", maxsplit=1)[0]
        keys = re.findall(r"target\.`([^`]+)` = source\.`[^`]+`", on_clause)
        for incoming in self.stages[staging_id.group(1)]:
            key = tuple(incoming[column] for column in keys)
            current = next(
                (
                    row
                    for row in target_rows
                    if tuple(row[column] for column in keys) == key
                ),
                None,
            )
            if current is None:
                target_rows.append(dict(incoming))
            else:
                current.update(incoming)
        return _Job()

    def delete_table(self, table_id: str, *, not_found_ok: bool) -> None:
        self.deleted_tables.append(table_id)
        self.stages.pop(table_id, None)


@pytest.fixture
def loader(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, _FakeBigQueryClient]:
    helper = _load_helper()
    client = _FakeBigQueryClient()
    bigquery = SimpleNamespace(
        Client=lambda project: client,
        SchemaField=lambda name, field_type: SimpleNamespace(name=name, type=field_type),
        Table=lambda table_id, schema: SimpleNamespace(table_id=table_id, schema=schema),
        LoadJobConfig=lambda **values: SimpleNamespace(**values),
        QueryJobConfig=lambda **values: SimpleNamespace(**values),
        WriteDisposition=SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE"),
    )
    google = ModuleType("google")
    google_cloud = ModuleType("google.cloud")
    google.cloud = google_cloud  # type: ignore[attr-defined]
    google_cloud.bigquery = bigquery  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", google_cloud)
    return helper, client


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "ABC",
                "fiscal_year": 2025,
                "document_link": "gs://archive/report-1.pdf",
                "net_income": 100,
            },
            {
                "symbol": "ABC",
                "fiscal_year": 2025,
                "document_link": "gs://archive/report-1.pdf",
                "net_income": 100,
            },
        ]
    )


def test_repeated_and_overlapping_runs_use_source_keys_and_isolated_staging(
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


def test_financial_revision_uses_document_content_identity_and_keeps_current_schema(
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
    corrected = first.assign(net_income=125, document_revision="b" * 64)

    helper.upsert_financial_report_revision(first, "project")
    helper.upsert_financial_report_revision(corrected, "project")

    revision_table = client.created_table
    assert revision_table.table_id == "project.stocks.financial_report_revisions"
    assert any(
        field.name == "document_revision" and field.type == "STRING"
        for field in revision_table.schema
    )
    assert len(client.tables["project.stocks.financial_report_revisions"]) == 2


def test_financial_pdf_caller_commits_revision_before_retryable_archive(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    current = pd.DataFrame([{
        "symbol": "ABC",
        "fiscal_year": 2025,
        "document_link": "gs://archive/annual.pdf",
        "net_income": 125,
    }])
    revision = current.assign(document_revision="c" * 64)
    archive_calls = 0

    def archive_once_fails() -> None:
        nonlocal archive_calls
        archive_calls += 1
        if archive_calls == 1:
            raise OSError("archive unavailable")

    with pytest.raises(OSError, match="archive unavailable"):
        helper.upsert_financial_report_and_archive(
            current, revision, "project", archive_once_fails, dataset="stocks"
        )

    assert len(client.merge_queries) == 2
    assert "MERGE `project.stocks.financials`" in client.merge_queries[0]
    assert "MERGE `project.stocks.financial_report_revisions`" in client.merge_queries[1]
    helper.upsert_financial_report_and_archive(
        current, revision, "project", archive_once_fails, dataset="stocks"
    )

    assert len(client.tables["project.stocks.financials"]) == 1
    assert len(client.tables["project.stocks.financial_report_revisions"]) == 1
    assert archive_calls == 2


@pytest.mark.parametrize("failure_stage", ["load", "merge"])
def test_failed_load_or_merge_never_archives_or_leaves_shared_staging(
    loader: tuple[ModuleType, _FakeBigQueryClient], failure_stage: str
) -> None:
    helper, client = loader
    failure = RuntimeError(f"{failure_stage} failed")
    if failure_stage == "load":
        client.load_error = failure
    else:
        client.merge_error = failure
    archived: list[bool] = []

    with pytest.raises(RuntimeError, match=f"{failure_stage} failed"):
        helper.upsert_and_archive(
            _rows().iloc[[0]],
            "project",
            "stocks",
            "financials",
            ["symbol", "fiscal_year", "document_link"],
            lambda: archived.append(True),
            run_id=f"failed-{failure_stage}",
        )

    assert archived == []
    assert client.deleted_tables == [
        f"project.stocks.financials__stage_failed-{failure_stage}"
    ]
