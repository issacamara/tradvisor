"""Serialized, completion-driven requests for the existing analytical job."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol, TypeVar

from backend.configuration import PublicationControlConfiguration
from backend.contracts.publication_control import (
    MAX_ANALYTICAL_ATTEMPTS,
    ManagedImportCompletion,
    PublicationControlOutcome,
    ReadySourceInput,
    SourceInputIdentity,
)

_T = TypeVar("_T")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("publication-control time must be an explicit UTC instant")
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class PublicationControlState:
    """Only sanitized coalescing, request, identity, and bounded outcome state."""

    coalescing_started_at: datetime | None = None
    ready_inputs: tuple[ReadySourceInput, ...] = ()
    last_requested_identity: SourceInputIdentity | None = None
    active_identity: SourceInputIdentity | None = None
    analytical_attempts: int = 0
    last_outcome: PublicationControlOutcome | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.analytical_attempts <= MAX_ANALYTICAL_ATTEMPTS:
            raise ValueError("publication-control attempts exceed the bounded limit")
        sources = tuple(item.source for item in self.ready_inputs)
        if len(sources) > 2 or sources != tuple(sorted(set(sources))):
            raise ValueError("publication-control ready inputs must be unique and bounded")
        if bool(self.ready_inputs) != (self.coalescing_started_at is not None):
            raise ValueError("publication-control coalescing time must match pending inputs")
        if self.active_identity is not None and self.active_identity != self.last_requested_identity:
            raise ValueError("active publication identity must match the last request")
        if self.active_identity is not None and not 1 <= self.analytical_attempts <= MAX_ANALYTICAL_ATTEMPTS:
            raise ValueError("active publication request has an invalid attempt count")

    def to_record(self) -> dict[str, object]:
        """Return the strict, sanitized document shape for a persistence adapter."""
        return {
            "coalescing_started_at": (
                self.coalescing_started_at.isoformat().replace("+00:00", "Z")
                if self.coalescing_started_at is not None
                else None
            ),
            "ready_inputs": [item.model_dump(mode="json") for item in self.ready_inputs],
            "last_requested_identity": (
                self.last_requested_identity.model_dump(mode="json")
                if self.last_requested_identity is not None
                else None
            ),
            "active_identity": (
                self.active_identity.model_dump(mode="json")
                if self.active_identity is not None
                else None
            ),
            "analytical_attempts": self.analytical_attempts,
            "last_outcome": (
                self.last_outcome.model_dump(mode="json")
                if self.last_outcome is not None
                else None
            ),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "PublicationControlState":
        expected = {
            "coalescing_started_at", "ready_inputs", "last_requested_identity",
            "active_identity", "analytical_attempts", "last_outcome",
        }
        if set(record) != expected:
            raise ValueError("publication-control record has an invalid shape")
        raw_time = record["coalescing_started_at"]
        if raw_time is not None and not isinstance(raw_time, str):
            raise ValueError("publication-control coalescing time must be a timestamp")
        started = datetime.fromisoformat(raw_time.replace("Z", "+00:00")) if isinstance(raw_time, str) else None

        def identity(value: object) -> SourceInputIdentity | None:
            return SourceInputIdentity.model_validate(value) if value is not None else None

        raw_inputs = record["ready_inputs"]
        if not isinstance(raw_inputs, list):
            raise ValueError("publication-control ready inputs must be a list")
        raw_outcome = record["last_outcome"]
        attempts = record["analytical_attempts"]
        if not isinstance(attempts, int) or isinstance(attempts, bool):
            raise ValueError("publication-control attempts must be an integer")
        return cls(
            coalescing_started_at=_utc(started) if started is not None else None,
            ready_inputs=tuple(ReadySourceInput.model_validate(value) for value in raw_inputs),
            last_requested_identity=identity(record["last_requested_identity"]),
            active_identity=identity(record["active_identity"]),
            analytical_attempts=attempts,
            last_outcome=(
                PublicationControlOutcome.model_validate(raw_outcome)
                if raw_outcome is not None
                else None
            ),
        )


class PublicationControlStore(Protocol):
    """Persistence seam; transact must serialize and atomically commit transitions."""

    def transact(self, transition: Callable[[PublicationControlState], _T]) -> _T:
        """Run one transition against the latest state under a durable transaction."""
        ...


class ExistingAnalyticalJobInvoker(Protocol):
    """Idempotent adapter for invoking and waiting on the existing job."""

    def invoke_and_wait(self, input_identity: SourceInputIdentity) -> None:
        """Wait for terminal publication; the identity is the idempotency key."""
        ...


@dataclass(frozen=True, slots=True)
class _Claim:
    identity: SourceInputIdentity
    attempt: int


class PublicationRequestController:
    """Coalesce eligible completions, deduplicate identities, and invoke once."""

    def __init__(
        self,
        store: PublicationControlStore,
        invoker: ExistingAnalyticalJobInvoker,
        configuration: PublicationControlConfiguration,
    ) -> None:
        self._store = store
        self._invoker = invoker
        self._configuration = configuration

    def accept(
        self, completion: ManagedImportCompletion, *, received_at: datetime
    ) -> PublicationControlOutcome | None:
        """Persist one completion; failed eligible imports get a no-request outcome."""
        received_at = _utc(received_at)

        def transition(state: PublicationControlState) -> PublicationControlOutcome | None:
            if completion.status == "failed" and completion.source in {"shares", "financials"}:
                outcome = PublicationControlOutcome(
                    state="no_request", outcome="import_failed_no_request"
                )
                state.last_outcome = outcome
                return outcome
            if not completion.triggers_publication:
                return None
            receipt = completion.managed_write
            if receipt is None:
                raise ValueError("eligible successful completion has no managed-write receipt")
            source: Literal["shares", "financials"]
            if completion.source == "shares":
                source = "shares"
            elif completion.source == "financials":
                source = "financials"
            else:
                return None
            if state.coalescing_started_at is None:
                state.coalescing_started_at = received_at
            previous_inputs = (
                state.ready_inputs
                or (
                    state.last_requested_identity.inputs
                    if state.last_requested_identity is not None
                    else ()
                )
            )
            inputs = {item.source: item for item in previous_inputs}
            inputs[source] = ReadySourceInput(
                source=source,
                revision_fingerprint=receipt.revision_fingerprint,
            )
            state.ready_inputs = tuple(inputs[key] for key in sorted(inputs))
            return None

        return self._store.transact(transition)

    def dispatch_ready(self, *, now: datetime) -> PublicationControlOutcome | None:
        """Dispatch a debounced ready set with finite, serialized retries."""
        now = _utc(now)
        claim = self._store.transact(lambda state: self._claim_ready(state, now))
        if isinstance(claim, PublicationControlOutcome) or claim is None:
            return claim
        if not isinstance(claim, _Claim):
            raise AssertionError("publication-control transition returned an invalid claim")
        active_claim = claim

        for attempt in range(active_claim.attempt, MAX_ANALYTICAL_ATTEMPTS + 1):
            try:
                self._invoker.invoke_and_wait(active_claim.identity)
            except Exception:
                failed = PublicationControlOutcome(
                    state="completed",
                    outcome="analytical_failed",
                    input_identity=active_claim.identity,
                    analytical_attempts=attempt,
                )
                self._store.transact(
                    lambda state: self._finish(state, active_claim.identity, failed)
                )
                if attempt == MAX_ANALYTICAL_ATTEMPTS:
                    return failed
                next_claim = self._store.transact(
                    lambda state: self._retry(state, active_claim.identity, attempt)
                )
                if next_claim is None:
                    return failed
                active_claim = next_claim
                continue

            published = PublicationControlOutcome(
                state="completed",
                outcome="published",
                input_identity=active_claim.identity,
                analytical_attempts=attempt,
            )
            self._store.transact(
                lambda state: self._finish(state, active_claim.identity, published)
            )
            return published
        raise AssertionError("bounded publication retry loop terminated unexpectedly")

    def _claim_ready(
        self, state: PublicationControlState, now: datetime
    ) -> _Claim | PublicationControlOutcome | None:
        started = state.coalescing_started_at
        if started is None or state.active_identity is not None or not state.ready_inputs:
            return None
        if now < started + timedelta(seconds=self._configuration.debounce_seconds):
            return None

        identity = SourceInputIdentity.from_inputs(state.ready_inputs)
        state.coalescing_started_at = None
        state.ready_inputs = ()
        if identity == state.last_requested_identity:
            if state.last_outcome is None or state.last_outcome.outcome != "analytical_failed":
                no_op = PublicationControlOutcome(
                    state="completed",
                    outcome="unchanged_input_no_op",
                    input_identity=identity,
                )
                state.last_outcome = no_op
                return no_op
            if state.analytical_attempts >= MAX_ANALYTICAL_ATTEMPTS:
                return state.last_outcome
        else:
            state.last_requested_identity = identity
            state.analytical_attempts = 0

        state.active_identity = identity
        state.analytical_attempts += 1
        return _Claim(identity=identity, attempt=state.analytical_attempts)

    def _retry(
        self, state: PublicationControlState, identity: SourceInputIdentity, attempt: int
    ) -> _Claim | None:
        if (
            state.active_identity is not None
            or state.last_requested_identity != identity
            or state.analytical_attempts != attempt
            or attempt >= MAX_ANALYTICAL_ATTEMPTS
        ):
            return None
        state.active_identity = identity
        state.analytical_attempts += 1
        return _Claim(identity=identity, attempt=state.analytical_attempts)

    @staticmethod
    def _finish(
        state: PublicationControlState,
        identity: SourceInputIdentity,
        outcome: PublicationControlOutcome,
    ) -> None:
        if state.active_identity == identity:
            state.active_identity = None
            state.last_outcome = outcome
