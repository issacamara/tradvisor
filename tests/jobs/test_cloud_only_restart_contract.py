"""Offline evidence for restart-safe, cloud-only V1 job boundaries."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOYABLE_ROOTS = (
    ROOT / "backend",
    ROOT / "functions",
    ROOT / "archive" / "legacy-ingestion" / "scripts",
    ROOT / "terraform",
)
TEXT_SUFFIXES = {
    ".Dockerfile",
    ".in",
    ".lock",
    ".py",
    ".tf",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}


def _deployable_text_files() -> list[Path]:
    return sorted(
        path
        for root in DEPLOYABLE_ROOTS
        for path in root.rglob("*")
        if path.is_file() and (path.suffix in TEXT_SUFFIXES or path.name == "Dockerfile")
    )


def test_deployable_sources_have_no_duckdb_or_local_database_dependency() -> None:
    forbidden = ("duckdb", "sqlite3", "sqlite://")
    violations = {
        str(path.relative_to(ROOT)): token
        for path in _deployable_text_files()
        for token in forbidden
        if token in path.read_text(encoding="utf-8").lower()
    }

    assert violations == {}

