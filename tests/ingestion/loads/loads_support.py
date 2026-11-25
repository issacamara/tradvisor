"""Shared fakes and module loaders for the BigQuery load tests."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
import pandas as pd
import pytest


# The ingestion modules import siblings (e.g. ingestion_observability) by bare
# name. Append, never prepend: the directory holds a calendar.py that would
# otherwise shadow the standard library.
_INGESTION_DIRECTORY = str(Path(__file__).resolve().parents[3] / "functions" / "ingestion")
if _INGESTION_DIRECTORY not in sys.path:
    sys.path.append(_INGESTION_DIRECTORY)


def _load_helper() -> ModuleType:
    helper_path = (
        Path(__file__).resolve().parents[3]
        / "functions"
        / "ingestion"
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
        self.loaded_dataframes: list[pd.DataFrame] = []
        self.merge_queries: list[str] = []
        self.cleanup_queries: list[str] = []
        self.cleanup_run_ids: list[str] = []
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
        self.loaded_dataframes.append(dataframe.copy())
        rows = dataframe.to_dict(orient="records")
        if job_config.write_disposition == "WRITE_APPEND":
            self.stages.setdefault(table_id, []).extend(rows)
        else:
            self.stages[table_id] = rows
        return _Job(error=self.load_error)

    def query(self, sql: str, *, job_config: Any = None) -> _Job:
        parameters = {
            parameter.name: parameter.value
            for parameter in getattr(job_config, "query_parameters", [])
        }
        if sql.lstrip().startswith("DELETE FROM"):
            table_match = re.search(r"DELETE FROM `([^`]+)`", sql)
            assert table_match is not None
            self.cleanup_queries.append(sql)
            self.cleanup_run_ids.append(parameters["run_id"])
            table_id = table_match.group(1)
            self.stages[table_id] = [
                row
                for row in self.stages.get(table_id, [])
                if row.get("run_id") != parameters["run_id"]
            ]
            return _Job()
        if "FROM `project.stocks.financial_report_revisions`" in sql:
            self.select_queries.append(sql)
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
                    and (
                        "document_revision" not in parameters
                        or row.get("document_revision")
                        == parameters["document_revision"]
                    )
                ),
                None,
            )
            return _Job(result=[dict(match)] if match else [])
        if sql.lstrip().startswith("SELECT symbol, fiscal_year, document_link"):
            self.select_queries.append(sql)
            table_match = re.search(r"FROM `([^`]+)`", sql)
            assert table_match is not None
            rows = self.tables.get(table_match.group(1), [])
            return _Job(
                result=[
                    SimpleNamespace(
                        symbol=row["symbol"],
                        fiscal_year=row["fiscal_year"],
                        document_link=row.get("document_link"),
                    )
                    for row in rows
                ]
            )
        self.merge_queries.append(sql)
        staging_id = re.search(r"USING `([^`]+)`", sql) or re.search(
            r"FROM `([^`]+)`", sql
        )
        target_id = re.search(r"MERGE `([^`]+)`", sql)
        assert staging_id is not None and target_id is not None
        if self.merge_error:
            return _Job(error=self.merge_error)

        target_rows = self.tables.setdefault(target_id.group(1), [])
        on_clause = sql.split("WHEN", maxsplit=1)[0]
        keys = re.findall(r"target\.`([^`]+)` = source\.`[^`]+`", on_clause)
        source_rows = self.stages[staging_id.group(1)]
        if "@run_id" in sql:
            source_rows = [
                row for row in source_rows if row.get("run_id") == parameters["run_id"]
            ]
        for incoming in source_rows:
            incoming = {key: value for key, value in incoming.items() if key != "run_id"}
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
        Client=lambda **kwargs: client,
        SchemaField=lambda name, field_type: SimpleNamespace(name=name, type=field_type),
        Table=lambda table_id, schema: SimpleNamespace(table_id=table_id, schema=schema),
        LoadJobConfig=lambda **values: SimpleNamespace(**values),
        QueryJobConfig=lambda **values: SimpleNamespace(**values),
        ScalarQueryParameter=lambda name, type_, value: SimpleNamespace(
            name=name, type=type_, value=value
        ),
        WriteDisposition=SimpleNamespace(
            WRITE_APPEND="WRITE_APPEND", WRITE_TRUNCATE="WRITE_TRUNCATE"
        ),
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
        / "functions"
        / "financials"
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
