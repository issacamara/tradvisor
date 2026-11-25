"""Financial commit-then-archive ordering tests."""

from __future__ import annotations

from types import ModuleType
from typing import Any
import pandas as pd
import pytest

from loads_support import (
    _FakeBigQueryClient,
    loader,
    _rows,
    _FakePdfBlob,
    _load_financial_processor,
)  # noqa: F401 (imported fixtures)


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
