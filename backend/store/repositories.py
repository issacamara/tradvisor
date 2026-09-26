"""Bounded, versioned repository interfaces for application-store records.

Adapters map these operations to Firestore transactions and ordered queries.
The module deliberately has no SDK dependency, allowing contract tests to use
local fakes without contacting an emulator or cloud project.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from typing import Generic, Literal, Protocol, TypeVar, cast
from urllib.parse import quote, unquote

from pydantic import BaseModel

from backend.contracts.envelopes import IdempotencyKey
from backend.contracts.paper import (
    CashMovement,
    ExecutionPrice,
    PaperCommandReceipt,
    PaperExecution,
    PaperOrder,
    PaperPosition,
    PaperPreferences,
    PortfolioControl,
    PortfolioSummary,
)
from backend.contracts.scalars import OpaqueIdentifier
from backend.store.transactions import Transaction, TransactionRunner, run_transaction

Record = TypeVar("Record", bound=BaseModel)
T = TypeVar("T")
MAX_PAGE_SIZE = 100
MAX_SNAPSHOT_ATTEMPTS = 3


class RepositoryError(RuntimeError):
    """A repository operation violates its storage or version contract."""


class SnapshotChanged(RepositoryError):
    """The active portfolio changed while a consistent read was assembled."""


class VersionConflict(RepositoryError):
    """The document no longer has the state version observed by the caller."""


class GenerationConflict(RepositoryError):
    """A write targeted a generation that is no longer active."""


@dataclass(frozen=True, slots=True)
class OwnerContext:
    """Owner identity resolved by the authenticated backend boundary."""

    uid: OpaqueIdentifier


@dataclass(frozen=True, slots=True)
class DocumentKey:
    """Stable collection/document path represented without provider objects."""

    collection: str
    document_id: str

    @property
    def path(self) -> str:
        return f"{self.collection}/{self.document_id}"


@dataclass(frozen=True, slots=True)
class VersionedDocument(Generic[Record]):
    key: DocumentKey
    schema_version: int
    state_version: int
    record: Record

    def __post_init__(self) -> None:
        if self.schema_version < 1 or self.state_version < 0:
            raise ValueError("document versions must be nonnegative and schema version positive")


def _segment(value: str) -> str:
    """Encode opaque contract IDs as a single Firestore path segment."""

    return quote(value, safe="")


@dataclass(frozen=True, slots=True)
class Page(Generic[Record]):
    items: tuple[Record, ...]
    next_cursor: str | None


class DocumentReader(Protocol):
    def get(self, key: DocumentKey) -> VersionedDocument[BaseModel] | None: ...


class QueryReader(Protocol):
    def page(
        self,
        collection: str,
        *,
        filters: tuple[tuple[str, str, str], ...],
        order_by: tuple[tuple[str, Literal["asc", "desc"]], ...],
        limit: int,
        cursor: str | None,
        cursor_context: tuple[str, int] | None = None,
    ) -> Page[BaseModel]: ...


class TransactionalStore(DocumentReader, QueryReader, Protocol):
    def run(self, callback: Callable[[Transaction], T], *, max_attempts: int) -> T: ...

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None: ...

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None: ...


class PaperRepositories:
    """Owner-scoped, bounded repository façade for paper and receipt records."""

    def __init__(self, store: TransactionalStore, owner: OwnerContext) -> None:
        self._store = store
        self._owner = owner

    @property
    def owner_uid(self) -> OpaqueIdentifier:
        return self._owner.uid

    def control_key(self) -> DocumentKey:
        return DocumentKey("paper_portfolios", _segment(str(self._owner.uid)))

    def preferences_key(self) -> DocumentKey:
        return DocumentKey("users", _segment(str(self._owner.uid)))

    def generation_key(self, generation: OpaqueIdentifier) -> DocumentKey:
        return DocumentKey(
            f"paper_portfolios/{_segment(str(self._owner.uid))}/generations",
            _segment(str(generation)),
        )

    def position_key(self, generation: OpaqueIdentifier, symbol: OpaqueIdentifier) -> DocumentKey:
        return DocumentKey(
            f"paper_portfolios/{_segment(str(self._owner.uid))}/generations/"
            f"{_segment(str(generation))}/positions",
            _segment(str(symbol)),
        )

    def order_key(self, generation: OpaqueIdentifier, order_id: OpaqueIdentifier) -> DocumentKey:
        return DocumentKey(
            f"paper_portfolios/{_segment(str(self._owner.uid))}/generations/"
            f"{_segment(str(generation))}/orders",
            _segment(str(order_id)),
        )

    def execution_key(
        self, generation: OpaqueIdentifier, order_id: OpaqueIdentifier
    ) -> DocumentKey:
        return DocumentKey(
            f"paper_portfolios/{_segment(str(self._owner.uid))}/generations/"
            f"{_segment(str(generation))}/executions",
            _segment(str(order_id)),
        )

    def cash_movement_key(
        self, generation: OpaqueIdentifier, movement_id: OpaqueIdentifier
    ) -> DocumentKey:
        return DocumentKey(
            f"paper_portfolios/{_segment(str(self._owner.uid))}/generations/"
            f"{_segment(str(generation))}/cash_movements",
            _segment(str(movement_id)),
        )

    def receipt_key(self, key: IdempotencyKey) -> DocumentKey:
        digest = hashlib.sha256(f"{self._owner.uid}\0{key}".encode("utf-8")).hexdigest()
        return DocumentKey(
            f"paper_portfolios/{_segment(str(self._owner.uid))}/command_receipts", digest
        )

    def get_control(self) -> VersionedDocument[PortfolioControl] | None:
        return self._typed(self._store.get(self.control_key()), PortfolioControl)

    def get_preferences(self) -> VersionedDocument[PaperPreferences] | None:
        return self._typed(self._store.get(self.preferences_key()), PaperPreferences)

    def get_summary(
        self, generation: OpaqueIdentifier
    ) -> VersionedDocument[PortfolioSummary] | None:
        return self._read_active(self.generation_key(generation), generation, PortfolioSummary)

    def get_position(
        self, generation: OpaqueIdentifier, symbol: OpaqueIdentifier
    ) -> VersionedDocument[PaperPosition] | None:
        return self._read_active(self.position_key(generation, symbol), generation, PaperPosition)

    def get_order(
        self, generation: OpaqueIdentifier, order_id: OpaqueIdentifier
    ) -> VersionedDocument[PaperOrder] | None:
        return self._read_active(self.order_key(generation, order_id), generation, PaperOrder)

    def get_execution(
        self, generation: OpaqueIdentifier, order_id: OpaqueIdentifier
    ) -> VersionedDocument[PaperExecution] | None:
        return self._read_active(
            self.execution_key(generation, order_id), generation, PaperExecution
        )

    def get_cash_movement(
        self, generation: OpaqueIdentifier, movement_id: OpaqueIdentifier
    ) -> VersionedDocument[CashMovement] | None:
        return self._read_active(
            self.cash_movement_key(generation, movement_id), generation, CashMovement
        )

    @staticmethod
    def execution_price_key(price_revision_id: OpaqueIdentifier) -> DocumentKey:
        return DocumentKey("execution_prices", _segment(str(price_revision_id)))

    def get_execution_price(
        self, price_revision_id: OpaqueIdentifier
    ) -> VersionedDocument[ExecutionPrice] | None:
        return self._typed(self._store.get(self.execution_price_key(price_revision_id)), ExecutionPrice)

    def get_receipt(self, key: IdempotencyKey) -> VersionedDocument[PaperCommandReceipt] | None:
        return self._typed(self._store.get(self.receipt_key(key)), PaperCommandReceipt)

    def list_orders(
        self, generation: OpaqueIdentifier, *, limit: int, cursor: str | None = None
    ) -> Page[PaperOrder]:
        return self._page(
            "orders",
            generation,
            PaperOrder,
            limit=limit,
            cursor=cursor,
            order_by=(("accepted_at", "desc"), ("order_id", "desc")),
        )

    def list_executions(
        self, generation: OpaqueIdentifier, *, limit: int, cursor: str | None = None
    ) -> Page[PaperExecution]:
        return self._page(
            "executions", generation, PaperExecution, limit=limit, cursor=cursor,
            order_by=(("processed_at", "desc"), ("order_id", "desc")),
        )

    def list_cash_movements(
        self, generation: OpaqueIdentifier, *, limit: int, cursor: str | None = None
    ) -> Page[CashMovement]:
        return self._page(
            "cash_movements", generation, CashMovement, limit=limit, cursor=cursor,
            order_by=(("occurred_at", "desc"), ("movement_id", "desc")),
        )

    def transact(self, callback: Callable[[Transaction], T], *, max_attempts: int = 5) -> T:
        """Invoke a transaction-only callback; callbacks may run repeatedly."""

        return run_transaction(self._store, callback, max_attempts=max_attempts)

    def write_in_transaction(
        self,
        transaction: Transaction,
        *,
        key: DocumentKey,
        record: Record,
        schema_version: int,
        expected_state_version: int | None,
    ) -> VersionedDocument[Record]:
        """Create or advance a document after checking its observed version."""

        self._validate_owner_path(key)
        generation = self._generation_for_key(key)
        if generation is not None:
            control = self._store.get_in_transaction(transaction, self.control_key())
            if control is None:
                raise GenerationConflict("cannot write a generation without portfolio control")
            control_record = self._record(control.record, PortfolioControl)
            if control_record.active_generation != generation:
                raise GenerationConflict(
                    f"generation {generation} is not the active portfolio generation"
                )
        if schema_version < 1:
            raise ValueError("schema_version must be positive")
        current = self._store.get_in_transaction(transaction, key)
        self._validate_record_identity(key, record, current)
        if current is not None and key.collection.endswith("/executions"):
            existing_execution = self._record(current.record, PaperExecution)
            if (
                current.schema_version == schema_version
                and existing_execution.model_dump(mode="python")
                == record.model_dump(mode="python")
            ):
                return cast(VersionedDocument[Record], current)
            raise RepositoryError("execution records are immutable")
        actual_version = None if current is None else current.state_version
        if actual_version != expected_state_version:
            raise VersionConflict(
                f"expected state version {expected_state_version}, found {actual_version}"
            )
        document = VersionedDocument(
            key=key,
            schema_version=schema_version,
            state_version=0 if actual_version is None else actual_version + 1,
            record=record,
        )
        self._store.put_in_transaction(
            transaction, cast(VersionedDocument[BaseModel], document)
        )
        return document

    def _validate_owner_path(self, key: DocumentKey) -> None:
        owner_segment = _segment(str(self._owner.uid))
        allowed = (
            (key.collection == "paper_portfolios" and key.document_id == owner_segment)
            or key.collection.startswith(f"paper_portfolios/{owner_segment}/")
            or key.collection == f"paper_portfolios/{owner_segment}/command_receipts"
            or (key.collection == "users" and key.document_id == owner_segment)
        )
        if not allowed:
            raise RepositoryError("document path is outside the authenticated owner scope")

    @staticmethod
    def _generation_for_key(key: DocumentKey) -> str | None:
        parts = key.collection.split("/")
        try:
            index = parts.index("generations")
        except ValueError:
            return None
        if index + 1 >= len(parts):
            if index == len(parts) - 1:
                return unquote(key.document_id)
            raise RepositoryError("generation collection path is incomplete")
        return unquote(parts[index + 1])

    @staticmethod
    def _validate_record_identity(
        key: DocumentKey,
        record: Record,
        current: VersionedDocument[BaseModel] | None,
    ) -> None:
        if not key.collection.endswith("/executions"):
            return
        if not isinstance(record, PaperExecution):
            raise RepositoryError("execution writes require a PaperExecution record")
        order_id = unquote(key.document_id)
        if record.order_id != order_id or record.execution_id != record.order_id:
            raise RepositoryError("execution identity must equal its order identity")
        if current is not None:
            existing = PaperRepositories._record(current.record, PaperExecution)
            if existing.execution_id != record.execution_id:
                raise RepositoryError("an order cannot receive a second execution identity")

    def _page(
        self,
        collection: str,
        generation: OpaqueIdentifier,
        record_type: type[Record],
        *,
        limit: int,
        cursor: str | None,
        order_by: tuple[tuple[str, Literal["asc", "desc"]], ...],
    ) -> Page[Record]:
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        context = self._active_generation_context(generation)
        result = self._store.page(
            f"paper_portfolios/{_segment(str(self._owner.uid))}/generations/"
            f"{_segment(str(generation))}/{collection}",
            filters=(("generation", "==", str(generation)),),
            order_by=order_by,
            limit=limit,
            cursor=cursor,
            cursor_context=context,
        )
        if context != self._active_generation_context(generation):
            raise GenerationConflict("portfolio changed during history read")
        return Page(tuple(self._record(item, record_type) for item in result.items), result.next_cursor)

    def _active_generation_context(self, generation: OpaqueIdentifier) -> tuple[str, int]:
        control = self.get_control()
        if control is None or control.record.active_generation != generation:
            raise GenerationConflict(f"generation {generation} is not the active portfolio generation")
        return str(generation), control.state_version

    def _read_active(
        self,
        key: DocumentKey,
        generation: OpaqueIdentifier,
        record_type: type[Record],
    ) -> VersionedDocument[Record] | None:
        def read(transaction: Transaction) -> VersionedDocument[Record] | None:
            control = self._store.get_in_transaction(transaction, self.control_key())
            if control is None:
                raise GenerationConflict("cannot read a generation without portfolio control")
            control_record = self._record(control.record, PortfolioControl)
            if control_record.active_generation != generation:
                raise GenerationConflict(
                    f"generation {generation} is not the active portfolio generation"
                )
            return self._typed(self._store.get_in_transaction(transaction, key), record_type)

        return self._store.run(read, max_attempts=MAX_SNAPSHOT_ATTEMPTS)

    @staticmethod
    def _record(value: BaseModel, record_type: type[Record]) -> Record:
        if isinstance(value, record_type):
            return value
        return record_type.model_validate(value.model_dump(mode="python"))

    @classmethod
    def _typed(
        cls, value: VersionedDocument[BaseModel] | None, record_type: type[Record]
    ) -> VersionedDocument[Record] | None:
        if value is None:
            return None
        return VersionedDocument(
            key=value.key,
            schema_version=value.schema_version,
            state_version=value.state_version,
            record=cls._record(value.record, record_type),
        )


class PublicationRepositories:
    """Shared immutable result documents, addressed and paged by batch."""

    def __init__(self, store: TransactionalStore) -> None:
        self._store = store

    @staticmethod
    def result_key(batch_id: OpaqueIdentifier, record_id: OpaqueIdentifier) -> DocumentKey:
        return DocumentKey(
            f"analysis_batches/{_segment(str(batch_id))}/results",
            _segment(str(record_id)),
        )

    def write_result(
        self,
        transaction: Transaction,
        *,
        batch_id: OpaqueIdentifier,
        record_id: OpaqueIdentifier,
        record: Record,
        schema_version: int,
    ) -> VersionedDocument[Record]:
        """Write one immutable result; identical retries are idempotent."""

        if schema_version < 1:
            raise ValueError("schema_version must be positive")
        key = self.result_key(batch_id, record_id)
        current = self._store.get_in_transaction(transaction, key)
        if current is not None:
            if current.schema_version != schema_version or (
                current.record.model_dump(mode="json") != record.model_dump(mode="json")
            ):
                raise RepositoryError("published result IDs are immutable")
            return VersionedDocument(
                key=key,
                schema_version=current.schema_version,
                state_version=current.state_version,
                record=cast(Record, current.record),
            )
        document = VersionedDocument(key, schema_version, 0, record)
        self._store.put_in_transaction(transaction, cast(VersionedDocument[BaseModel], document))
        return document

    def list_results(
        self,
        batch_id: OpaqueIdentifier,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> Page[BaseModel]:
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        result = self._store.page(
            f"analysis_batches/{_segment(str(batch_id))}/results",
            filters=(),
            order_by=(("__name__", "asc"),),
            limit=limit,
            cursor=cursor,
        )
        return result


def consistent_read(
    read: Callable[[], tuple[int, str, T]],
    current_version: Callable[[], tuple[int, str]],
    *,
    max_attempts: int = MAX_SNAPSHOT_ATTEMPTS,
) -> T:
    """Return a read only when its version and generation remain unchanged."""

    if not 1 <= max_attempts <= 10:
        raise ValueError("max_attempts must be between 1 and 10")
    for _ in range(max_attempts):
        before_version, before_generation, result = read()
        after_version, after_generation = current_version()
        if (before_version, before_generation) == (after_version, after_generation):
            return result
    raise SnapshotChanged("portfolio changed during every consistent-read attempt")
