from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RECORD = ROOT / "docs/operations/fi1-cutover-verification.md"


def test_cutover_record_has_release_evidence_and_all_operational_gates() -> None:
    text = RECORD.read_text()

    assert "80eec3e3ed0dec2c1a888b65110c4581bc887ce9" in text
    assert "87045ed9882ed11845c0e074750801b17d1835e0" in text
    assert "c8fa3bd2b5d1f2fca7445318d13820dd5f6da2f9" in text
    assert "fi1_job.digest" in text
    assert "digest value and artifact reference are withheld" in text.lower()
    assert "sha256:" not in text
    assert "tradvisor-" not in text

    for requirement in (
        "one active execution",
        "never exceeds four",
        "within 60 minutes",
        "exactly one state read and one staged `MERGE`",
        "no source document, extracted text/value, prompt, provider response, or extraction evidence was persisted",
        "historical source archives and annual-financial revision assets remain preserved",
        "development Terraform apply/deployment",
        "FI-1 schedule activation",
        "paid provider call or BigQuery query",
        "same immutable image digest",
    ):
        assert requirement in text

    assert "OPENROUTER_API_KEY=" not in text
