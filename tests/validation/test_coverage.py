from pathlib import Path


DOCUMENT = Path("docs/validation/coverage.md")


def test_coverage_document_keeps_source_gaps_visible() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for phrase in ("no missing-year interpolation", "Dividend scoring remains explicitly deferred", "Missing dimensions remain visible"):
        assert phrase.lower() in text.lower()
    assert "/Users/" not in text
    assert "financials.csv" not in text
    assert "shares_low.csv" not in text


def test_coverage_document_has_all_v1_workflows_and_states() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for phrase in ("Growth", "Current advice", "Swing warm-up", "Full", "Partial", "Unavailable", "Owner Acceptance"):
        assert phrase in text
