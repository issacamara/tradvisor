from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import BaseModel

from backend.contracts.analysis import NormalizedPrice, NormalizedSession, Provenance, Revision
from backend.contracts.paper import ExecutionPrice
from backend.contracts.scalars import NonNegativeMoney
from backend.publication.execution_prices import (
    CalendarUnavailable,
    ExecutionPricePublisher,
    ImmutableRevisionConflict,
    PriceRevision,
    RevisionValidity,
    SymbolSessionControl,
)
from backend.store.repositories import DocumentKey, VersionedDocument
from backend.store.transactions import Transaction

UTC = timezone.utc
NOW = datetime(2026, 9, 26, 14, tzinfo=UTC)


class _Transaction:
    def __init__(self, documents: dict[str, VersionedDocument[BaseModel]]) -> None:
        self.documents = documents
        self.writes: dict[str, VersionedDocument[BaseModel]] = {}


class _Store:
    def __init__(self) -> None:
        self.documents: dict[str, VersionedDocument[BaseModel]] = {}
        self.server_time = NOW
        self.lose_next_response = False
        self.commit_count = 0

    def run(self, callback: Callable[[Transaction], Any], *, max_attempts: int) -> Any:
        del max_attempts
        transaction = _Transaction(deepcopy(self.documents))
        result = callback(transaction)  # type: ignore[arg-type]
        self.documents.update(transaction.writes)
        self.commit_count += 1
        self.server_time += timedelta(seconds=1)
        if self.lose_next_response:
            self.lose_next_response = False
            raise TimeoutError("simulated lost commit response")
        return result

    def get(self, key: DocumentKey) -> VersionedDocument[BaseModel] | None:
        return self.documents.get(key.path)

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        return self._transaction(transaction).writes.get(key.path) or self._transaction(
            transaction
        ).documents.get(key.path)

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None:
        self._transaction(transaction).writes[document.key.path] = document

    def put_with_server_timestamps_in_transaction(
        self,
        transaction: Transaction,
        document: VersionedDocument[BaseModel],
        *,
        fields: tuple[str, ...],
    ) -> None:
        resolved = document.record.model_copy(
            update={field: self.server_time for field in fields}
        )
        self.put_in_transaction(
            transaction,
            VersionedDocument(
                document.key,
                document.schema_version,
                document.state_version,
                resolved,
            ),
        )

    @staticmethod
    def _transaction(transaction: Transaction) -> _Transaction:
        assert isinstance(transaction, _Transaction)
        return transaction


def _provenance() -> Provenance:
    return Provenance(
        source_id="brvm",
        collected_at=NOW - timedelta(hours=2),
        published_at=NOW - timedelta(hours=1),
        basis="actual",
    )


def _session(
    *, session_date: date = date(2026, 9, 25), status: str = "trading", version: str = "cal-1"
) -> NormalizedSession:
    return NormalizedSession(
        calendar_version=version,
        session_id=f"session-{session_date.isoformat()}",
        session_date=session_date,
        session_index=10,
        exchange_timezone="Africa/Abidjan",
        status=status,  # type: ignore[arg-type]
        official_close_at=NOW - timedelta(hours=1) if status == "trading" else None,
        source_evidence=(_provenance(),),
        revision=Revision(
            revision=1,
            known_at=NOW - timedelta(hours=1),
            provenance=_provenance(),
        ),
        reason_codes=() if status == "trading" else ("verified_holiday",),
    )


def _price(close: str = "1050.250000") -> NormalizedPrice:
    return NormalizedPrice(
        symbol="SNTS",
        session_date=date(2026, 9, 25),
        close=NonNegativeMoney(amount=close, currency="XOF"),
        close_basis="raw",
        high=NonNegativeMoney(amount="1060", currency="XOF"),
        low=NonNegativeMoney(amount="1040", currency="XOF"),
        volume=125,
        trade_status="traded",
        basis="actual",
        original_source_date=date(2026, 9, 25),
        price_basis_ref="raw-v1",
        validated_available_at=NOW - timedelta(minutes=30),
        suspension_status="not_suspended",
        revision=Revision(
            revision=1,
            known_at=NOW - timedelta(minutes=30),
            provenance=_provenance(),
        ),
    )


