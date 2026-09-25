"""Fixture-only tests for the shared financial PDF extraction path."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "archive" / "legacy-ingestion" / "scripts"


class _Blob:
    def __init__(self) -> None:
        self.payload: str | None = None

    def exists(self) -> bool:
        return self.payload is not None

    def download_as_text(self) -> str:
        assert self.payload is not None
        return self.payload

    def upload_from_string(self, payload: str, **kwargs: object) -> None:
        self.payload = payload


class _Bucket:
    def __init__(self) -> None:
        self.blobs: dict[str, _Blob] = {}

    def blob(self, name: str) -> _Blob:
        return self.blobs.setdefault(name, _Blob())

    def list_blobs(self, prefix: str) -> list[_Blob]:
        return [blob for name, blob in self.blobs.items() if name.startswith(prefix)]


class _MemoryBlob(_Blob):
    def __init__(self, bucket: "_MemoryBucket", name: str) -> None:
        super().__init__()
        self.bucket = bucket
        self.name = name

    def upload_from_string(self, payload: str | bytes, **kwargs: object) -> None:
        self.payload = payload.decode() if isinstance(payload, bytes) else payload

    def download_as_bytes(self) -> bytes:
        assert self.payload is not None
        return self.payload.encode()

    def delete(self) -> None:
        self.bucket.blobs.pop(self.name, None)


class _MemoryBucket(_Bucket):
    def __init__(self, client: "_MemoryStorageClient", name: str) -> None:
        super().__init__()
        self.client = client
        self.name = name

    def blob(self, name: str) -> _MemoryBlob:
        return self.blobs.setdefault(name, _MemoryBlob(self, name))  # type: ignore[return-value]

    def copy_blob(
        self,
        source_blob: _MemoryBlob,
        destination_bucket: "_MemoryBucket",
        destination_name: str,
    ) -> _MemoryBlob:
        destination = destination_bucket.blob(destination_name)
        destination.payload = source_blob.payload
        return destination


class _MemoryStorageClient:
    def __init__(self) -> None:
        self.buckets: dict[str, _MemoryBucket] = {}

    def bucket(self, name: str) -> _MemoryBucket:
        return self.buckets.setdefault(name, _MemoryBucket(self, name))


class _BigQueryJob:
    def __init__(self, result: object = None) -> None:
        self.value = result

    def result(self) -> object:
        return self.value


class _MemoryBigQueryClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, object]]] = {}
        self.staging: dict[str, list[dict[str, object]]] = {}

    def load_table_from_dataframe(self, dataframe, table_id, *, job_config):
        self.staging[table_id] = dataframe.to_dict(orient="records")
        return _BigQueryJob()

    def query(self, sql: str, *, job_config=None):
        if sql.lstrip().startswith("SELECT"):
            if "financial_report_revisions" not in sql:
                table_id = sql.split("FROM `", 1)[1].split("`", 1)[0]
                rows = self.tables.get(table_id, [])
                return _BigQueryJob([SimpleNamespace(**row) for row in rows])
            parameters = {
                item.name: item.value for item in job_config.query_parameters
            }
            rows = self.tables.get("fixture-project.stocks.financial_report_revisions", [])
            matching = [
                row for row in rows
                if all(row.get(key) == value for key, value in parameters.items())
            ]
            return _BigQueryJob(matching[:1])

        target = sql.split("MERGE `", 1)[1].split("`", 1)[0]
        staging = sql.split("USING `", 1)[1].split("`", 1)[0]
        key_clause = sql.split("ON ", 1)[1].split("WHEN", 1)[0]
        import re

        keys = re.findall(r"target\.`([^`]+)` = source\.`([^`]+)`", key_clause)
        key_columns = [(left, right) for left, right in keys]
        destination_rows = self.tables.setdefault(target, [])
        for incoming in self.staging[staging]:
            existing = next(
                (
                    row for row in destination_rows
                    if all(row.get(left) == incoming.get(right) for left, right in key_columns)
                ),
                None,
            )
            if existing is None:
                destination_rows.append(dict(incoming))
            elif "WHEN MATCHED THEN UPDATE SET" in sql:
                existing.update(incoming)
        return _BigQueryJob()

    def delete_table(self, table_id: str, *, not_found_ok: bool) -> None:
        self.staging.pop(table_id, None)


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def adapter_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)
    yaml = ModuleType("yaml")
    yaml.safe_load = lambda stream: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaml", yaml)

    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("fixture-credentials", "fixture-project")  # type: ignore[attr-defined]
    cloud = ModuleType("google.cloud")
    storage = SimpleNamespace(Client=lambda **kwargs: None)
    bigquery = SimpleNamespace(Client=lambda **kwargs: None)
    cloud.storage = storage  # type: ignore[attr-defined]
    cloud.bigquery = bigquery  # type: ignore[attr-defined]
    google.auth = google_auth  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)

    helper = ModuleType("helper")
    for name in (
        "get_financial_report_revision",
        "upsert_financial_report_and_archive",
        "upsert_into_bigquery",
        "get_project_number",
    ):
        setattr(helper, name, lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "helper", helper)

    return _load_module(SCRIPTS / "insert_financials.py", "financial_pipeline_adapter")


def test_recorded_provider_response_replays_only_for_matching_pdf(
    adapter_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = b"fixture PDF bytes"
    digest = hashlib.sha256(pdf).hexdigest()
    result = {
        "revenue": 500,
        "net_income": 100,
        "total_debt": 80,
        "cash_and_cash_equivalents": 40,
        "total_equity": 200,
    }
    artifact = {
        "pdf_sha256": digest,
        "model": "fixture/model-v1",
        "prompt": "fixture extraction prompt",
        "response": {"choices": [{"message": {"content": "recorded"}}]},
        "result": result,
    }

    def forbidden_provider(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay must not call a provider")

    monkeypatch.setitem(
        sys.modules,
        "curl_cffi",
        SimpleNamespace(requests=SimpleNamespace(post=forbidden_provider)),
    )
    evidence: list[dict[str, object]] = []

    assert adapter_module.extract_financials_from_pdf(
        pdf, recorded_response=artifact, evidence_callback=evidence.append
    ) == result
    assert evidence == [artifact]
    with pytest.raises(ValueError, match="does not match the PDF hash"):
        adapter_module.extract_financials_from_pdf(
            b"different PDF", recorded_response=artifact
        )


def test_saved_artifact_is_keyed_by_pdf_hash_and_replays_without_reextraction(
    adapter_module: ModuleType,
) -> None:
    bucket = _Bucket()
    pdf = b"accepted fixture PDF"
    digest = hashlib.sha256(pdf).hexdigest()
    evidence = {
        "model": "fixture/model-v1",
        "prompt": "fixture prompt",
        "response": {"id": "fixture-response"},
        "result": {
            "revenue": 10,
            "net_income": 2,
            "total_debt": 4,
            "cash_and_cash_equivalents": 3,
            "total_equity": 8,
        },
    }

    adapter_module.save_extraction_artifact(bucket, digest, evidence)
    stored = adapter_module.load_extraction_artifact(bucket, digest)

    assert stored["pdf_sha256"] == digest
    assert stored["model"] == evidence["model"]
    assert stored["prompt"] == evidence["prompt"]
    assert stored["response"] == evidence["response"]
    assert adapter_module.extract_financials_from_pdf(
        pdf, recorded_response=stored
    ) == evidence["result"]
    assert len(bucket.blobs) == 1
    assert json.loads(next(iter(bucket.blobs.values())).payload or "{}") == stored


def test_mocked_provider_response_captures_model_prompt_and_response(
    adapter_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = b"fixture PDF bytes"
    extracted = {
        "revenue": 500,
        "net_income": 100,
        "total_debt": 80,
        "cash_and_cash_equivalents": 40,
        "total_equity": 200,
    }
    provider_response = {
        "model": "fixture/model-v1",
        "choices": [{"message": {"content": json.dumps(extracted)}}],
    }
    calls: list[dict[str, object]] = []

    class _Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return provider_response

    requests = SimpleNamespace(
        post=lambda url, **kwargs: calls.append(kwargs) or _Response()
    )
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=requests))
    monkeypatch.setattr(
        adapter_module,
        "extract_text_from_pdf",
        lambda content: "fixture report text " * 10,
    )
    evidence: list[dict[str, object]] = []

    assert adapter_module.extract_financials_from_pdf(
        pdf, "fixture-key", evidence_callback=evidence.append
    ) == extracted
    assert len(calls) == 1
    assert evidence[0]["model"] == "fixture/model-v1"
    assert "Extract structured financial data" in evidence[0]["prompt"]
    assert evidence[0]["response"] == provider_response
    assert evidence[0]["result"] == extracted


def test_provider_attempt_budget_is_shared_and_bounded(
    adapter_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class _Failure:
        status_code = 503
        text = "fixture failure"

    requests = SimpleNamespace(post=lambda *args, **kwargs: calls.append(args) or _Failure())
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=requests))
    attempt_budget = [0]

    adapter_module.send_openrouter_payload(
        [{"type": "text", "text": "fixture"}],
        "fixture-key",
        attempt_budget=attempt_budget,
        max_provider_attempts=1,
    )

    assert attempt_budget == [1]
    assert len(calls) == 1


def test_incomplete_extraction_is_not_accepted_and_remains_retryable(
    adapter_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = b"fixture incomplete then complete PDF"
    digest = hashlib.sha256(pdf).hexdigest()
    bucket = _Bucket()
    incomplete = {
        "fiscal_year": 2025,
        "revenue": 500,
        "net_income": 100,
        "total_debt": None,
        "cash_and_cash_equivalents": 40,
        "total_equity": 200,
    }
    complete = dict(incomplete, total_debt=80)
    provider_results = [incomplete] * 4 + [complete]
    provider_calls: list[dict[str, object]] = []

    class _Response:
        status_code = 200

        def __init__(self, result: dict[str, object]) -> None:
            self.result = result

        def json(self) -> dict[str, object]:
            return {
                "model": "fixture/model-v1",
                "choices": [{"message": {"content": json.dumps(self.result)}}],
            }

    def post(url: str, **kwargs: object) -> _Response:
        result = provider_results[len(provider_calls)]
        provider_calls.append(kwargs)
        return _Response(result)

    monkeypatch.setitem(
        sys.modules,
        "curl_cffi",
        SimpleNamespace(requests=SimpleNamespace(post=post)),
    )
    monkeypatch.setattr(
        adapter_module,
        "extract_text_from_pdf",
        lambda content: "fixture report text " * 10,
    )
    monkeypatch.setattr(
        adapter_module,
        "extract_relevant_pdf_pages",
        lambda content, max_pages: content,
    )

    incomplete_evidence: list[dict[str, object]] = []
    assert adapter_module.extract_financials_from_pdf(
        pdf,
        "fixture-key",
        evidence_callback=incomplete_evidence.append,
    ) is None
    assert len(provider_calls) == 4
    with pytest.raises(ValueError, match="not a complete accepted extraction"):
        adapter_module.save_extraction_artifact(
            bucket, digest, incomplete_evidence[-1]
        )
    assert not bucket.blob(adapter_module.extraction_artifact_name(digest)).exists()

    stale_artifact = dict(incomplete_evidence[-1], pdf_sha256=digest)
    bucket.blob(adapter_module.extraction_artifact_name(digest)).upload_from_string(
        json.dumps(stale_artifact)
    )
    assert adapter_module.load_extraction_artifact(bucket, digest) is None

    accepted_evidence: list[dict[str, object]] = []
    assert adapter_module.extract_financials_from_pdf(
        pdf,
        "fixture-key",
        recorded_response=adapter_module.load_extraction_artifact(bucket, digest),
        evidence_callback=accepted_evidence.append,
    ) == complete
    assert len(provider_calls) == 5
    adapter_module.save_extraction_artifact(bucket, digest, accepted_evidence[-1])
    accepted = adapter_module.load_extraction_artifact(bucket, digest)
    assert adapter_module.extract_financials_from_pdf(
        pdf, recorded_response=accepted
    ) == complete
    assert len(provider_calls) == 5


def test_monthly_incremental_retry_reuses_canonical_pdf_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)
    monkeypatch.setitem(sys.modules, "yaml", SimpleNamespace(safe_load=lambda stream: {}))
    monkeypatch.setitem(sys.modules, "bs4", SimpleNamespace(BeautifulSoup=lambda *a, **k: None))

    pdf = b"fixture monthly annual report PDF bytes"
    storage_client = _MemoryStorageClient()
    bigquery_client = _MemoryBigQueryClient()

    class _BigQuery:
        Client = lambda self, **kwargs: bigquery_client
        LoadJobConfig = lambda self, **kwargs: SimpleNamespace(**kwargs)
        QueryJobConfig = lambda self, **kwargs: SimpleNamespace(**kwargs)
        WriteDisposition = SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE")
        ScalarQueryParameter = lambda self, name, kind, value: SimpleNamespace(
            name=name, type=kind, value=value
        )

    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("fixture-credentials", "fixture-project")  # type: ignore[attr-defined]
    cloud = ModuleType("google.cloud")
    cloud.storage = SimpleNamespace(Client=lambda **kwargs: storage_client)  # type: ignore[attr-defined]
    cloud.bigquery = _BigQuery()  # type: ignore[attr-defined]
    google = ModuleType("google")
    google.auth = google_auth  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)

    fiscal_year = datetime.now().year
    result = {
        "fiscal_year": fiscal_year,
        "financial_category": "bank",
        "revenue": 500,
        "pnb": 500,
        "net_income": 100,
        "total_debt": 80,
        "cash_and_cash_equivalents": 40,
        "total_equity": 200,
        "annual_report": {
            "period": {
                "fiscal_year": fiscal_year,
                "start": f"{fiscal_year - 1}-07-01",
                "end": f"{fiscal_year}-06-30",
                "full_year": True,
            },
            "publication": {
                "published_at": f"{fiscal_year}-07-15T12:00:00Z",
                "evidenced": True,
            },
            "currency": "XOF",
            "report_scope": "consolidated",
            "accounting_basis": "SYSCOHADA",
            "financial_category": "bank",
            "revenue": {
                "value": "500",
                "currency": "XOF",
                "unit": "million XOF",
                "scale_to_xof": "1000000",
                "evidenced": True,
            },
            "ordinary_owner_earnings": {
                "value": "-2.5",
                "currency": "XOF",
                "unit": "million XOF",
                "scale_to_xof": "1000000",
                "evidenced": True,
            },
            "earnings_basis": "ordinary_owner",
            "earnings_scope": "consolidated",
            "equity": {
                "value": "20",
                "currency": "XOF",
                "unit": "million XOF",
                "scale_to_xof": "1000000",
                "evidenced": True,
            },
            "equity_basis": "ordinary_owner",
            "equity_scope": "consolidated",
        },
    }
    provider_calls: list[dict[str, object]] = []

    class _ProviderResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "model": "fixture/model-v1",
                "choices": [{"message": {"content": json.dumps(result)}}],
            }

    class _DownloadResponse:
        status_code = 200
        content = pdf

    class _Session:
        def get(self, *args: object, **kwargs: object) -> _DownloadResponse:
            return _DownloadResponse()

        def close(self) -> None:
            return None

    requests = SimpleNamespace(
        Session=lambda: _Session(),
        post=lambda url, **kwargs: provider_calls.append(kwargs) or _ProviderResponse(),
    )
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=requests))

    helper = _load_module(SCRIPTS / "helper.py", "helper")
    monkeypatch.setattr(helper, "get_project_number", lambda project_id: "123")
    insert = _load_module(SCRIPTS / "insert_financials.py", "insert_financials")
    canonical_rows: list[dict[str, object]] = []
    monkeypatch.setattr(
        insert,
        "persist_annual_financial_revision",
        lambda rows, project_id: canonical_rows.extend(
            rows if isinstance(rows, list) else [rows]
        ),
    )
    monkeypatch.setattr(
        insert,
        "extract_text_from_pdf",
        lambda content: "fixture report text " * 10,
    )
    scraper = _load_module(SCRIPTS / "scrape_financials.py", "financial_pipeline_monthly")
    announcement = {
        "symbol": "ABC",
        "title": "Fixture annual report",
        "announcement_date": f"{fiscal_year}-06-30",
        "fiscal_year": fiscal_year,
        "url": "https://fixture.invalid/annual.pdf",
    }
    monkeypatch.setattr(scraper, "table_exists", lambda name: True)
    monkeypatch.setattr(scraper, "get_symbols_from_richbourse", lambda url: ["ABC"])
    monkeypatch.setattr(
        scraper,
        "get_announcements_for_symbol",
        lambda symbol: [announcement],
    )

    current_table = "fixture-project.stocks.financials"
    revision_table = "fixture-project.stocks.financial_report_revisions"
    bigquery_client.tables[current_table] = [{
        "symbol": "XYZ",
        "fiscal_year": fiscal_year,
        "announcement_date": f"{fiscal_year}-01-01",
        "document_link": "https://fixture.invalid/existing.pdf",
    }]

    scraper.scrape_financials("fixture://source", "fixture-key")
    scraper.scrape_financials("fixture://source", "fixture-key")

    assert len(provider_calls) == 1
    current = [
        row for row in bigquery_client.tables[current_table]
        if row["symbol"] == "ABC"
    ]
    revisions = bigquery_client.tables[revision_table]
    digest = hashlib.sha256(pdf).hexdigest()
    assert len(current) == 1
    assert current[0]["revenue"] is None
    assert current[0]["net_income"] == result["net_income"]
    assert current[0]["total_debt"] == result["total_debt"]
    assert current[0]["fiscal_year"] == fiscal_year
    assert len(canonical_rows) == 2
    assert {row["revision_id"] for row in canonical_rows} == {
        canonical_rows[0]["revision_id"]
    }
    canonical = canonical_rows[0]
    assert canonical["revenue"] is None
    assert canonical["ordinary_owner_earnings"] == -2_500_000
    assert canonical["equity"] == 20_000_000
    assert canonical["report_scope"] == "consolidated"
    assert canonical["publication_status"] == "published"
    assert canonical["source_published_at"] == f"{fiscal_year}-07-15 12:00:00"
    datetime.strptime(canonical["collected_at"], "%Y-%m-%d %H:%M:%S")
    assert len(revisions) == 1
    assert revisions[0]["document_revision"] == digest
    assert revisions[0]["document_link"] == announcement["url"]
    artifact = json.loads(
        storage_client.bucket("data-123").blobs[
            f"financial_extraction_artifacts/{digest}.json"
        ].payload or "{}"
    )
    assert artifact["result"] == result


def test_empty_table_hands_initialization_through_canonical_pdf_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)
    monkeypatch.setitem(sys.modules, "yaml", SimpleNamespace(safe_load=lambda stream: {}))
    monkeypatch.setitem(sys.modules, "bs4", SimpleNamespace(BeautifulSoup=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=SimpleNamespace()))
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("fixture-credentials", "fixture-project")  # type: ignore[attr-defined]
    google = ModuleType("google")
    google.auth = google_auth  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    helper = ModuleType("helper")
    helper.get_financial_report_revision = lambda *a, **k: None  # type: ignore[attr-defined]
    helper.get_symbols_from_richbourse = lambda *a, **k: []  # type: ignore[attr-defined]
    helper.save_dataframe_as_csv = lambda *a, **k: None  # type: ignore[attr-defined]
    helper.table_exists = lambda name: False  # type: ignore[attr-defined]
    helper.upsert_financial_report_current_and_revision = lambda *a, **k: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "helper", helper)

    calls: list[tuple[str | None, str | None]] = []
    init = ModuleType("scrape_financials_init")
    init.scrape_financials_init = lambda url, key: calls.append((url, key)) or 1  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scrape_financials_init", init)
    scraper = _load_module(SCRIPTS / "scrape_financials.py", "financial_pipeline_monthly")

    assert scraper.scrape_financials("fixture://source", "fixture-key") == 1
    assert calls == [("fixture://source", "fixture-key")]


def test_initialization_loads_fixture_pdf_into_canonical_current_and_revision_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)
    monkeypatch.setitem(sys.modules, "yaml", SimpleNamespace(safe_load=lambda stream: {}))
    monkeypatch.setitem(sys.modules, "bs4", SimpleNamespace(BeautifulSoup=lambda *a, **k: None))

    pdf = b"fixture annual report PDF bytes"
    storage_client = _MemoryStorageClient()
    bigquery_client = _MemoryBigQueryClient()

    class _BigQuery:
        Client = lambda self, **kwargs: bigquery_client
        LoadJobConfig = lambda self, **kwargs: SimpleNamespace(**kwargs)
        QueryJobConfig = lambda self, **kwargs: SimpleNamespace(**kwargs)
        WriteDisposition = SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE")
        ScalarQueryParameter = lambda self, name, kind, value: SimpleNamespace(
            name=name, type=kind, value=value
        )

    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: ("fixture-credentials", "fixture-project")  # type: ignore[attr-defined]
    cloud = ModuleType("google.cloud")
    cloud.storage = SimpleNamespace(Client=lambda **kwargs: storage_client)  # type: ignore[attr-defined]
    cloud.bigquery = _BigQuery()  # type: ignore[attr-defined]
    google = ModuleType("google")
    google.auth = google_auth  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)

    class _DownloadResponse:
        status_code = 200
        content = pdf

    requests = SimpleNamespace(Session=lambda: SimpleNamespace(get=lambda *a, **k: _DownloadResponse()))
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=requests))

    helper = _load_module(SCRIPTS / "helper.py", "helper")
    monkeypatch.setattr(helper, "get_project_number", lambda project_id: "123")
    company_reference = ModuleType("company_reference")
    company_reference.build_company_records = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    company_reference.read_mapping = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "company_reference", company_reference)
    insert = _load_module(SCRIPTS / "insert_financials.py", "insert_financials")
    monkeypatch.setattr(insert, "get_existing_data_in_bigquery", lambda project_id: set())
    result = {
        "fiscal_year": 2025,
        "revenue": 500,
        "net_income": 100,
        "total_debt": 80,
        "cash_and_cash_equivalents": 40,
        "total_equity": 200,
    }
    extraction_calls: list[bytes] = []

    def extract_fixture(content, api_key=None, *, evidence_callback=None, **kwargs):
        extraction_calls.append(content)
        if evidence_callback:
            evidence_callback({
                "model": "fixture/model-v1",
                "prompt": "fixture prompt",
                "response": {"id": "fixture-response"},
                "result": result,
            })
        return result

    monkeypatch.setattr(insert, "extract_financials_from_pdf", extract_fixture)
    init = _load_module(SCRIPTS / "scrape_financials_init.py", "scrape_financials_init")
    monkeypatch.setattr(
        init,
        "discover_company_references",
        lambda path: [SimpleNamespace(source_slug="fixture-company", symbol="ABC", name="Fixture Co")],
    )
    monkeypatch.setattr(
        init,
        "get_financial_reports_for_company",
        lambda slug, max_year: [{
            "title": "Fixture annual report",
            "fiscal_year": 2025,
            "pdf_url": "https://fixture.invalid/annual.pdf",
        }],
    )
    monkeypatch.setattr(init, "get_bucket_name", lambda: "data-123")

    assert init.scrape_financials_init("fixture://source", "fixture-key") == 1
    assert extraction_calls == [pdf]

    digest = hashlib.sha256(pdf).hexdigest()
    current = bigquery_client.tables["fixture-project.stocks.financials"]
    revisions = bigquery_client.tables[
        "fixture-project.stocks.financial_report_revisions"
    ]
    assert len(current) == 1
    assert {key: current[0][key] for key in result} == result
    assert len(revisions) == 1
    assert revisions[0]["document_revision"] == digest
    assert revisions[0]["document_link"] == (
        f"gs://archive-123/financial_report_revisions/ABC/2025/{digest}.pdf"
    )
    source_blobs = storage_client.bucket("data-123").blobs
    assert not any(name.startswith("financials/") for name in source_blobs)
    artifact = json.loads(
        source_blobs[f"financial_extraction_artifacts/{digest}.json"].payload or "{}"
    )
    assert artifact["pdf_sha256"] == digest
    assert artifact["model"] == "fixture/model-v1"
    assert artifact["prompt"] == "fixture prompt"
    assert artifact["response"] == {"id": "fixture-response"}
    assert storage_client.bucket("archive-123").blob(
        f"financial_report_revisions/ABC/2025/{digest}.pdf"
    ).download_as_bytes() == pdf


def test_importing_financial_pipeline_modules_does_not_construct_clients_or_call_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def forbidden(name):
        def fail(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"import must not invoke {name}")
        return fail

    framework = ModuleType("functions_framework")
    framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", framework)
    monkeypatch.setitem(sys.modules, "yaml", SimpleNamespace(safe_load=forbidden("yaml")))
    monkeypatch.setitem(sys.modules, "bs4", SimpleNamespace(BeautifulSoup=forbidden("BeautifulSoup")))
    requests = SimpleNamespace(Session=forbidden("provider/source session"), post=forbidden("provider"))
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=requests))

    google_auth = ModuleType("google.auth")
    google_auth.default = forbidden("google.auth.default")  # type: ignore[attr-defined]
    cloud = ModuleType("google.cloud")
    cloud.storage = SimpleNamespace(Client=forbidden("storage.Client"))  # type: ignore[attr-defined]
    cloud.bigquery = SimpleNamespace(Client=forbidden("bigquery.Client"))  # type: ignore[attr-defined]
    google = ModuleType("google")
    google.auth = google_auth  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)

    helper = ModuleType("helper")
    for name in (
        "get_financial_report_revision",
        "get_symbols_from_richbourse",
        "save_dataframe_as_csv",
        "table_exists",
        "upsert_financial_report_and_archive",
        "upsert_financial_report_current_and_revision",
    ):
        setattr(helper, name, lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "helper", helper)
    company_reference = ModuleType("company_reference")
    company_reference.build_company_records = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    company_reference.read_mapping = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "company_reference", company_reference)

    for path, name in (
        ("scrape_financials.py", "financial_import_scraper"),
        ("scrape_financials_init.py", "financial_import_init"),
        ("insert_financials.py", "financial_import_insert"),
    ):
        _load_module(SCRIPTS / path, name)

    assert calls == []
