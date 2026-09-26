from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import pytest
from pydantic import BaseModel

from backend.contracts.scalars import OpaqueIdentifier
from backend.contracts.paper import PaperExecution
from backend.store.repositories import (
    DocumentKey,
    GenerationConflict,
    OwnerContext,
    Page,
    PaperRepositories,
    PublicationRepositories,
    RepositoryError,
    SnapshotChanged,
    VersionConflict,
    VersionedDocument,
    consistent_read,
)
from backend.store.transactions import Transaction


class Record(BaseModel):
    generation: str
    value: int


@dataclass
class FakeTransaction:
    writes: dict[str, VersionedDocument[BaseModel]] = field(default_factory=dict)
    commit_immediately: bool = True


class FakeStore:
    def __init__(self) -> None:
        self.documents: dict[str, VersionedDocument[BaseModel]] = {}
        self.queries: list[dict[str, Any]] = []
        self.callbacks: list[Callable[[Transaction], Any]] = []
        self.retry_once_with: VersionedDocument[BaseModel] | None = None
        self.retry_once_with_control: VersionedDocument[BaseModel] | None = None

    def get(self, key: DocumentKey) -> VersionedDocument[BaseModel] | None:
        return self.documents.get(key.path)

    def page(
        self,
        collection: str,
        *,
        filters: tuple[tuple[str, str, str], ...],
        order_by: tuple[tuple[str, Literal["asc", "desc"]], ...],
        limit: int,
        cursor: str | None,
    ) -> Page[BaseModel]:
        self.queries.append(
            {
                "collection": collection,
                "filters": filters,
                "order_by": order_by,
                "limit": limit,
                "cursor": cursor,
            }
        )
        return Page((), "next" if cursor is None else None)

    def run(
        self, callback: Callable[[Transaction], Any], *, max_attempts: int
    ) -> Any:
        self.callbacks.append(callback)
        transaction = FakeTransaction(commit_immediately=False)
        result = callback(transaction)
        if self.retry_once_with is not None or self.retry_once_with_control is not None:
            concurrent = self.retry_once_with
            self.retry_once_with = None
            if concurrent is not None:
                self.documents[concurrent.key.path] = concurrent
            control = self.retry_once_with_control
            self.retry_once_with_control = None
            if control is not None:
                self.documents[control.key.path] = control
            self.callbacks.append(callback)
            transaction = FakeTransaction(commit_immediately=False)
            result = callback(transaction)
        self.documents.update(transaction.writes)
        return result

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        assert isinstance(transaction, FakeTransaction)
        if key.path in transaction.writes:
            return transaction.writes[key.path]
        return self.documents.get(key.path)

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None:
        assert isinstance(transaction, FakeTransaction)
        transaction.writes[document.key.path] = document
        if transaction.commit_immediately:
            self.documents.update(transaction.writes)


@pytest.fixture
def repositories() -> tuple[FakeStore, PaperRepositories]:
    store = FakeStore()
    owner = OwnerContext(uid=OpaqueIdentifier("verified-user"))
    return store, PaperRepositories(store, owner)


def _control(generation: str | None) -> BaseModel:
    from backend.contracts.paper import PortfolioControl

    return PortfolioControl.model_validate(
        {
            "owner_uid": "verified-user",
            "active_generation": generation,
            "configured_fee_rate_pct": None,
            "state_version": 0,
            "preference_version": 0,
            "recovery_id": "recovery-1",
            "updated_at": datetime.now(timezone.utc),
        }
    )


