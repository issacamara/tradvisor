from __future__ import annotations

import hashlib
import json
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from scripts.release.manifest import ManifestError, build_manifest, validate_manifest, verify_manifest_files, write_manifest


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _manifest(tmp_path: Path) -> dict:
    development = tmp_path / "development.tar"
    production = tmp_path / "production.tar"
    artifacts = [(development, "development", b"development frontend"), (production, "production", b"production frontend")]
    for function_name in ("shares", "dividends", "financials", "ratings"):
        artifacts.append((tmp_path / f"{function_name}.tar", f"function:{function_name}", b"function archive"))
    for path, target, payload in artifacts:
        with tarfile.open(path, "w") as archive:
            marker = tarfile.TarInfo(".tradvisor-target")
            marker.size = len(target)
            archive.addfile(marker, BytesIO(target.encode()))
            item = tarfile.TarInfo("payload")
            item.size = len(payload)
            archive.addfile(item, BytesIO(payload))
    return build_manifest(
        release_id="release-2026-10-16",
        commit="a" * 40,
        backend_digest="sha256:" + "b" * 64,
        function_archives={name: tmp_path / f"{name}.tar" for name in ("shares", "dividends", "financials", "ratings")},
        frontend_artifacts={"development": development, "production": production},
        rule_versions={"swing": "swing-v1", "long_term": "long-term-v1"},
        toolchains={"python": "3.11.11", "node": "22.14.0"},
        config_fingerprints={"development": _digest("dev"), "production": _digest("prod")},
    )


def test_manifest_records_immutable_artifacts_and_distinct_environment_checksums(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    assert manifest["backend"] == {"digest": "sha256:" + "b" * 64}
    assert manifest["frontend"]["development"]["sha256"] != manifest["frontend"]["production"]["sha256"]
    validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [("commit", "short"), ("backend", {"digest": "registry/api:latest"})],
)
def test_manifest_rejects_mutable_or_unverifiable_identity(tmp_path: Path, field: str, value: object) -> None:
    manifest = _manifest(tmp_path)
    manifest[field] = value

    with pytest.raises(ManifestError):
        validate_manifest(manifest)


def test_manifest_allows_backend_only_release(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["frontend"] = {}
    manifest["configuration"] = {}

    validate_manifest(manifest)


def test_manifest_rejects_wrong_target_label(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["frontend"]["production"]["target"] = "development"

    with pytest.raises(ManifestError):
        validate_manifest(manifest)


def test_manifest_requires_all_function_archives(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    del manifest["functions"]["ratings"]

    with pytest.raises(ManifestError, match="shares, dividends, financials, and ratings"):
        validate_manifest(manifest)


def test_manifest_verifies_downloaded_artifacts(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    root = tmp_path / "bundle"
    (root / "functions").mkdir(parents=True)
    (root / "frontend").mkdir()
    for source, destination in (
        *[(tmp_path / f"{name}.tar", root / f"functions/{name}.tar") for name in ("shares", "dividends", "financials", "ratings")],
        (tmp_path / "development.tar", root / "frontend/development.tar"),
        (tmp_path / "production.tar", root / "frontend/production.tar"),
    ):
        destination.write_bytes(source.read_bytes())

    verify_manifest_files(manifest, root)


def test_manifest_is_canonical_and_written_atomically(tmp_path: Path) -> None:
    output = tmp_path / "release" / "manifest.json"
    write_manifest(_manifest(tmp_path), output)

    assert json.loads(output.read_text()) == _manifest(tmp_path)
    assert list(output.parent.glob(".*manifest.json.*")) == []
