from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_workspaces_expose_named_navigation_and_table_equivalents() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "frontend/src/app", ROOT / "frontend/src/features").__iter__() if path.is_file())
    all_sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "frontend/src").rglob("*.tsx"))
    assert 'aria-label="Investor workspaces"' in all_sources
    assert "<table" in all_sources and "<caption" in all_sources
    assert 'role="tablist"' in all_sources


def test_accessibility_report_keeps_manual_evidence_and_failures_visible() -> None:
    report = (ROOT / "docs/validation/accessibility.md").read_text(encoding="utf-8")
    assert "manual" in report.lower()
    assert "unresolved" in report.lower()
    assert "WCAG 2.2 AA" in report
