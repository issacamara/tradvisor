"""Validate the repository's pinned delivery inputs."""

from __future__ import annotations

import re
from pathlib import Path


PYTHON_VERSION = "3.11.11"
NODE_VERSION = "22.14.0"
TERRAFORM_VERSION = "1.9.8"
FIREBASE_TOOLS_VERSION = "13.29.1"
PYTHON_BASE = (
    "python:3.11.11-slim-bookworm@"
    "sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5"
)


def validate(root: Path) -> None:
    ci = (root / ".github/workflows/ci.yml").read_text()
    development = (root / ".github/workflows/v1-development-delivery.yml").read_text()
    production = (root / ".github/workflows/v1-production-delivery.yml").read_text()
    plan_attestation = (root / "scripts/deployment/terraform_plan_attestation.py").read_text()
    release = (root / ".github/workflows/v1-release.yml").read_text()
    dockerfile = (root / "backend/Dockerfile").read_text()
    manifest = (root / "scripts/release/manifest.py").read_text()

    if ci.count(f'python-version: "{PYTHON_VERSION}"') != 2:
        raise ValueError("CI must pin both Python setup steps")
    for workflow in (ci, development, production):
        if f"terraform_version: {TERRAFORM_VERSION}" not in workflow:
            raise ValueError("all Terraform setup steps must pin Terraform")
        if f"node-version: {NODE_VERSION}" not in workflow:
            raise ValueError("all Node.js setup steps must use the pinned runtime")
        if "firebase-tools@" in workflow and f"firebase-tools@{FIREBASE_TOOLS_VERSION}" not in workflow:
            raise ValueError("Firebase CLI references must use the pinned version")
    if 'uses: actions/upload-artifact@v4' not in release:
        raise ValueError("release workflow must upload the immutable artifact bundle")
    if 'manifest.py' not in release or 'package_artifact.py' not in release:
        raise ValueError("release workflow must package artifacts and create a manifest")
    if f"FROM {PYTHON_BASE}" not in dockerfile:
        raise ValueError("backend image must use the pinned Python digest")
    if re.search(r"firebase-tools@(latest|[0-9]+(?:\.[0-9]+)?(?:\.[0-9]+)?)\b", ci):
        raise ValueError("CI contains a mutable or non-exact Firebase CLI reference")
    if 'IMAGE_DIGEST = re.compile(r"^sha256:' not in manifest:
        raise ValueError("release manifest must require immutable SHA-256 backend digests")
    if 'REQUIRED_ENVIRONMENTS = frozenset({"development", "production"})' not in manifest:
        raise ValueError("release manifest must bind both environment artifacts")
    for workflow in (development, production):
        if "terraform_plan_run_id" not in workflow:
            raise ValueError("delivery workflows must accept an exact reviewed plan run")
        if "terraform_plan_attestation.py verify" not in workflow:
            raise ValueError("apply must verify the Terraform plan attestation")
        if "terraform_plan_attestation.py create" not in workflow:
            raise ValueError("plan must publish a Terraform plan attestation")
        if "terraform apply -auto-approve ../reviewed-plan/tfplan" not in workflow:
            raise ValueError("apply must consume the reviewed Terraform plan")
    if "def validate_attestation" not in plan_attestation or "terraform_plan_sha256" not in plan_attestation:
        raise ValueError("Terraform plan attestation must bind the exact plan checksum")


if __name__ == "__main__":
    validate(Path(__file__).resolve().parents[2])
    print("delivery inputs are pinned")