def _ready_publisher() -> tuple[_Store, ExecutionPricePublisher]:
    store = _Store()
    publisher = ExecutionPricePublisher(store)  # type: ignore[arg-type]
    publisher.publish_calendar_session(_session())
    return store, publisher


def test_lost_commit_response_and_identical_retry_preserve_one_revision_timestamp() -> None:
    store, publisher = _ready_publisher()
    store.lose_next_response = True

    first = publisher.publish(_price(), source_revision_id="source-rev-1")
    retry = _price().model_copy(
        update={
            "validated_available_at": NOW - timedelta(minutes=5),
            "revision": Revision(
                revision=1,
                known_at=NOW - timedelta(minutes=5),
                provenance=Provenance(
                    source_id="brvm",
                    collected_at=NOW - timedelta(minutes=1),
                    published_at=NOW - timedelta(hours=1),
                    basis="actual",
                ),
            ),
        }
    )
    repeated = publisher.publish(retry, source_revision_id="source-rev-1")

    assert first.validated_available_at == repeated.validated_available_at
    assert first.validated_available_at != _price().validated_available_at
    assert first.sequence == repeated.sequence == 1
    assert first.price_revision_id == repeated.price_revision_id
    assert store.commit_count == 3
    assert len([path for path in store.documents if path.startswith("execution_price_revisions/")]) == 1
    execution_doc = store.get(
        DocumentKey("execution_prices", first.price_revision_id)
    )
    assert execution_doc is not None
    execution_price = ExecutionPrice.model_validate_json(execution_doc.record.model_dump_json())
    assert execution_price.validated_available_at == first.validated_available_at


def test_late_correction_gets_new_server_time_and_next_sequence() -> None:
    _, publisher = _ready_publisher()

    first = publisher.publish(_price(), source_revision_id="source-rev-1")
    correction = publisher.publish(
        _price("1051.000000"), source_revision_id="source-rev-2"
    )

    assert correction.sequence == first.sequence + 1
    assert correction.validated_available_at > first.validated_available_at
    assert correction.validated_available_at != _price().validated_available_at
    control = publisher.read_control("SNTS", date(2026, 9, 25))
    assert isinstance(control, SymbolSessionControl)
    assert control.current_revision_id == correction.price_revision_id
    assert control.revision_sequence == 2


def test_invalidation_appends_event_and_advances_worker_controls_idempotently() -> None:
    store, publisher = _ready_publisher()
    price = publisher.publish(_price(), source_revision_id="source-rev-1")
    before = publisher.read_control("SNTS", date(2026, 9, 25))
    assert before is not None

    first = publisher.invalidate(
        price.price_revision_id, event_id="invalidate-1", reason_code="source_correction"
    )
    repeated = publisher.invalidate(
        price.price_revision_id, event_id="invalidate-1", reason_code="source_correction"
    )
    after = publisher.read_control("SNTS", date(2026, 9, 25))

    assert isinstance(first, RevisionValidity)
    assert first.valid is False
    assert repeated == first
    assert after is not None and after.publication_version == before.publication_version + 1
    assert publisher.read_validity(price.price_revision_id) == first
    assert len([path for path in store.documents if path.startswith("execution_price_validity_events/")]) == 1
    with pytest.raises(ImmutableRevisionConflict):
        publisher.invalidate(
            price.price_revision_id,
            event_id="invalidate-1",
            reason_code="different_reason",
        )


def test_price_publication_requires_active_verified_trading_session() -> None:
    store = _Store()
    publisher = ExecutionPricePublisher(store)  # type: ignore[arg-type]
    with pytest.raises(CalendarUnavailable):
        publisher.publish(_price(), source_revision_id="source-rev-1")

    publisher.publish_calendar_session(_session(status="holiday"))
    with pytest.raises(CalendarUnavailable):
        publisher.publish(_price(), source_revision_id="source-rev-1")


def test_same_source_revision_id_cannot_be_reused_for_different_evidence() -> None:
    _, publisher = _ready_publisher()
    publisher.publish(_price(), source_revision_id="source-rev-1")

    with pytest.raises(ImmutableRevisionConflict):
        publisher.publish(_price("1051"), source_revision_id="source-rev-1")
