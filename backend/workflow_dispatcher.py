"""Completion-aware Cloud Workflows dispatcher used by serialized queues."""

from __future__ import annotations

import time
from typing import Any


class WorkflowDispatchError(RuntimeError):
    """The workflow could not be started or did not reach a terminal state."""


def dispatch_and_wait(
    workflow_name: str,
    *,
    project: str,
    region: str,
    timeout_seconds: int = 900,
    poll_seconds: float = 2.0,
    session: Any | None = None,
) -> str:
    """Start a workflow and hold the task until its execution terminates."""
    if session is None:
        from google.auth import default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
    base = f"https://workflowexecutions.googleapis.com/v1/projects/{project}/locations/{region}/workflows/{workflow_name}"
    started = session.post(f"{base}/executions", json={"argument": "{}"}, timeout=30)
    started.raise_for_status()
    execution = started.json()
    execution_name = execution.get("name")
    if not isinstance(execution_name, str) or not execution_name:
        raise WorkflowDispatchError("workflow execution did not return a name")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = session.get(f"https://workflowexecutions.googleapis.com/v1/{execution_name}", timeout=30)
        response.raise_for_status()
        state = response.json().get("state")
        if state == "SUCCEEDED":
            return execution_name
        if state in {"FAILED", "CANCELLED", "UNAVAILABLE"}:
            raise WorkflowDispatchError(f"workflow execution ended in {state}")
        time.sleep(poll_seconds)
    raise WorkflowDispatchError("workflow execution exceeded dispatcher timeout")
