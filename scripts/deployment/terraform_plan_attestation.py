"""Create and verify a non-secret attestation for an exact Terraform plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PlanAttestationError(ValueError):
    """Raised when a reviewed Terraform plan cannot be trusted."""


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise PlanAttestationError(f"Terraform plan is not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as plan:
        for chunk in iter(lambda: plan.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlanAttestationError(f"attestation field {field!r} must be non-empty text")
    return value


def build_attestation(
    *,
    plan: Path,
    release_manifest: Path,
    release_run_id: str,
    environment: str,
    project_id: str,
    state_bucket: str,
    state_prefix: str,
    api_image: str,
) -> dict[str, Any]:
    """Build an attestation using only public release and delivery metadata."""

    try:
        manifest = json.loads(release_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanAttestationError("release manifest is unreadable") from error
    release_id = _required_text(manifest.get("release_id"), "release_id")
    commit = _required_text(manifest.get("commit"), "commit")
    _required_text(release_run_id, "release_run_id")
    _required_text(environment, "environment")
    _required_text(project_id, "project_id")
    _required_text(state_bucket, "state_bucket")
    _required_text(state_prefix, "state_prefix")
    _required_text(api_image, "api_image")
    return {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "release_commit": commit,
        "release_run_id": release_run_id,
        "environment": environment,
        "project_id": project_id,
        "state_bucket": state_bucket,
        "state_prefix": state_prefix,
        "api_image": api_image,
        "terraform_plan_sha256": sha256_file(plan),
    }


def validate_attestation(
    attestation: dict[str, Any],
    *,
    plan: Path,
    release_manifest: Path,
    release_run_id: str,
    environment: str,
    project_id: str,
    state_bucket: str,
    state_prefix: str,
    api_image: str,
) -> None:
    """Fail closed unless the plan matches this release and delivery context."""

    expected = build_attestation(
        plan=plan,
        release_manifest=release_manifest,
        release_run_id=release_run_id,
        environment=environment,
        project_id=project_id,
        state_bucket=state_bucket,
        state_prefix=state_prefix,
        api_image=api_image,
    )
    if attestation != expected:
        raise PlanAttestationError("reviewed Terraform plan does not match the delivery context")
    if not SHA256.fullmatch(str(attestation["terraform_plan_sha256"])):
        raise PlanAttestationError("reviewed Terraform plan checksum is invalid")


def _context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--release-run-id", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--state-bucket", required=True)
    parser.add_argument("--state-prefix", required=True)
    parser.add_argument("--api-image", required=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    _context_args(create)
    create.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    _context_args(verify)
    args = parser.parse_args()
    try:
        values = vars(args)
        context = {key: values[key] for key in (
            "plan", "release_manifest", "release_run_id", "environment", "project_id",
            "state_bucket", "state_prefix", "api_image",
        )}
        if args.command == "create":
            attestation = build_attestation(**context)
            args.output.write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            if args.attestation is None:
                parser.error("--attestation is required for verify")
            attestation = json.loads(args.attestation.read_text(encoding="utf-8"))
            validate_attestation(attestation, **context)
    except (OSError, json.JSONDecodeError, PlanAttestationError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
