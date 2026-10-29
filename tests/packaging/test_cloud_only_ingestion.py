"""Offline package checks for every cloud-only ingestion function artifact."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
from types import ModuleType, SimpleNamespace
from zipfile import ZipFile

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "archive" / "legacy-ingestion" / "scripts"
FUNCTION_ROOTS = {
    "scrape_shares": ROOT / "functions" / "shares",
    "insert_shares": ROOT / "functions" / "shares",
    "scrape_dividends": ROOT / "functions" / "dividends",
    "insert_dividends": ROOT / "functions" / "dividends",
    "scrape_financials": ROOT / "functions" / "financials",
    "insert_financials": ROOT / "functions" / "financials",
    "scrape_financials_init": ROOT / "functions" / "financials",
    "scrape_ratings": ROOT / "functions" / "ratings",
    "insert_ratings": ROOT / "functions" / "ratings",
    "scrape_ratings_init": ROOT / "functions" / "ratings",
}
ARTIFACTS = {
    "normal": (
        "scrape_shares",
        "insert_shares",
        "scrape_dividends",
        "insert_dividends",
        "scrape_financials",
        "insert_financials",
        "scrape_ratings",
        "insert_ratings",
    ),
    "managed": (
        "scrape_shares",
        "insert_shares",
        "scrape_dividends",
        "insert_dividends",
        "scrape_financials",
        "insert_financials",
        "scrape_ratings",
        "insert_ratings",
    ),
    "initialization": ("scrape_financials_init", "scrape_ratings_init"),
}
FUNCTION_LOCAL_FILES = {
    "insert_shares": ("scrape_shares.py",),
    "scrape_financials": ("insert_financials.py", "scrape_financials_init.py"),
    "insert_financials": ("financial_normalization.py",),
}
INITIALIZATION_LOCAL_FILES = {
    "scrape_financials_init": ("company_reference.py",),
    "scrape_ratings_init": ("scrape_ratings.py",),
}
NORMAL_MAPPING_FUNCTIONS = {
    "scrape_financials",
    "insert_financials",
    "scrape_ratings",
    "insert_ratings",
}


def _install_cloud_fakes(monkeypatch: pytest.MonkeyPatch, project_id: str | None = "fixture-project") -> None:
    framework = ModuleType("functions_framework")
    framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", framework)

    bs4 = ModuleType("bs4")
    bs4.BeautifulSoup = lambda *_args, **_kwargs: SimpleNamespace()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bs4", bs4)
    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.CurlHttpVersion = SimpleNamespace(V1_1=2)  # type: ignore[attr-defined]
    curl_cffi.requests = SimpleNamespace(Session=lambda: SimpleNamespace())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "curl_cffi", curl_cffi)

    google = ModuleType("google")
    google.__path__ = []  # type: ignore[attr-defined]
    auth = ModuleType("google.auth")
    auth.default = lambda: ("fixture-credentials", project_id)  # type: ignore[attr-defined]
    cloud = ModuleType("google.cloud")
    cloud.__path__ = []  # type: ignore[attr-defined]
    storage = ModuleType("google.cloud.storage")
    storage.Client = lambda **_kwargs: SimpleNamespace()  # type: ignore[attr-defined]
    bigquery = ModuleType("google.cloud.bigquery")
    bigquery.Client = lambda **_kwargs: SimpleNamespace()  # type: ignore[attr-defined]
    api_core = ModuleType("google.api_core")
    exceptions = ModuleType("google.api_core.exceptions")
    exceptions.PreconditionFailed = type("PreconditionFailed", (Exception,), {})  # type: ignore[attr-defined]
    google.auth = auth  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    google.api_core = api_core  # type: ignore[attr-defined]
    cloud.storage = storage  # type: ignore[attr-defined]
    cloud.bigquery = bigquery  # type: ignore[attr-defined]
    api_core.exceptions = exceptions  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", auth)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", storage)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)
    monkeypatch.setitem(sys.modules, "google.api_core", api_core)
    monkeypatch.setitem(sys.modules, "google.api_core.exceptions", exceptions)


def _build_artifact(tmp_path: Path, artifact_kind: str, name: str) -> Path:
    source_root = FUNCTION_ROOTS[name]
    package = tmp_path / name
    package.mkdir(parents=True)
    for common in (
        "helper.py",
        "ingestion_configuration.py",
        "ingestion_observability.py",
        "requirements.txt",
    ):
        shutil.copy2(SCRIPTS / common, package / common)
    if artifact_kind != "normal" or name in NORMAL_MAPPING_FUNCTIONS:
        shutil.copy2(SCRIPTS / "mapping.csv", package / "mapping.csv")
    shutil.copy2(source_root / f"{name}.py", package / "main.py")
    local_files = (
        INITIALIZATION_LOCAL_FILES.get(name, ())
        if artifact_kind == "initialization"
        else FUNCTION_LOCAL_FILES.get(name, ())
    )
    for local_file in local_files:
        shutil.copy2(source_root / local_file, package / local_file)
    archive = tmp_path / f"{name}.zip"
    with ZipFile(archive, "w") as output:
        for file in package.iterdir():
            output.write(file, file.name)
    extracted = tmp_path / f"{name}-extracted"
    with ZipFile(archive) as output:
        output.extractall(extracted)
    return extracted


def _import_artifact(monkeypatch: pytest.MonkeyPatch, package: Path, module_name: str) -> ModuleType:
    for local_name in (
        "helper",
        "ingestion_configuration",
        "scrape_shares",
        "scrape_ratings",
        "company_reference",
        "insert_financials",
    ):
        monkeypatch.delitem(sys.modules, local_name, raising=False)
    monkeypatch.syspath_prepend(str(package))
    specification = importlib.util.spec_from_file_location(module_name, package / "main.py")
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    specification.loader.exec_module(module)
    return module


def _load_helper(package: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location("helper", package / "helper.py")
    assert specification is not None and specification.loader is not None
    helper = importlib.util.module_from_spec(specification)
    sys.modules["helper"] = helper
    specification.loader.exec_module(helper)
    return helper


def test_declared_artifacts_build_and_import_with_cloud_fakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_cloud_fakes(monkeypatch)
    requirements = (SCRIPTS / "requirements.txt").read_text().lower()

    for artifact_kind, entrypoints in ARTIFACTS.items():
        for entrypoint in entrypoints:
            package = _build_artifact(tmp_path / artifact_kind, artifact_kind, entrypoint)
            module = _import_artifact(monkeypatch, package, f"{artifact_kind}_{entrypoint}")
            assert callable(module.entry_point)
            assert (package / "helper.py").is_file()
            assert (package / "ingestion_configuration.py").is_file()
            assert (package / "requirements.txt").is_file()
            assert (package / "mapping.csv").is_file() is (
                artifact_kind != "normal" or entrypoint in NORMAL_MAPPING_FUNCTIONS
            )

    assert "duckdb" not in requirements


def test_share_scraper_artifact_runs_against_fake_gcs_without_marker_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_cloud_fakes(monkeypatch)
    _set_ingestion_environment(monkeypatch)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FUNCTION_TARGET", raising=False)

    scraper_package = _build_artifact(tmp_path / "scraper", "managed", "scrape_shares")
    monkeypatch.chdir(scraper_package)
    scraper = _import_artifact(monkeypatch, scraper_package, "cloud_fake_scraper")
    helper = _load_helper(scraper_package)
    uploaded: dict[str, str] = {}

    class Blob:
        def __init__(self, name: str) -> None:
            self.name = name

        def upload_from_string(self, content: str, **kwargs: object) -> None:
            assert kwargs == {"content_type": "text/csv", "if_generation_match": 0}
            uploaded[self.name] = content

    bucket = SimpleNamespace(name="fixture-data-bucket", blob=Blob)
    storage = sys.modules["google.cloud.storage"]
    storage.Client = lambda **_kwargs: SimpleNamespace(bucket=lambda _name: bucket)  # type: ignore[attr-defined]
    monkeypatch.setattr(scraper, "scrape_brvm_shares", lambda *_args, **_kwargs: pd.DataFrame())
    assert "fixture-data-bucket" in scraper.entry_point()
    assert len(uploaded) == 1
    assert next(iter(uploaded)).startswith("shares-")


def test_share_loader_artifact_rejects_missing_adc_project_without_local_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_cloud_fakes(monkeypatch, project_id=None)
    _set_ingestion_environment(monkeypatch)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FUNCTION_TARGET", raising=False)

    loader_package = _build_artifact(tmp_path / "loader", "managed", "insert_shares")
    monkeypatch.chdir(loader_package)
    loader = _import_artifact(monkeypatch, loader_package, "cloud_fake_loader")
    _load_helper(loader_package)
    before = {
        path.relative_to(loader_package)
        for path in loader_package.rglob("*")
        if "__pycache__" not in path.parts
    }
    with pytest.raises(ValueError, match="application-default project"):
        loader.entry_point()
    assert {
        path.relative_to(loader_package)
        for path in loader_package.rglob("*")
        if "__pycache__" not in path.parts
    } == before


def test_cloud_references_are_documented_without_secrets_or_local_storage() -> None:
    example = (ROOT / ".env.example").read_text()

    assert "TRADVISOR_RUNTIME_TARGET=ingestion" in example
    assert "TRADVISOR_INGESTION_DATA_BUCKET" in example
    assert "TRADVISOR_INGESTION_SERVICE_ACCOUNT" in example
    assert "TRADVISOR_INGESTION_SOURCE_SHARES_URL" in example
    assert "workload identity" in example
    assert "/Users/" not in example


def _set_ingestion_environment(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setenv(
        "TRADVISOR_INGESTION_COMPANIES_TABLE", "fixture-project.stocks.brvm_companies"
    )
    for asset in ("SHARES", "DIVIDENDS", "FINANCIALS", "RATINGS"):
        monkeypatch.setenv(
            f"TRADVISOR_INGESTION_{asset}_TABLE",
            f"fixture-project.stocks.{asset.lower()}",
        )
    for name in (
        "SHARES", "BRVM_SESSION", "BONDS", "CAPITALIZATIONS", "VOLUMES",
        "INDICES", "DIVIDENDS", "FINANCIALS", "RATINGS", "COMPANY_LISTING",
    ):
        monkeypatch.setenv(
            f"TRADVISOR_INGESTION_SOURCE_{name}_URL",
            f"https://source.example.test/{name.lower()}",
        )


def _source_config() -> dict[str, dict[str, str]]:
    return {
        "url": {
            "shares": "https://source.example.test/shares",
            "brvm_session": "https://source.example.test/sessions",
            "bonds": "https://source.example.test/bonds",
            "capitalizations": "https://source.example.test/capitalizations",
            "volumes": "https://source.example.test/volumes",
            "indices": "https://source.example.test/indices",
            "dividends": "https://source.example.test/dividends",
            "financials": "https://source.example.test/financials",
            "ratings": "https://source.example.test/ratings",
        }
    }
