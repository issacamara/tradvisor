from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from backend.commands.admin_support import parse_utc, require_identifier


ROOT = Path(__file__).resolve().parents[2]


def test_admin_commands_are_packaged_in_the_backend_image() -> None:
    configuration = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())
    packages = configuration["tool"]["setuptools"]["packages"]
    assert "backend.commands" in packages
    assert (ROOT / "backend/commands/admission.py").is_file()
    assert (ROOT / "backend/commands/recovery.py").is_file()
    dockerfile = (ROOT / "backend/Dockerfile").read_text()
    assert "COPY . /app/backend/" in dockerfile


@pytest.mark.parametrize("value", ["", "subject/email", "subject with spaces", "x" * 129])
def test_command_identifiers_are_bounded_and_opaque(value: str) -> None:
    with pytest.raises(ValueError, match="bounded opaque"):
        require_identifier(value, field="operation-id")


def test_command_time_requires_explicit_utc() -> None:
    assert parse_utc("2026-10-16T12:00:00Z").tzinfo is not None
    with pytest.raises(ValueError, match="explicit UTC"):
        parse_utc("2026-10-16T12:00:00")
