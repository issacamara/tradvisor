"""Fixture-only tests for the shared financial PDF extraction path."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
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
    result = {"revenue": 500, "net_income": 100}
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
        "result": {"revenue": 10},
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


def test_initialization_runs_shared_canonical_loader_after_fixture_downloads(
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
    cloud = ModuleType("google.cloud")
    cloud.storage = SimpleNamespace(Client=lambda **kwargs: None)  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    company_reference = ModuleType("company_reference")
    company_reference.build_company_records = lambda *a, **k: []  # type: ignore[attr-defined]
    company_reference.read_mapping = lambda *a, **k: []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "company_reference", company_reference)

    loader_calls: list[str] = []
    insert = ModuleType("insert_financials")
    insert.process_financial_pdfs = lambda key: loader_calls.append(key) or 1  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "insert_financials", insert)
    init = _load_module(SCRIPTS / "scrape_financials_init.py", "financial_pipeline_init")
    monkeypatch.setattr(init, "discover_company_references", lambda path: [])
    monkeypatch.setattr(init, "get_bucket_name", lambda: "fixture-bucket")

    assert init.scrape_financials_init("fixture://source", "fixture-key") == 1
    assert loader_calls == ["fixture-key"]
