"""Create and validate the immutable V1 release manifest.

The manifest contains only public release metadata and SHA-256 fingerprints. It
never stores artifact contents, credentials, or environment values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import tarfile
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_ENVIRONMENTS = frozenset({"development", "production"})
REQUIRED_FUNCTIONS = frozenset({"shares", "dividends", "financials", "ratings"})


class ManifestError(ValueError):
    """Raised when release metadata is incomplete or mutable."""


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a regular file."""

    if not path.is_file():
        raise ManifestError(f"artifact is not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_target(path: Path) -> str:
    """Read the target marker embedded by the release packager."""

    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                return archive.read(".tradvisor-target").decode("utf-8")
        if tarfile.is_tarfile(path):
            with tarfile.open(path, "r:*") as archive:
                marker = archive.extractfile(".tradvisor-target")
                if marker is not None:
                    return marker.read().decode("utf-8")
    except (KeyError, OSError, UnicodeDecodeError) as error:
        raise ManifestError(f"artifact target marker is unreadable: {path}") from error
    raise ManifestError(f"artifact has no target marker: {path}")


def _pairs(values: Iterable[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        name, separator, item = value.partition("=")
        if not separator or not name or not item or name in result:
            raise ManifestError(f"{label} must contain unique NAME=VALUE entries")
        result[name] = item
    return dict(sorted(result.items()))


def _fingerprints(values: Iterable[str], label: str) -> dict[str, str]:
    result = _pairs(values, label)
    invalid = [name for name, digest in result.items() if not SHA256.fullmatch(digest)]
    if invalid:
        raise ManifestError(f"{label} contains invalid SHA-256 values: {', '.join(invalid)}")
    return result


def build_manifest(
    *,
    release_id: str,
    commit: str,
    backend_digest: str,
    function_archives: Mapping[str, Path],
    frontend_artifacts: Mapping[str, Path],
    rule_versions: Mapping[str, str],
    config_fingerprints: Mapping[str, str],
    toolchains: Mapping[str, str],
    terraform_plan: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic, content-addressed release manifest."""

    if not RELEASE_ID.fullmatch(release_id):
        raise ManifestError("release_id must be a bounded identifier")
    if not COMMIT.fullmatch(commit):
        raise ManifestError("commit must be a full 40-character SHA-1")
    if not IMAGE_DIGEST.fullmatch(backend_digest):
        raise ManifestError("backend_digest must be an immutable sha256:<digest>")
    if REQUIRED_ENVIRONMENTS - frontend_artifacts.keys():
        missing = ", ".join(sorted(REQUIRED_ENVIRONMENTS - frontend_artifacts.keys()))
        raise ManifestError(f"frontend artifacts missing required environments: {missing}")
    if REQUIRED_FUNCTIONS - function_archives.keys():
        missing = ", ".join(sorted(REQUIRED_FUNCTIONS - function_archives.keys()))
        raise ManifestError(f"function archives missing required targets: {missing}")
    if REQUIRED_ENVIRONMENTS - config_fingerprints.keys():
        missing = ", ".join(sorted(REQUIRED_ENVIRONMENTS - config_fingerprints.keys()))
        raise ManifestError(f"configuration fingerprints missing required environments: {missing}")
    if not rule_versions:
        raise ManifestError("at least one rule version is required")
    if not toolchains:
        raise ManifestError("at least one toolchain version is required")

    def artifact_entry(name: str, path: Path) -> dict[str, str]:
        expected_target = name if name in REQUIRED_ENVIRONMENTS else f"function:{name}"
        if artifact_target(path) != expected_target:
            raise ManifestError(f"artifact target does not match {name}: {path}")
        return {"sha256": sha256_file(path), "target": expected_target}

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "commit": commit,
        "backend": {"digest": backend_digest},
        "functions": {
            name: artifact_entry(name, path)
            for name, path in sorted(function_archives.items())
        },
        "frontend": {
            environment: artifact_entry(environment, path)
            for environment, path in sorted(frontend_artifacts.items())
        },
        "rules": dict(sorted(rule_versions.items())),
        "toolchains": dict(sorted(toolchains.items())),
        "configuration": _fingerprints(
            (f"{name}={value}" for name, value in config_fingerprints.items()),
            "configuration fingerprints",
        ),
    }
    if terraform_plan is not None:
        manifest["terraform_plan"] = {"sha256": sha256_file(terraform_plan)}
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a decoded manifest before it is published or consumed."""

    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("unsupported manifest schema")
    for field in ("release_id", "commit", "backend", "functions", "frontend", "rules", "toolchains", "configuration"):
        if field not in manifest:
            raise ManifestError(f"manifest is missing {field}")
    if not isinstance(manifest["release_id"], str) or not RELEASE_ID.fullmatch(manifest["release_id"]):
        raise ManifestError("manifest has an invalid release_id")
    if not isinstance(manifest["commit"], str) or not COMMIT.fullmatch(manifest["commit"]):
        raise ManifestError("manifest has an invalid commit")
    backend = manifest["backend"]
    if not isinstance(backend, Mapping) or not IMAGE_DIGEST.fullmatch(str(backend.get("digest", ""))):
        raise ManifestError("manifest backend digest is not immutable")
    for section in ("functions", "frontend"):
        entries = manifest[section]
        if not isinstance(entries, Mapping) or not entries:
            raise ManifestError(f"manifest {section} must not be empty")
        for name, entry in entries.items():
            expected_target = name if section == "frontend" else f"function:{name}"
            if (not isinstance(name, str) or not isinstance(entry, Mapping)
                    or not SHA256.fullmatch(str(entry.get("sha256", "")))
                    or entry.get("target") != expected_target):
                raise ManifestError(f"manifest {section} entry {name!r} has no valid checksum")
    if REQUIRED_FUNCTIONS - set(manifest["functions"]):
        raise ManifestError("manifest functions must include shares, dividends, financials, and ratings")
    frontend_names = set(manifest["frontend"])
    if REQUIRED_ENVIRONMENTS - frontend_names:
        raise ManifestError("manifest frontend section must include development and production")
    rules = manifest["rules"]
    if not isinstance(rules, Mapping) or not rules or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in rules.items()):
        raise ManifestError("manifest rules must contain non-empty versions")
    toolchains = manifest["toolchains"]
    if not isinstance(toolchains, Mapping) or not toolchains or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in toolchains.items()):
        raise ManifestError("manifest toolchains must contain non-empty versions")
    configuration = manifest["configuration"]
    if not isinstance(configuration, Mapping):
        raise ManifestError("manifest configuration must contain fingerprints")
    if REQUIRED_ENVIRONMENTS - set(configuration):
        raise ManifestError("manifest configuration must include development and production")
    if any(not isinstance(value, str) or not SHA256.fullmatch(value) for value in configuration.values()):
        raise ManifestError("manifest configuration contains an invalid fingerprint")
    if "terraform_plan" in manifest:
        plan = manifest["terraform_plan"]
        if not isinstance(plan, Mapping) or not SHA256.fullmatch(str(plan.get("sha256", ""))):
            raise ManifestError("manifest Terraform plan checksum is invalid")


def write_manifest(manifest: Mapping[str, Any], output: Path) -> None:
    """Write canonical JSON without exposing a partially written manifest."""

    validate_manifest(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as destination:
            json.dump(manifest, destination, indent=2, sort_keys=True)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_manifest_files(manifest: Mapping[str, Any], root: Path) -> None:
    """Verify that the downloaded bundle still matches its manifest."""

    validate_manifest(manifest)
    for name, entry in manifest["functions"].items():
        path = root / "functions" / f"{name}.tar"
        if artifact_target(path) != entry["target"] or sha256_file(path) != entry["sha256"]:
            raise ManifestError(f"function artifact does not match manifest: {name}")
    for environment, entry in manifest["frontend"].items():
        path = root / "frontend" / f"{environment}.tar"
        if artifact_target(path) != entry["target"] or sha256_file(path) != entry["sha256"]:
            raise ManifestError(f"frontend artifact does not match manifest: {environment}")


def _path_pairs(values: list[str], label: str) -> dict[str, Path]:
    return {name: Path(path) for name, path in _pairs(values, label).items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--backend-digest", required=True)
    parser.add_argument("--function-archive", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--frontend-artifact", action="append", default=[], metavar="ENVIRONMENT=PATH")
    parser.add_argument("--rule-version", action="append", default=[], metavar="NAME=VERSION")
    parser.add_argument("--toolchain", action="append", default=[], metavar="NAME=VERSION")
    parser.add_argument("--config-fingerprint", action="append", default=[], metavar="ENVIRONMENT=SHA256")
    parser.add_argument("--terraform-plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    try:
        if args.verify_manifest:
            if args.artifact_root is None:
                parser.error("--artifact-root is required with --verify-manifest")
            manifest = json.loads(args.verify_manifest.read_text(encoding="utf-8"))
            verify_manifest_files(manifest, args.artifact_root)
            return 0
        if args.output is None:
            parser.error("--output is required when creating a manifest")
        manifest = build_manifest(
            release_id=args.release_id,
            commit=args.commit,
            backend_digest=args.backend_digest,
            function_archives=_path_pairs(args.function_archive, "function archives"),
            frontend_artifacts=_path_pairs(args.frontend_artifact, "frontend artifacts"),
            rule_versions=_pairs(args.rule_version, "rule versions"),
            toolchains=_pairs(args.toolchain, "toolchains"),
            config_fingerprints=_pairs(args.config_fingerprint, "configuration fingerprints"),
            terraform_plan=args.terraform_plan,
        )
        write_manifest(manifest, args.output)
    except ManifestError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
