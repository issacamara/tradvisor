"""Integration coverage for BRVM discovery and company-reference adaptation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "archive" / "legacy-ingestion" / "scripts"


def _load_module(path: Path, name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def _load_financial_discovery(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    _load_module(SCRIPTS / "company_reference.py", "company_reference")

    curl_cffi = ModuleType("curl_cffi")
    curl_cffi.requests = SimpleNamespace(  # type: ignore[attr-defined]
        Session=lambda: (_ for _ in ()).throw(AssertionError("unexpected HTTP call"))
    )
    monkeypatch.setitem(sys.modules, "curl_cffi", curl_cffi)

    yaml = ModuleType("yaml")
    yaml.safe_load = lambda stream: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaml", yaml)

    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: (_ for _ in ()).throw(  # type: ignore[attr-defined]
        AssertionError("unexpected credential lookup")
    )
    google_cloud = ModuleType("google.cloud")
    google_storage = ModuleType("google.cloud.storage")
    google_cloud.storage = google_storage  # type: ignore[attr-defined]
    google.auth = google_auth  # type: ignore[attr-defined]
    google.cloud = google_cloud  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.cloud", google_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", google_storage)

    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)

    bs4 = ModuleType("bs4")
    bs4.BeautifulSoup = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[attr-defined]
        AssertionError("unexpected HTML parsing")
    )
    monkeypatch.setitem(sys.modules, "bs4", bs4)

    return _load_module(
        SCRIPTS / "scrape_financials_init.py",
        "scrape_financials_init_company_test",
    )


def test_discovery_builds_references_and_only_processes_known_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scraper = _load_financial_discovery(monkeypatch)
    discovered = [
        ("air-liquide-ci", "AIR LIQUIDE CI"),
        ("mystery-bank", "Mystery Bank"),
    ]
    captured_records = []
    report_calls = []
    download_calls = []
    real_builder = scraper.build_company_records

    def capture_records(catalog, corrections):
        records = real_builder(catalog, corrections)
        captured_records.extend(records)
        return records

    monkeypatch.setattr(scraper, "get_companies_from_brvm", lambda: discovered)
    monkeypatch.setattr(scraper, "build_company_records", capture_records)
    monkeypatch.setattr(scraper, "get_bucket_name", lambda: "test-bucket")

    def mapped_reports(slug, max_year):
        report_calls.append((slug, max_year))
        return [
            {
                "title": "Etats financiers - Exercice 2025",
                "fiscal_year": 2025,
                "pdf_url": "https://example.invalid/financials.pdf",
            }
        ]

    monkeypatch.setattr(scraper, "get_financial_reports_for_company", mapped_reports)
    monkeypatch.setattr(
        scraper,
        "download_pdf_to_storage",
        lambda symbol, fiscal_year, report, bucket: download_calls.append(
            (symbol, fiscal_year, report["pdf_url"], bucket)
        )
        or True,
    )

    assert scraper.scrape_financials_init() == 1

    discovered_records = [record for record in captured_records if record.source_slug]
    assert len(discovered_records) == 2
    assert any(
        record.source_slug == "air-liquide-ci" and record.symbol == "SIVC"
        for record in discovered_records
    )
    assert any(
        record.source_slug == "mystery-bank"
        and record.name == "Mystery Bank"
        and record.symbol is None
        and record.financial_category == "unsupported"
        for record in discovered_records
    )
    assert [slug for slug, _ in report_calls] == ["air-liquide-ci"]
    assert download_calls == [
        (
            "SIVC",
            2025,
            "https://example.invalid/financials.pdf",
            "test-bucket",
        )
    ]
