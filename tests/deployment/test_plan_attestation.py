import hashlib
import json
from pathlib import Path

import pytest

from scripts.deployment.terraform_plan_attestation import (
    PlanAttestationError,
    build_attestation,
    validate_attestation,
)


def _context(tmp_path: Path) -> dict:
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({"release_id": "release-1", "commit": "a" * 40}), encoding="utf-8")
    plan = tmp_path / "tfplan"
    plan.write_bytes(b"reviewed plan")
    return {
        "plan": plan,
        "release_manifest": manifest,
        "release_run_id": "123",
        "environment": "development",
        "project_id": "dev-tradvisor",
        "state_bucket": "dev-tradvisor-tfstate",
        "state_prefix": "state/dev",
        "api_image": "europe-central2-docker.pkg.dev/dev-tradvisor/api@sha256:" + "b" * 64,
    }


def test_attestation_binds_plan_hash_and_delivery_context(tmp_path: Path) -> None:
    context = _context(tmp_path)
    attestation = build_attestation(**context)

    assert attestation["terraform_plan_sha256"] == hashlib.sha256(b"reviewed plan").hexdigest()
    validate_attestation(attestation, **context)


@pytest.mark.parametrize("field", ["release_run_id", "environment", "project_id", "api_image"])
def test_attestation_rejects_context_changes(tmp_path: Path, field: str) -> None:
    context = _context(tmp_path)
    attestation = build_attestation(**context)
    changed = dict(context)
    changed[field] = str(changed[field]) + "-changed"

    with pytest.raises(PlanAttestationError):
        validate_attestation(attestation, **changed)


def test_attestation_rejects_plan_changes(tmp_path: Path) -> None:
    context = _context(tmp_path)
    attestation = build_attestation(**context)
    context["plan"].write_bytes(b"changed plan")

    with pytest.raises(PlanAttestationError):
        validate_attestation(attestation, **context)
