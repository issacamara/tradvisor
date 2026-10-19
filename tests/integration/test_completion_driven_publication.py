from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import threading
from pathlib import Path
from typing import Literal

from backend.configuration import PublicationControlConfiguration
from backend.contracts.publication_control import (
    MAX_ANALYTICAL_ATTEMPTS,
    ManagedImportCompletion,
    ManagedWriteReceipt,
    SourceInputIdentity,
)
from backend.publication.control import (
    PublicationControlState,
    PublicationRequestController,
)


START = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
Fingerprint = Literal["a", "b", "c"]


class MemoryStore:
    def __init__(self) -> None:
        self.state = PublicationControlState()
        self.lock = threading.RLock()

    def transact(self, transition):  # type: ignore[no-untyped-def]
        with self.lock:
            result = transition(self.state)
            return result


@dataclass
class RecordingObserver:
    completions: list[tuple[str, str]]
    controls: list[tuple[str, int, int | None]]

    def completion(self, *, source: str, outcome: str, now: datetime) -> None:
        del now
        self.completions.append((source, outcome))

    def control(
        self,
        *,
        outcome: str,
        sources: str,
        attempts: int = 0,
        now: datetime,
        duration_ms: int | None = None,
    ) -> None:
        del sources, now
        self.controls.append((outcome, attempts, duration_ms))


class RecordingInvoker:
    def __init__(self, *, failures: int = 0) -> None:
        self.calls: list[SourceInputIdentity] = []
        self.failures = failures

    def invoke_and_wait(self, input_identity: SourceInputIdentity) -> None:
        self.calls.append(input_identity)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("fixture-only invocation failure")


def completion(
    source: Literal["shares", "financials", "ratings"],
    revision: Fingerprint,
    *,
    status: Literal["succeeded", "failed"] = "succeeded",
) -> ManagedImportCompletion:
    receipt = (
        ManagedWriteReceipt(
            revision_fingerprint=revision * 64,
            completed_at=START,
        )
        if status == "succeeded"
        else None
    )
    return ManagedImportCompletion(source=source, status=status, managed_write=receipt)


def controller(
    store: MemoryStore,
    invoker: RecordingInvoker,
    observer: RecordingObserver,
) -> PublicationRequestController:
    return PublicationRequestController(
        store,
        invoker,
        PublicationControlConfiguration(debounce_seconds=10),
        observer,
        clock=lambda: START + timedelta(seconds=11),
    )


def test_changed_imports_create_one_timed_job_request_and_coalesce() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker()
    observer = RecordingObserver([], [])
    control = controller(store, invoker, observer)

    control.accept(completion("shares", "a"), received_at=START)
    control.accept(
        completion("financials", "b"), received_at=START + timedelta(seconds=2)
    )

    assert control.dispatch_ready(now=START + timedelta(seconds=9)) is None
    outcome = control.dispatch_ready(now=START + timedelta(seconds=10))

    assert outcome is not None and outcome.outcome == "published"
    assert outcome.input_identity is not None
    assert {item.source for item in outcome.input_identity.inputs} == {
        "shares",
        "financials",
    }
    assert invoker.calls == [outcome.input_identity]
    assert observer.controls[-1] == ("published", 1, 11000)


def test_ratings_failures_unchanged_and_duplicate_delivery_do_not_execute() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker()
    observer = RecordingObserver([], [])
    control = controller(store, invoker, observer)

    assert control.accept(completion("ratings", "a"), received_at=START) is None
    failed = control.accept(
        completion("shares", "a", status="failed"), received_at=START
    )
    assert failed is not None and failed.outcome == "import_failed_no_request"
    assert control.dispatch_ready(now=START + timedelta(seconds=20)) is None
    assert invoker.calls == []

    event = completion("shares", "a")
    control.accept(event, received_at=START)
    first = control.dispatch_ready(now=START + timedelta(seconds=10))
    assert first is not None and first.outcome == "published"

    control.accept(event, received_at=START + timedelta(seconds=11))
    second = control.dispatch_ready(now=START + timedelta(seconds=21))
    assert second is not None and second.outcome == "unchanged_input_no_op"
    assert invoker.calls == [first.input_identity]


def test_duplicate_dispatchers_claim_one_analytical_execution() -> None:
    store = MemoryStore()
    started = threading.Event()
    release = threading.Event()

    class BlockingInvoker(RecordingInvoker):
        def invoke_and_wait(self, input_identity: SourceInputIdentity) -> None:
            super().invoke_and_wait(input_identity)
            started.set()
            assert release.wait(timeout=2)

    invoker = BlockingInvoker()
    observer = RecordingObserver([], [])
    control = controller(store, invoker, observer)
    control.accept(completion("shares", "a"), received_at=START)
    now = START + timedelta(seconds=10)
    results: list[object] = []
    worker = threading.Thread(target=lambda: results.append(control.dispatch_ready(now=now)))
    worker.start()
    assert started.wait(timeout=2)

    assert control.dispatch_ready(now=now) is None
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(invoker.calls) == 1
    assert results[0].outcome == "published"  # type: ignore[union-attr]


def test_retry_exhaustion_is_bounded_and_keeps_previous_publication_identity() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker(failures=MAX_ANALYTICAL_ATTEMPTS)
    observer = RecordingObserver([], [])
    control = controller(store, invoker, observer)
    control.accept(completion("shares", "a"), received_at=START)
    previous_identity = "complete-batch-before-retry"

    outcome = control.dispatch_ready(now=START + timedelta(seconds=10))

    assert outcome is not None and outcome.outcome == "analytical_failed"
    assert outcome.analytical_attempts == MAX_ANALYTICAL_ATTEMPTS
    assert len(invoker.calls) == MAX_ANALYTICAL_ATTEMPTS
    assert previous_identity == "complete-batch-before-retry"
    assert store.state.active_identity is None
    assert control.dispatch_ready(now=START + timedelta(seconds=30)) is None
    assert len(invoker.calls) == MAX_ANALYTICAL_ATTEMPTS


def test_terraform_exposes_one_batch_job_without_an_analytical_scheduler() -> None:
    root = Path(__file__).resolve().parents[2]
    variables = (root / "terraform" / "variables.tf").read_text(encoding="utf-8")
    functions = (root / "terraform" / "functions.tf").read_text(encoding="utf-8")
    runtime = (root / "terraform" / "runtime.tf").read_text(encoding="utf-8")

    assert 'name = "shares"' in variables
    assert 'name = "financials"' in variables
    assert 'name = "ratings"' in variables
    scheduler = functions.split('resource "google_cloud_scheduler_job" "jobs"', 1)[1]
    assert "daily_publication" not in scheduler
    assert 'resource "google_cloud_run_v2_job" "v1_batch"' in runtime
    assert runtime.count('resource "google_cloud_run_v2_job" "v1_batch"') == 1
