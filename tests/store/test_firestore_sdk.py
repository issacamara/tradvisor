from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.store.firestore_sdk import FirestoreSdkStore
from backend.store.repositories import DocumentKey


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

    def get(self, reference: _Reference) -> Iterator[_Snapshot]:
        self.requested.append(reference)
        return iter(self.snapshots)

    def set(self, reference: _Reference, value: dict[str, Any]) -> None:
        raise AssertionError(f"unexpected write to {reference.path}: {value}")


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

    def where(self, **kwargs: object) -> "_FakeQuery":
        return self

    def order_by(self, *args: object, **kwargs: object) -> "_FakeQuery":
        return self

    def start_at(self, *args: object, **kwargs: object) -> "_FakeQuery":
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
    store = FirestoreSdkStore(project_id="local-project", client=_FakeClient())

    result = store.get_in_transaction(transaction, key)

    assert result is not None
    assert result.key == key
    assert result.state_version == 2
    assert result.record.model_dump() == {"generation": "g1", "value": 7}
    assert transaction.requested[0].path == key.path


def test_sdk_transactional_read_returns_none_for_empty_snapshot_iterator() -> None:
    key = DocumentKey("paper_portfolios/u/generations/g1/orders", "missing")
    transaction = _FakeTransaction(())
    store = FirestoreSdkStore(project_id="local-project", client=_FakeClient())

    assert store.get_in_transaction(transaction, key) is None


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
    store = FirestoreSdkStore(project_id="local-project", client=client)

    page = store.page(
        "analysis_batches/b1/results",
        filters=(),
        order_by=(("value", "asc"),),
        limit=2,
        cursor=None,
    )

    assert client.query.requested_limit == 3
    assert len(page.items) == 2
    assert page.next_cursor is None
