from __future__ import annotations

import pytest

from backend.workflow_dispatcher import WorkflowDispatchError, dispatch_and_wait


class _Response:
    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return self.payload


class _Session:
    def __init__(self, states: list[str]) -> None:
        self.states = iter(states)
        self.posts: list[str] = []
        self.gets: list[str] = []

    def post(self, url: str, **_: object) -> _Response:
        self.posts.append(url)
        return _Response({"name": "projects/p/locations/r/workflows/shares-wf/executions/1"})

    def get(self, url: str, **_: object) -> _Response:
        self.gets.append(url)
        return _Response({"state": next(self.states)})


def test_dispatch_waits_for_workflow_completion() -> None:
    session = _Session(["RUNNING", "SUCCEEDED"])

    execution = dispatch_and_wait(
        "shares-wf", project="p", region="r", poll_seconds=0, session=session
    )

    assert execution.endswith("/executions/1")
    assert session.posts == [
        "https://workflowexecutions.googleapis.com/v1/projects/p/locations/r/workflows/shares-wf/executions"
    ]
    assert len(session.gets) == 2


def test_dispatch_raises_when_workflow_fails() -> None:
    session = _Session(["FAILED"])

    with pytest.raises(WorkflowDispatchError, match="FAILED"):
        dispatch_and_wait("shares-wf", project="p", region="r", poll_seconds=0, session=session)
