from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.store.firestore_sdk import FirestoreSdkStore
from backend.store.repositories import DocumentKey, VersionedDocument


class Record(BaseModel):
    generation: str
    value: int


class _Snapshot:
    exists = True

    def __init__(self, fields: dict[str, Any]) -> None:
        self._fields = fields

    def to_dict(self) -> dict[str, Any]:
        return self._fields


class _Reference:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeTransaction:
    def __init__(self, snapshots: tuple[_Snapshot, ...]) -> None:
        self.snapshots = snapshots
        self.requested: list[_Reference] = []
        self.events: list[str] = []
        self.writes: list[tuple[_Reference, dict[str, Any]]] = []

    def get(self, reference: _Reference) -> Iterator[_Snapshot]:
        self.requested.append(reference)
        self.events.append(f"read:{reference.path}")
        return iter(self.snapshots)

    def set(self, reference: _Reference, value: dict[str, Any]) -> None:
        self.events.append(f"write:{reference.path}")
        self.writes.append((reference, value))


class _FakeClient:
    def __init__(self, records: list["_Document"] | None = None) -> None:
        self.records = [] if records is None else records
        self.query = _FakeQuery(self.records)

    def document(self, path: str) -> _Reference:
        return _Reference(path)

    def collection(self, collection: str) -> "_FakeQuery":
        assert collection == "analysis_batches/b1/results"
        return self.query


class _Document:
    def __init__(self, document_id: str, value: int) -> None:
        self.id = document_id
        self.reference = _Reference(f"analysis_batches/b1/results/{document_id}")
        self._fields = {
            "_schema_version": 1,
            "_document_state_version": 0,
            "generation": "b1",
            "value": value,
        }

    @property
    def exists(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return self._fields


class _FakeQuery:
    def __init__(self, records: list[_Document]) -> None:
        self.records = records
        self.requested_limit: int | None = None
        self.start_after_values: object | None = None

    def where(self, **kwargs: object) -> "_FakeQuery":
        return self

    def order_by(self, *args: object, **kwargs: object) -> "_FakeQuery":
        return self

    def start_after(self, *args: object, **kwargs: object) -> "_FakeQuery":
        self.start_after_values = args[0] if args else None
        return self

    def limit(self, value: int) -> "_FakeQuery":
        self.requested_limit = value
        return self

    def stream(self) -> Iterator[_Document]:
        return iter(self.records[: self.requested_limit])


def test_sdk_transactional_read_consumes_snapshot_iterator() -> None:
    key = DocumentKey("paper_portfolios/u/generations/g1/orders", "order-1")
    transaction = _FakeTransaction(
        (
            _Snapshot(
                {
                    "_schema_version": 1,
                    "_document_state_version": 2,
                    "generation": "g1",
                    "value": 7,
                }
            ),
        )
    )
    store = FirestoreSdkStore(
        project_id="local-project", cursor_secret="local-test-cursor-secret", client=_FakeClient()
    )

    result = store.get_in_transaction(transaction, key)

    assert result is not None
    assert result.key == key
    assert result.state_version == 2
    assert result.record.model_dump() == {"generation": "g1", "value": 7}
    assert transaction.requested[0].path == key.path


def test_sdk_transactional_read_returns_none_for_empty_snapshot_iterator() -> None:
    key = DocumentKey("paper_portfolios/u/generations/g1/orders", "missing")
    transaction = _FakeTransaction(())
    store = FirestoreSdkStore(
        project_id="local-project", cursor_secret="local-test-cursor-secret", client=_FakeClient()
    )

    assert store.get_in_transaction(transaction, key) is None


def test_sdk_fake_multi_record_transaction_reads_before_writes() -> None:
    first_key = DocumentKey("paper_portfolios/u/generations/g1/orders", "order-1")
    second_key = DocumentKey("paper_portfolios/u/generations/g1/positions", "ABC")
    snapshot = _Snapshot(
        {
            "_schema_version": 1,
            "_document_state_version": 0,
            "generation": "g1",
            "value": 7,
        }
    )
    transaction = _FakeTransaction((snapshot,))
    store = FirestoreSdkStore(
        project_id="local-project", cursor_secret="local-test-cursor-secret", client=_FakeClient()
    )

    assert store.get_in_transaction(transaction, first_key) is not None
    assert store.get_in_transaction(transaction, second_key) is not None
    store.put_in_transaction(
        transaction,
        VersionedDocument(first_key, 1, 1, Record(generation="g1", value=8)),
    )
    store.put_in_transaction(
        transaction,
        VersionedDocument(second_key, 1, 1, Record(generation="g1", value=9)),
    )

    assert [event.split(":", 1)[0] for event in transaction.events] == [
        "read",
        "read",
        "write",
        "write",
    ]


def test_sdk_server_timestamp_uses_firestore_transform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    monkeypatch.setattr(
        "backend.store.firestore_sdk.importlib.import_module",
        lambda name: SimpleNamespace(SERVER_TIMESTAMP=sentinel),
    )
    store = FirestoreSdkStore(
        project_id="local-project", cursor_secret="local-test-cursor-secret", client=_FakeClient()
    )
    transaction = _FakeTransaction(())
    key = DocumentKey("execution_price_revisions", "revision-1")
    record = Record(generation="source", value=7)

    store.put_with_server_timestamps_in_transaction(
        transaction,
        VersionedDocument(key, 1, 0, record),
        fields=("value",),
    )

    assert transaction.writes[0][0].path == key.path
    assert transaction.writes[0][1]["value"] is sentinel


def test_sdk_pager_fetches_one_extra_and_omits_cursor_on_final_exact_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [_Document("a", 1), _Document("b", 2)]
    client = _FakeClient(records)
    fake_firestore = SimpleNamespace(
        FieldPath=SimpleNamespace(document_id=lambda: "__name__"),
        Query=SimpleNamespace(ASCENDING="ASCENDING", DESCENDING="DESCENDING"),
    )
    monkeypatch.setattr(
        "backend.store.firestore_sdk.importlib.import_module",
        lambda name: fake_firestore,
    )
    store = FirestoreSdkStore(
        project_id="local-project", cursor_secret="local-test-cursor-secret", client=client
    )

    page = store.page(
        "analysis_batches/b1/results",
        filters=(),
        order_by=(("value", "asc"),),
        limit=2,
        cursor=None,
    )

    assert client.query.requested_limit == 3
    assert len(page.items) == 2
    assert page.keys == (
        DocumentKey("analysis_batches/b1/results", "a"),
        DocumentKey("analysis_batches/b1/results", "b"),
    )
    assert page.next_cursor is None


def test_sdk_pager_uses_start_after_for_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient([_Document("a", 1), _Document("b", 2), _Document("c", 3)])
    fake_firestore = SimpleNamespace(
        FieldPath=SimpleNamespace(document_id=lambda: "__name__"),
        Query=SimpleNamespace(ASCENDING="ASCENDING", DESCENDING="DESCENDING"),
    )
    monkeypatch.setattr(
        "backend.store.firestore_sdk.importlib.import_module",
        lambda name: fake_firestore,
    )
    store = FirestoreSdkStore(
        project_id="local-project", cursor_secret="local-test-cursor-secret", client=client
    )
    first = store.page(
        "analysis_batches/b1/results",
        filters=(),
        order_by=(("value", "asc"),),
        limit=2,
        cursor=None,
    )
    assert first.next_cursor is not None

    store.page(
        "analysis_batches/b1/results",
        filters=(),
        order_by=(("value", "asc"),),
        limit=2,
        cursor=first.next_cursor,
    )

    assert client.query.start_after_values is not None
