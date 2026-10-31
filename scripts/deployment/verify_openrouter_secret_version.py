"""Require an enabled Secret Manager version without reading its payload."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable


SECRET_ID = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def has_enabled_version(
    secret_id: str,
    project_id: str,
    *,
    run: Runner = subprocess.run,
) -> bool:
    """Query enabled version names only; never call access or print CLI output."""
    if not SECRET_ID.fullmatch(secret_id) or not project_id.strip():
        return False
    result = run(
        [
            "gcloud",
            "secrets",
            "versions",
            "list",
            secret_id,
            f"--project={project_id}",
            "--filter=state=ENABLED",
            "--format=value(name)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def main() -> int:
    secret_id = os.environ.get("OPENROUTER_SECRET_ID", "")
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    if not SECRET_ID.fullmatch(secret_id):
        print("OPENROUTER_SECRET_ID must be an explicit non-secret Secret Manager ID", file=sys.stderr)
        return 2
    if not project_id.strip():
        print("GCP_PROJECT_ID is required for the Secret Manager metadata check", file=sys.stderr)
        return 2
    try:
        enabled = has_enabled_version(secret_id, project_id)
    except OSError:
        enabled = False
    if not enabled:
        print("OpenRouter secret has no enabled version in the configured development project", file=sys.stderr)
        return 1
    print("OpenRouter secret-version prerequisite satisfied (metadata only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
