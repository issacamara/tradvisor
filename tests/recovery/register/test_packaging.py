from __future__ import annotations

from pathlib import Path
import tomllib


def test_recovery_register_is_declared_in_backend_distribution() -> None:
    repository = Path(__file__).resolve().parents[3]
    configuration_path = repository / "backend" / "pyproject.toml"
    configuration = tomllib.loads(configuration_path.read_text(encoding="utf-8"))
    packages = configuration["tool"]["setuptools"]["packages"]

    assert "backend.recovery" in packages
    assert (repository / "backend" / "recovery" / "register.py").is_file()
