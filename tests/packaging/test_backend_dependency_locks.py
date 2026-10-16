"""Offline checks for the backend's reproducible Python dependency inputs."""

from __future__ import annotations

from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
RUNTIME_LOCK = BACKEND / "requirements" / "runtime.lock"
TEST_LOCK = BACKEND / "requirements" / "test.lock"


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked_packages(lock: Path) -> set[str]:
    return {
        _normalized(match.group(1))
        for match in re.finditer(r"^([A-Za-z0-9_.-]+)==[^\\s]+", lock.read_text(), re.MULTILINE)
    }


def _requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    assert match is not None
    return _normalized(match.group(0))


def test_declared_backend_dependencies_are_locked_with_hashes() -> None:
    configuration = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    runtime_packages = _locked_packages(RUNTIME_LOCK)
    test_packages = _locked_packages(TEST_LOCK)

    declared = [*configuration["project"]["dependencies"], *configuration["build-system"]["requires"]]
    for extra in ("test", "type", "lock"):
        declared.extend(configuration["project"]["optional-dependencies"][extra])

    assert {_requirement_name(requirement) for requirement in declared} <= test_packages
    assert {_requirement_name(requirement) for requirement in configuration["project"]["dependencies"]} <= runtime_packages
    assert _requirement_name(configuration["build-system"]["requires"][0]) in runtime_packages

    for lock in (RUNTIME_LOCK, TEST_LOCK):
        entries = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", lock.read_text())
        locked_entries = [entry for entry in entries if re.match(r"^[A-Za-z0-9_.-]+==", entry)]
        assert locked_entries
        assert all("--hash=sha256:" in entry for entry in locked_entries)


def test_container_installs_the_runtime_lock_and_records_its_identity() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text()

    assert "COPY requirements/runtime.lock /app/backend/requirements/runtime.lock" in dockerfile
    assert "--require-hashes" in dockerfile
    assert "-r /app/backend/requirements/runtime.lock" in dockerfile
    assert "--no-deps --no-build-isolation /app/backend" in dockerfile
    assert "sha256sum /app/backend/requirements/runtime.lock" in dockerfile
    assert "/usr/share/tradvisor-backend-lock.sha256" in dockerfile


def test_ci_installs_locks_and_rejects_lock_drift() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "--require-hashes -r backend/requirements/test.lock" in workflow
    assert "--require-hashes -r backend/requirements/runtime.lock" in workflow
    assert "pip-compile --all-build-deps --allow-unsafe --strip-extras --generate-hashes" in workflow
    assert "--extra=test --extra=type --extra=lock" in workflow
    assert "git diff --exit-code -- backend/requirements" in workflow
