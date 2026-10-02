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
    keys: tuple[DocumentKey, ...] = ()


@dataclass(frozen=True, slots=True)
class WriteRequest:
    """One validated mutation request in a read-before-write transaction plan."""

    key: DocumentKey
    record: BaseModel
    schema_version: int
    expected_state_version: int | None


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
