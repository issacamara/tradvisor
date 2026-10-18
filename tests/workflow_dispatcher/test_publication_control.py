from __future__ import annotations

from copy import deepcopy
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import threading
from typing import Literal, TypeVar

from backend.configuration import PublicationControlConfiguration
from backend.contracts.publication_control import (
    MAX_ANALYTICAL_ATTEMPTS,
    ManagedImportCompletion,
    ManagedWriteReceipt,
    PublicationControlOutcome,
    SourceInputIdentity,
)
from backend.publication.control import (
    PublicationControlState,
    PublicationRequestController,
)

START = datetime(2026, 10, 18, tzinfo=timezone.utc)
_T = TypeVar("_T")


class MemoryStore:
    def __init__(self) -> None:
        self.state = PublicationControlState()
        self.lock = threading.RLock()

    def transact(
        self, transition: Callable[[PublicationControlState], _T]
    ) -> _T:
        with self.lock:
            candidate = deepcopy(self.state)
            result = transition(candidate)
            self.state = candidate
            return result


class RecordingInvoker:
    def __init__(self, failures: int = 0) -> None:
        self.calls: list[SourceInputIdentity] = []
        self.failures = failures

    def invoke_and_wait(self, input_identity: SourceInputIdentity) -> None:
        self.calls.append(input_identity)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("private invoker error is not persisted")


def completion(
    source: Literal["shares", "financials", "ratings"],
    revision: str,
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


def controller(store: MemoryStore, invoker: RecordingInvoker) -> PublicationRequestController:
    return PublicationRequestController(
        store, invoker, PublicationControlConfiguration(debounce_seconds=10)
    )


def test_ratings_and_failed_imports_never_request_publication() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker()
    control = controller(store, invoker)

    assert control.accept(completion("ratings", "a"), received_at=START) is None
    failed = control.accept(
        completion("shares", "a", status="failed"), received_at=START
    )

    assert failed is not None
    assert failed.outcome == "import_failed_no_request"
    assert store.state.ready_inputs == ()
    assert control.dispatch_ready(now=START + timedelta(seconds=20)) is None
    assert invoker.calls == []


def test_debounce_coalesces_latest_eligible_sources_into_one_job_request() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker()
    control = controller(store, invoker)
    control.accept(completion("shares", "a"), received_at=START)
    control.accept(completion("financials", "b"), received_at=START + timedelta(seconds=2))

    assert control.dispatch_ready(now=START + timedelta(seconds=9)) is None
    outcome = control.dispatch_ready(now=START + timedelta(seconds=10))

    assert outcome is not None and outcome.outcome == "published"
    assert outcome.input_identity is not None
    assert [item.source for item in outcome.input_identity.inputs] == ["financials", "shares"]
    assert invoker.calls == [outcome.input_identity]


def test_duplicate_completion_is_a_bounded_no_op_after_success() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker()
    control = controller(store, invoker)
    event = completion("shares", "a")
    control.accept(event, received_at=START)
    first = control.dispatch_ready(now=START + timedelta(seconds=10))
    assert first is not None and first.outcome == "published"

    control.accept(event, received_at=START + timedelta(seconds=11))
    second = control.dispatch_ready(now=START + timedelta(seconds=21))

    assert second is not None and second.outcome == "unchanged_input_no_op"
    assert invoker.calls == [first.input_identity]


def test_changed_financial_revision_requests_correction_through_same_invoker() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker()
    control = controller(store, invoker)
    control.accept(completion("shares", "b"), received_at=START)
    control.accept(completion("financials", "a"), received_at=START)
    first = control.dispatch_ready(now=START + timedelta(seconds=10))
    control.accept(completion("financials", "c"), received_at=START + timedelta(seconds=11))
    second = control.dispatch_ready(now=START + timedelta(seconds=21))

    assert first is not None and second is not None
    assert first.outcome == second.outcome == "published"
    assert first.input_identity != second.input_identity
    assert first.input_identity is not None and second.input_identity is not None
    assert first.input_identity.digest != second.input_identity.digest
    assert {item.source for item in second.input_identity.inputs} == {"shares", "financials"}
    assert invoker.calls == [first.input_identity, second.input_identity]


def test_concurrent_dispatchers_claim_one_invocation() -> None:
    store = MemoryStore()
    started = threading.Event()
    release = threading.Event()

    class BlockingInvoker(RecordingInvoker):
        def invoke_and_wait(self, input_identity: SourceInputIdentity) -> None:
            super().invoke_and_wait(input_identity)
            started.set()
            assert release.wait(timeout=2)

    invoker = BlockingInvoker()
    control = controller(store, invoker)
    control.accept(completion("shares", "a"), received_at=START)
    now = START + timedelta(seconds=10)
    first_result: list[PublicationControlOutcome | None] = []
    worker = threading.Thread(target=lambda: first_result.append(control.dispatch_ready(now=now)))
    worker.start()
    assert started.wait(timeout=2)

    assert control.dispatch_ready(now=now) is None
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(invoker.calls) == 1
    assert first_result[0] is not None and first_result[0].outcome == "published"


def test_invocation_failure_is_sanitized_and_stops_after_finite_attempts() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker(failures=MAX_ANALYTICAL_ATTEMPTS + 1)
    control = controller(store, invoker)
    control.accept(completion("shares", "a"), received_at=START)

    outcome = control.dispatch_ready(now=START + timedelta(seconds=10))

    assert outcome is not None and outcome.outcome == "analytical_failed"
    assert outcome.analytical_attempts == MAX_ANALYTICAL_ATTEMPTS
    assert len(invoker.calls) == MAX_ANALYTICAL_ATTEMPTS
    assert "private invoker error" not in str(store.state.to_record())
    assert store.state.active_identity is None
    assert store.state.last_requested_identity == outcome.input_identity
    assert control.dispatch_ready(now=START + timedelta(seconds=30)) is None
    assert len(invoker.calls) == MAX_ANALYTICAL_ATTEMPTS


def test_persisted_state_round_trips_only_sanitized_fields() -> None:
    store = MemoryStore()
    invoker = RecordingInvoker()
    control = controller(store, invoker)
    control.accept(completion("shares", "a"), received_at=START)
    record = store.state.to_record()
    restored = PublicationControlState.from_record(record)

    assert restored.to_record() == record
    assert set(record) == {
        "coalescing_started_at", "ready_inputs", "last_requested_identity",
        "active_identity", "analytical_attempts", "last_outcome",
    }
    assert "payload" not in str(record)
