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
        self.select_queries: list[str] = []
        self.deleted_tables: list[str] = []
        self.load_error: Exception | None = None
        self.merge_error: Exception | None = None

    def get_table(self, table_id: str) -> Any:
        raise AssertionError(f"runtime schema lookup is not allowed: {table_id}")

    def create_table(self, table: Any, *, exists_ok: bool) -> Any:
        raise AssertionError(f"runtime table creation is not allowed: {table}")

    def load_table_from_dataframe(
        self, dataframe: pd.DataFrame, table_id: str, *, job_config: Any
    ) -> _Job:
        self.load_calls.append((table_id, job_config))
        self.stages[table_id] = dataframe.to_dict(orient="records")
        return _Job(error=self.load_error)

    def query(self, sql: str, *, job_config: Any) -> _Job:
        if "SELECT *" in sql:
            self.select_queries.append(sql)
            parameters = {
                parameter.name: parameter.value
                for parameter in job_config.query_parameters
            }
            table_match = re.search(r"FROM `([^`]+)`", sql)
            assert table_match is not None
            rows = self.tables.get(table_match.group(1), [])
            match = next(
                (
                    row
                    for row in rows
                    if row.get("symbol") == parameters["symbol"]
                    and row.get("fiscal_year") == parameters["fiscal_year"]
                    and row.get("document_link") == parameters["document_link"]
                    and row.get("document_revision")
                    == parameters["document_revision"]
                ),
                None,
            )
            return _Job(result=[dict(match)] if match else [])
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
            elif "WHEN MATCHED THEN UPDATE SET" in sql:
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
        ScalarQueryParameter=lambda name, type_, value: SimpleNamespace(
            name=name, type=type_, value=value
        ),
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


class _FakePdfBlob:
    def __init__(self, payload: bytes) -> None:
        self.name = "financials/ABC/2025/annual.pdf"
        self.payload = payload
        self.downloads = 0

    def download_as_bytes(self) -> bytes:
        self.downloads += 1
        return self.payload


def _load_financial_processor(
    monkeypatch: pytest.MonkeyPatch,
    helper: ModuleType,
    blob: _FakePdfBlob,
) -> ModuleType:
    scripts = (
        Path(__file__).resolve().parents[3]
        / "archive"
        / "legacy-ingestion"
        / "scripts"
    )
    bucket = SimpleNamespace(list_blobs=lambda prefix: [blob])
    storage_client = SimpleNamespace(bucket=lambda name: bucket)
    storage = SimpleNamespace(Client=lambda credentials=None: storage_client)

    google = sys.modules["google"]
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")  # type: ignore[attr-defined]
    google_cloud = sys.modules["google.cloud"]
    google.auth = google_auth  # type: ignore[attr-defined]
    google_cloud.storage = storage  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", storage)

    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)
    monkeypatch.setitem(sys.modules, "helper", helper)
    monkeypatch.setattr(helper, "get_project_number", lambda project_id: "123")

    path = scripts / "insert_financials.py"
    specification = importlib.util.spec_from_file_location(
        "ingestion_insert_financials_loads", path
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    monkeypatch.setattr(module, "get_existing_data_in_bigquery", lambda project_id: set())
    return module


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


def test_process_financial_pdfs_commits_current_revision_then_archives(
    loader: tuple[ModuleType, _FakeBigQueryClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, client = loader
    blob = _FakePdfBlob(b"first annual report")
    processor = _load_financial_processor(monkeypatch, helper, blob)
    parsed = {
        "revenue": 500,
        "net_income": 100,
        "total_debt": 80,
        "cash_and_cash_equivalents": 40,
        "total_equity": 200,
    }
    archive_calls: list[str] = []
    monkeypatch.setattr(
        processor, "extract_financials_from_pdf", lambda content, api_key: parsed
    )

    def archive(blob_arg: Any, bucket: Any, project_number: str, **kwargs: Any) -> bool:
        archive_calls.append(kwargs["destination_blob_name"])
        return True

    monkeypatch.setattr(processor, "move_pdf_to_archive", archive)

    assert processor.process_financial_pdfs("test-key") == 1

    revision = processor.hashlib.sha256(blob.payload).hexdigest()
    assert archive_calls == [f"financial_report_revisions/ABC/2025/{revision}.pdf"]
    assert len(client.tables["project.stocks.financials"]) == 1
    assert len(client.tables["project.stocks.financial_report_revisions"]) == 1
    assert "MERGE `project.stocks.financials`" in client.merge_queries[0]
    assert "MERGE `project.stocks.financial_report_revisions`" in client.merge_queries[1]


def test_process_financial_pdfs_retries_archive_without_mutating_revision(
    loader: tuple[ModuleType, _FakeBigQueryClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, client = loader
    blob = _FakePdfBlob(b"retryable annual report")
    processor = _load_financial_processor(monkeypatch, helper, blob)
    parsed_results = iter(
        [
            {
                "revenue": 500,
                "net_income": 100,
                "total_debt": 80,
                "cash_and_cash_equivalents": 40,
                "total_equity": 200,
            },
            {
                "revenue": 500,
                "net_income": 999,
                "total_debt": 80,
                "cash_and_cash_equivalents": 40,
                "total_equity": 200,
            },
        ]
    )
    extraction_calls = 0

    def extract(content: bytes, api_key: str) -> dict[str, int]:
        nonlocal extraction_calls
        extraction_calls += 1
        return next(parsed_results)

    monkeypatch.setattr(
        processor,
        "extract_financials_from_pdf",
        extract,
    )
    archive_results = iter([False, True])
    archive_calls = 0

    def archive(blob_arg: Any, bucket: Any, project_number: str, **kwargs: Any) -> bool:
        nonlocal archive_calls
        archive_calls += 1
        return next(archive_results)

    monkeypatch.setattr(processor, "move_pdf_to_archive", archive)

    assert processor.process_financial_pdfs("test-key") == 0
    assert processor.process_financial_pdfs("test-key") == 1

    revisions = client.tables["project.stocks.financial_report_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["net_income"] == 100
    assert client.tables["project.stocks.financials"][0]["net_income"] == 100
    assert archive_calls == 2
    assert blob.downloads == 2
    assert extraction_calls == 1
    revision_queries = [
        query
        for query in client.merge_queries
        if "financial_report_revisions`" in query
    ]
    assert len(revision_queries) == 2
    assert all("WHEN MATCHED THEN UPDATE SET" not in query for query in revision_queries)


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