def test_document_paths_are_stable_and_owner_scoped(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    _, repo = repositories
    generation = OpaqueIdentifier("generation-1")
    symbol = OpaqueIdentifier("ABC")

    assert repo.control_key().path == "paper_portfolios/verified-user"
    assert repo.generation_key(generation).path == (
        "paper_portfolios/verified-user/generations/generation-1"
    )
    assert repo.position_key(generation, symbol).document_id == "ABC"
    assert repo.order_key(generation, OpaqueIdentifier("order-1")).document_id == "order-1"
    assert repo.execution_key(generation, OpaqueIdentifier("order-1")).document_id == "order-1"
    assert repo.cash_movement_key(generation, OpaqueIdentifier("cash-1")).document_id == "cash-1"
    assert repo.receipt_key("request-1").path.startswith(
        "paper_portfolios/verified-user/command_receipts/"
    )

    with pytest.raises(RepositoryError, match="outside the authenticated owner scope"):
        repo.write_in_transaction(
            FakeTransaction(),
            key=DocumentKey("paper_portfolios/other-user/generations/g1/orders", "o1"),
            record=Record(generation="g1", value=1),
            schema_version=1,
            expected_state_version=None,
        )


def test_versioned_write_advances_only_the_expected_version(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    store, repo = repositories
    key = repo.generation_key(OpaqueIdentifier("g1"))
    store.documents[repo.control_key().path] = VersionedDocument(
        key=repo.control_key(), schema_version=1, state_version=0, record=_control("g1")
    )
    first = repo.write_in_transaction(
        FakeTransaction(),
        key=key,
        record=Record(generation="g1", value=1),
        schema_version=1,
        expected_state_version=None,
    )
    assert first.state_version == 0

    second = repo.write_in_transaction(
        FakeTransaction(),
        key=key,
        record=Record(generation="g1", value=2),
        schema_version=1,
        expected_state_version=0,
    )
    assert second.state_version == 1
    assert Record.model_validate(store.documents[key.path].record).value == 2

    with pytest.raises(VersionConflict):
        repo.write_in_transaction(
            FakeTransaction(),
            key=key,
            record=Record(generation="g1", value=3),
            schema_version=1,
            expected_state_version=0,
        )


def test_retryable_callback_has_a_finite_budget_and_no_external_runner(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    store, repo = repositories
    invocations: list[int] = []
    def callback(_transaction: Transaction) -> str:
        invocations.append(1)
        return "committed"

    result = repo.transact(callback)

    assert result == "committed"
    assert len(invocations) == 1
    assert len(store.callbacks) == 1
    with pytest.raises(ValueError, match="between 1 and 10"):
        repo.transact(lambda _transaction: None, max_attempts=11)


def test_concurrent_version_change_retries_callback_from_new_state(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    store, repo = repositories
    key = repo.generation_key(OpaqueIdentifier("g1"))
    store.documents[repo.control_key().path] = VersionedDocument(
        key=repo.control_key(), schema_version=1, state_version=0, record=_control("g1")
    )
    store.documents[key.path] = VersionedDocument(
        key=key,
        schema_version=1,
        state_version=0,
        record=Record(generation="g1", value=10),
    )
    store.retry_once_with = VersionedDocument(
        key=key,
        schema_version=1,
        state_version=1,
        record=Record(generation="g1", value=20),
    )
    callback_attempts: list[int] = []

    def increment(transaction: Transaction) -> VersionedDocument[Record]:
        current = store.get_in_transaction(transaction, key)
        assert current is not None
        callback_attempts.append(current.state_version)
        record = Record.model_validate(current.record.model_dump())
        record.value += 1
        return repo.write_in_transaction(
            transaction,
            key=key,
            record=record,
            schema_version=1,
            expected_state_version=current.state_version,
        )

    result = repo.transact(increment)

    assert callback_attempts == [0, 1]
    assert result.state_version == 2
    assert result.record.value == 21


def test_reset_race_rejects_old_generation_on_retry(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    store, repo = repositories
    key = repo.generation_key(OpaqueIdentifier("g1"))
    control_key = repo.control_key()
    store.documents[control_key.path] = VersionedDocument(
        key=control_key, schema_version=1, state_version=0, record=_control("g1")
    )
    store.retry_once_with_control = VersionedDocument(
        key=control_key, schema_version=1, state_version=1, record=_control("g2")
    )

    def stale_write(transaction: Transaction) -> None:
        repo.write_in_transaction(
            transaction,
            key=key,
            record=Record(generation="g1", value=1),
            schema_version=1,
            expected_state_version=None,
        )

    with pytest.raises(GenerationConflict, match="not the active"):
        repo.transact(stale_write)
    assert key.path not in store.documents


def test_execution_identity_is_one_to_one_with_order(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    store, repo = repositories
    generation = OpaqueIdentifier("g1")
    order_id = OpaqueIdentifier("order-1")
    store.documents[repo.control_key().path] = VersionedDocument(
        key=repo.control_key(), schema_version=1, state_version=0, record=_control("g1")
    )
    key = repo.execution_key(generation, order_id)
    first = PaperExecution.model_construct(order_id=order_id, execution_id=order_id)
    repo.write_in_transaction(
        FakeTransaction(),
        key=key,
        record=first,
        schema_version=1,
        expected_state_version=None,
    )

    duplicate_identity = PaperExecution.model_construct(
        order_id=order_id, execution_id=OpaqueIdentifier("fill-2")
    )
    with pytest.raises(RepositoryError, match="execution identity"):
        repo.write_in_transaction(
            FakeTransaction(),
            key=key,
            record=duplicate_identity,
            schema_version=1,
            expected_state_version=0,
        )


def test_order_query_is_bounded_ordered_and_generation_scoped(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    store, repo = repositories
    generation = OpaqueIdentifier("g1")
    page = repo.list_orders(generation, limit=25, cursor="opaque-cursor")

    assert page.items == ()
    assert store.queries == [
        {
            "collection": "paper_portfolios/verified-user/generations/g1/orders",
            "filters": (("generation", "==", "g1"),),
            "order_by": (("accepted_at", "desc"), ("order_id", "desc")),
            "limit": 25,
            "cursor": "opaque-cursor",
        }
    ]
    with pytest.raises(ValueError, match="limit must be between"):
        repo.list_orders(generation, limit=101)


def test_publication_results_are_immutable_and_bounded_by_batch(
    repositories: tuple[FakeStore, PaperRepositories],
) -> None:
    store, _ = repositories
    publications = PublicationRepositories(store)
    batch_id = OpaqueIdentifier("batch/one")
    record_id = OpaqueIdentifier("company/A")
    record = Record(generation="batch/one", value=7)

    first = publications.write_result(
        FakeTransaction(),
        batch_id=batch_id,
        record_id=record_id,
        record=record,
        schema_version=1,
    )
    repeated = publications.write_result(
        FakeTransaction(),
        batch_id=batch_id,
        record_id=record_id,
        record=record,
        schema_version=1,
    )
    assert first.key == repeated.key
    assert first.key.path == "analysis_batches/batch%2Fone/results/company%2FA"

    with pytest.raises(RepositoryError, match="immutable"):
        publications.write_result(
            FakeTransaction(),
            batch_id=batch_id,
            record_id=record_id,
            record=Record(generation="batch/one", value=8),
            schema_version=1,
        )

    page = publications.list_results(batch_id, limit=10)
    assert page.next_cursor == "next"
    assert store.queries[-1] == {
        "collection": "analysis_batches/batch%2Fone/results",
        "filters": (),
        "order_by": (("__name__", "asc"),),
        "limit": 10,
        "cursor": None,
    }


def test_consistent_read_retries_generation_change_before_returning() -> None:
    reads = iter(((1, "old-generation", "old"), (2, "new-generation", "new")))
    versions = iter(((2, "new-generation"), (2, "new-generation")))

    result = consistent_read(lambda: next(reads), lambda: next(versions))

    assert result == "new"


def test_consistent_read_never_returns_a_mixed_generation() -> None:
    read_versions = iter(((3, "old-generation", "old-state"),) * 3)
    current_versions = iter(((4, "new-generation"),) * 3)

    with pytest.raises(SnapshotChanged):
        consistent_read(lambda: next(read_versions), lambda: next(current_versions))
