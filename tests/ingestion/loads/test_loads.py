"""Focused tests for retry-safe BigQuery loads without cloud access."""

from __future__ import annotations

import importlib.util
import hashlib
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


def _load_monthly_scraper(
    monkeypatch: pytest.MonkeyPatch,
    helper: ModuleType,
) -> ModuleType:
    requests = SimpleNamespace(
        Session=lambda: SimpleNamespace(
            get=lambda *args, **kwargs: SimpleNamespace(
                status_code=200, content=b"monthly annual report"
            ),
            close=lambda: None,
        )
    )
    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.requests = requests  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "curl_cffi", curl_cffi)
    yaml = ModuleType("yaml")
    yaml.safe_load = lambda value: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaml", yaml)
    bs4 = ModuleType("bs4")
    bs4.BeautifulSoup = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bs4", bs4)
    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)

    google = sys.modules["google"]
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("credentials", "project")  # type: ignore[attr-defined]
    google.auth = google_auth  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "helper", helper)

    scripts = Path(__file__).resolve().parents[3] / "functions" / "financials"
    path = scripts / "scrape_financials.py"
    specification = importlib.util.spec_from_file_location(
        "ingestion_monthly_scraper_loads", path
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_monthly_scraper_existing_lookup_uses_managed_financial_schema(
    loader: tuple[ModuleType, _FakeBigQueryClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, client = loader
    client.tables["project.stocks.financials"] = [{
        "symbol": "ABC",
        "fiscal_year": 2025,
        "document_link": "https://reports.example/annual.pdf",
    }]
    scraper = _load_monthly_scraper(monkeypatch, helper)

    existing = scraper.get_existing_symbols_and_years("project.stocks.financials")

    assert existing == {
        ("ABC", 2025): {"document_link": "https://reports.example/annual.pdf"}
    }
    assert "announcement_date" not in client.select_queries[-1]


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


def test_monthly_scrape_commit_order_keeps_current_and_revision_consistent(
    loader: tuple[ModuleType, _FakeBigQueryClient],
) -> None:
    helper, client = loader
    first = pd.DataFrame([{
        "symbol": "ABC",
        "fiscal_year": 2025,
        "document_link": "https://reports.example/annual.pdf",
        "document_revision": "a" * 64,
        "revenue": 500,
        "net_income": 100,
    }])
    client.merge_error = RuntimeError("current-table merge failed")
    with pytest.raises(RuntimeError, match="current-table merge failed"):
        helper.upsert_financial_report_current_and_revision(first, "project")

    assert "project.stocks.financial_report_revisions" not in client.tables
    client.merge_error = None
    retried = first.assign(document_revision="b" * 64, net_income=125)
    helper.upsert_financial_report_current_and_revision(retried, "project")

    assert client.tables["project.stocks.financials"][0]["net_income"] == 125
    assert client.tables["project.stocks.financial_report_revisions"][0]["net_income"] == 125
    assert client.merge_queries[0].startswith("\n        MERGE `project.stocks.financials`")
    assert client.merge_queries[1].startswith("\n        MERGE `project.stocks.financials`")
    assert client.merge_queries[2].startswith("\n        MERGE `project.stocks.financial_report_revisions`")


def test_monthly_scraper_recovers_current_load_failure_without_revision_mismatch(
    loader: tuple[ModuleType, _FakeBigQueryClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, client = loader
    scraper = _load_monthly_scraper(monkeypatch, helper)
    source_url = "https://reports.example/annual.pdf"
    announcement = {
        "fiscal_year": 2025,
        "announcement_date": "2026-04-01",
        "url": source_url,
    }
    monkeypatch.setattr(scraper, "table_exists", lambda name: True)
    monkeypatch.setattr(
        scraper,
        "get_existing_symbols_and_years",
        lambda: {("OTHER", 2024): {"document_link": "https://reports.example/other.pdf"}},
    )
    monkeypatch.setattr(scraper, "get_symbols_from_company_reference", lambda project_id: ["ABC"])
    monkeypatch.setattr(
        scraper, "get_announcements_for_symbol", lambda symbol: [announcement]
    )
    parsed_results = iter(
        [
            {"revenue": 500, "net_income": 100, "total_debt": 80,
             "cash_and_cash_equivalents": 40, "total_equity": 200},
            {"revenue": 500, "net_income": 125, "total_debt": 80,
             "cash_and_cash_equivalents": 40, "total_equity": 200},
        ]
    )
    monkeypatch.setattr(
        scraper,
        "extract_financials_from_pdf",
        lambda content, api_key: next(parsed_results),
    )

    client.merge_error = RuntimeError("current-table merge failed")
    with pytest.raises(RuntimeError, match="current-table merge failed"):
        scraper.scrape_financials("https://reports.example", "test-key")
    assert "project.stocks.financial_report_revisions" not in client.tables

    client.merge_error = None
    scraper.scrape_financials("https://reports.example", "test-key")

    current = client.tables["project.stocks.financials"][0]
    revision = client.tables["project.stocks.financial_report_revisions"][0]
    assert current["net_income"] == revision["net_income"] == 125


def test_monthly_scraper_detects_replaced_pdf_at_same_url_and_date(
    loader: tuple[ModuleType, _FakeBigQueryClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, client = loader
    scraper = _load_monthly_scraper(monkeypatch, helper)
    source_url = "https://reports.example/annual.pdf"
    report_bytes = b"monthly annual report"
    previous_hash = hashlib.sha256(b"previous PDF bytes").hexdigest()
    client.tables["project.stocks.financials"] = [{
        "symbol": "ABC",
        "fiscal_year": 2025,
        "document_link": source_url,
        "net_income": 100,
    }]
    client.tables["project.stocks.financial_report_revisions"] = [{
        "symbol": "ABC",
        "fiscal_year": 2025,
        "document_link": source_url,
        "document_revision": previous_hash,
        "net_income": 100,
    }]
    announcement = {
        "fiscal_year": 2025,
        "announcement_date": "2026-04-01",
        "url": source_url,
    }
    monkeypatch.setattr(scraper, "table_exists", lambda name: True)
    monkeypatch.setattr(
        scraper,
        "get_existing_symbols_and_years",
        lambda: {("ABC", 2025): {
            "document_link": source_url
        }},
    )
    monkeypatch.setattr(scraper, "get_symbols_from_company_reference", lambda project_id: ["ABC"])
    monkeypatch.setattr(
        scraper, "get_announcements_for_symbol", lambda symbol: [announcement]
    )
    monkeypatch.setattr(
        scraper,
        "extract_financials_from_pdf",
        lambda content, api_key: {
            "revenue": 500,
            "net_income": 125,
            "total_debt": 80,
            "cash_and_cash_equivalents": 40,
            "total_equity": 200,
        },
    )

    scraper.scrape_financials("https://reports.example", "test-key")

    current = client.tables["project.stocks.financials"][0]
    revisions = client.tables["project.stocks.financial_report_revisions"]
    assert current["net_income"] == 125
    assert len(revisions) == 2
    assert {row["document_revision"] for row in revisions} == {
        previous_hash,
        hashlib.sha256(report_bytes).hexdigest(),
    }


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
    monkeypatch.setattr(processor, "annual_financial_revision_row", lambda *a, **k: {"fixture": True})
    monkeypatch.setattr(processor, "persist_annual_financial_revision", lambda *a, **k: None)
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
    monkeypatch.setattr(processor, "annual_financial_revision_row", lambda *a, **k: {"fixture": True})
    monkeypatch.setattr(processor, "persist_annual_financial_revision", lambda *a, **k: None)
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


class _SourceBlob:
    def __init__(self, name: str, content: str) -> None:
        self.name = name
        self._content = content

    def download_as_text(self) -> str:
        return self._content


def _install_cloud_runtime(
    monkeypatch: pytest.MonkeyPatch, blobs: list[_SourceBlob]
) -> None:
    monkeypatch.setenv("TRADVISOR_RUNTIME_TARGET", "ingestion")
    monkeypatch.setenv("TRADVISOR_ENVIRONMENT", "development")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "fixture-project")
    monkeypatch.setenv("TRADVISOR_TARGET_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("TRADVISOR_ENVIRONMENT_PROJECT_ID", "fixture-project")
    monkeypatch.setenv(
        "TRADVISOR_INGESTION_SERVICE_ACCOUNT",
        "fixture-ingestion@fixture-project.iam.gserviceaccount.com",
    )
    monkeypatch.setenv("TRADVISOR_INGESTION_DATA_BUCKET", "fixture-data-bucket")
    monkeypatch.setenv("TRADVISOR_INGESTION_ARCHIVE_BUCKET", "fixture-archive-bucket")
    monkeypatch.setenv("TRADVISOR_INGESTION_DATASET", "stocks")
    for asset in ("SHARES", "DIVIDENDS", "FINANCIALS", "RATINGS"):
        monkeypatch.setenv(
            f"TRADVISOR_INGESTION_{asset}_TABLE",
            f"fixture-project.stocks.{asset.lower()}",
        )
    bucket = SimpleNamespace(list_blobs=lambda prefix: blobs)
    storage = ModuleType("google.cloud.storage")
    storage.Client = lambda **kwargs: SimpleNamespace(bucket=lambda name: bucket)  # type: ignore[attr-defined]
    auth = ModuleType("google.auth")
    auth.default = lambda: ("fixture-credentials", "fixture-project")  # type: ignore[attr-defined]
    cloud = ModuleType("google.cloud")
    cloud.storage = storage  # type: ignore[attr-defined]
    google = ModuleType("google")
    google.auth = auth  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", storage)


def _load_cloud_consumer(
    monkeypatch: pytest.MonkeyPatch, path: Path, helper: ModuleType, name: str
) -> ModuleType:
    configuration_path = (
        Path(__file__).resolve().parents[3]
        / "archive"
        / "legacy-ingestion"
        / "scripts"
        / "ingestion_configuration.py"
    )
    configuration_specification = importlib.util.spec_from_file_location(
        "ingestion_configuration", configuration_path
    )
    assert (
        configuration_specification is not None
        and configuration_specification.loader is not None
    )
    configuration = importlib.util.module_from_spec(
        configuration_specification
    )
    monkeypatch.setitem(sys.modules, "ingestion_configuration", configuration)
    configuration_specification.loader.exec_module(configuration)

    framework = ModuleType("functions_framework")
    framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", framework)
    monkeypatch.setitem(sys.modules, "helper", helper)
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def test_dividend_entrypoint_retries_gcs_source_without_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blob = _SourceBlob("dividends-2026-10-14.csv", "payment_id|symbol\npayment-1|ABC\n")
    _install_cloud_runtime(monkeypatch, [blob])
    canonical: dict[str, dict[str, object]] = {}
    calls: list[str] = []
    archive_attempts = 0
    helper = ModuleType("helper")
    helper.get_project_number = lambda project_id: "123"  # type: ignore[attr-defined]

    def archive(source_bucket: str, archive_bucket: str, blob_name: str) -> None:
        nonlocal archive_attempts
        assert (source_bucket, archive_bucket, blob_name) == (
            "fixture-data-bucket",
            "fixture-archive-bucket",
            blob.name,
        )
        archive_attempts += 1
        calls.append("archive")
        if archive_attempts == 1:
            raise OSError("archive unavailable")

    def upsert_and_archive(frame, _project, _dataset, _table, keys, archive_callback) -> None:
        assert keys == ["payment_id"]
        for row in frame.to_dict("records"):
            canonical[row["payment_id"]] = row
        calls.append("upsert")
        archive_callback()

    helper.move_csv_file_gcp = archive  # type: ignore[attr-defined]
    helper.upsert_and_archive = upsert_and_archive  # type: ignore[attr-defined]
    module = _load_cloud_consumer(
        monkeypatch,
        Path(__file__).resolve().parents[3] / "functions" / "dividends" / "insert_dividends.py",
        helper,
        "cloud_only_dividends",
    )

    with pytest.raises(OSError, match="archive unavailable"):
        module.entry_point()
    assert canonical == {"payment-1": {"payment_id": "payment-1", "symbol": "ABC"}}
    assert calls == ["upsert", "archive"]

    assert module.entry_point() == "Data upsert successfully completed !\n"
    assert calls == ["upsert", "archive", "upsert", "archive"]
    assert len(canonical) == 1


def test_rating_entrypoint_preserves_revision_identity_across_gcs_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blob = _SourceBlob(
        "ratings-2026-10-14.csv", "symbol|source_revision_id\nABC|revision-1\n"
    )
    _install_cloud_runtime(monkeypatch, [blob])
    canonical: set[tuple[str, str]] = set()
    calls: list[str] = []
    archive_attempts = 0
    helper = ModuleType("helper")
    helper.get_project_number = lambda project_id: "123"  # type: ignore[attr-defined]
    helper.load_files = lambda _config, asset: [blob] if asset == "ratings" else []  # type: ignore[attr-defined]

    def upsert(frame, _project, _dataset, _table, keys, *, update_matched):
        assert keys == ["symbol", "source_revision_id"]
        assert update_matched is False
        canonical.update((row["symbol"], row["source_revision_id"]) for row in frame.to_dict("records"))
        calls.append("upsert")

    def archive(source_bucket: str, archive_bucket: str, blob_name: str) -> None:
        nonlocal archive_attempts
        assert (source_bucket, archive_bucket, blob_name) == (
            "fixture-data-bucket",
            "fixture-archive-bucket",
            blob.name,
        )
        archive_attempts += 1
        calls.append("archive")
        if archive_attempts == 1:
            raise OSError("archive unavailable")

    helper.upsert_into_bigquery = upsert  # type: ignore[attr-defined]
    helper.move_csv_file_gcp = archive  # type: ignore[attr-defined]
    module = _load_cloud_consumer(
        monkeypatch,
        Path(__file__).resolve().parents[3] / "functions" / "ratings" / "insert_ratings.py",
        helper,
        "cloud_only_ratings",
    )

    with pytest.raises(OSError, match="archive unavailable"):
        module.entry_point()
    assert canonical == {("ABC", "revision-1")}
    assert calls == ["upsert", "archive"]

    assert module.entry_point() == "Data insertion successfully completed !\n"
    assert calls == ["upsert", "archive", "upsert", "archive"]
    assert len(canonical) == 1


def test_shared_loader_rejects_missing_cloud_project_without_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _load_helper()
    _install_cloud_runtime(monkeypatch, [])
    sys.modules["google.auth"].default = lambda: ("fixture-credentials", None)  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="application-default project"):
        helper.load_files({"csv_directory": "local-data"}, "ratings")
