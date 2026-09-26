from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any, cast
from urllib.parse import parse_qs, unquote
from uuid import uuid4

import pytest
from pydantic import BaseModel

from backend.store.firestore import CursorError, FirestoreRestStore, SnapshotExpired
from backend.contracts.paper import PortfolioControl
from backend.store.repositories import (
    DocumentKey,
    GenerationConflict,
    OwnerContext,
    PaperRepositories,
    VersionedDocument,
)
from backend.store.transactions import Transaction
from backend.contracts.scalars import OpaqueIdentifier


class Record(BaseModel):
    generation: str
    value: int


class HistoryRecord(BaseModel):
    generation: str
    status: str
    accepted_at: datetime
    order_id: str


class TimestampRecord(BaseModel):
    value: int
    committed_at: datetime | None


TEST_CURSOR_SECRET = "local-test-cursor-secret"


def _control(generation: str | None) -> PortfolioControl:
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


class _LocalFirestoreState:
    def __init__(self) -> None:
        self.documents: dict[str, tuple[int, dict[str, object]]] = {}
        self.transactions: dict[str, dict[str, int]] = {}
        self.query_requests: list[dict[str, Any]] = []
        self.commit_time = datetime(2026, 9, 26, 12, 34, 56, tzinfo=timezone.utc)
        self.lock = Lock()


class _FirestoreEmulatorHandler(BaseHTTPRequestHandler):
    state: _LocalFirestoreState

    def do_POST(self) -> None:  # noqa: N802
        if self.path.endswith(":beginTransaction"):
            token = uuid4().hex
            with self.state.lock:
                self.state.transactions[token] = {}
            self._respond(200, {"transaction": token})
            return
        if self.path.endswith(":commit"):
            body = self._body()
            token = str(body["transaction"])
            with self.state.lock:
                reads = self.state.transactions.pop(token, {})
                if any(self.state.documents.get(path, (0, {}))[0] != version for path, version in reads.items()):
                    self._respond(409, {})
                    return
                for write in cast(list[dict[str, Any]], body.get("writes", [])):
                    document = write["update"]
                    path = unquote(document["name"].split("/documents/", 1)[-1])
                    fields = cast(dict[str, dict[str, Any]], document["fields"])
                    for transform in cast(list[dict[str, str]], write.get("updateTransforms", [])):
                        assert transform["setToServerValue"] == "REQUEST_TIME"
                        fields[transform["fieldPath"]] = {
                            "timestampValue": self.state.commit_time.isoformat().replace("+00:00", "Z")
                        }
                    version = self.state.documents.get(path, (0, {}))[0] + 1
                    self.state.documents[path] = (version, document)
            self._respond(200, {})
            return
        if self.path.endswith(":runQuery"):
            body = self._body()
            query = cast(dict[str, Any], body["structuredQuery"])
            parent = str(body["parent"]).split("/documents/", 1)[1]
            collection_id = str(query["from"][0]["collectionId"])
            with self.state.lock:
                self.state.query_requests.append(body)
                candidates = [
                    document
                    for path, (_, document) in self.state.documents.items()
                    if path.startswith(f"{parent}/{collection_id}/")
                ]
                candidates = [
                    document
                    for document in candidates
                    if self._matches_filters(document, query.get("where"))
                ]
                for ordering in reversed(query.get("orderBy", [])):
                    field = str(ordering["field"]["fieldPath"])
                    candidates.sort(
                        key=lambda document: self._field_value(document, field),
                        reverse=ordering["direction"] == "DESCENDING",
                    )
                start_at = query.get("startAt")
                if start_at is not None:
                    start_values = [
                        self._field_value({"fields": {"value": value}}, "value")
                        for value in start_at["values"]
                    ]
                    orderings = query.get("orderBy", [])
                    candidates = [
                        document
                        for document in candidates
                        if self._is_after(document, start_values, orderings)
                    ]
                candidates = candidates[: int(query["limit"])]
            self._respond_list(200, [{"document": document} for document in candidates])
            return
        self._respond(404, {})

    def do_GET(self) -> None:  # noqa: N802
        path, _, query = self.path.partition("?")
        if "/documents/" not in path:
            self._respond(404, {})
            return
        document_path = unquote(path.split("/documents/", 1)[1])
        params = parse_qs(query)
        transaction = params.get("transaction", [None])[0]
        with self.state.lock:
            stored = self.state.documents.get(document_path)
            if transaction is not None:
                reads = self.state.transactions[transaction]
                reads.setdefault(document_path, 0 if stored is None else stored[0])
            if stored is None:
                self._respond(404, {})
                return
            self._respond(200, stored[1])

    def log_message(self, format: str, *args: object) -> None:
        return

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return cast(dict[str, Any], json.loads(self.rfile.read(length)))

    def _respond(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _respond_list(self, status: int, body: list[dict[str, object]]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    @staticmethod
    def _field_value(document: dict[str, object], field: str) -> str | int:
        if field == "__name__":
            return str(document["name"])
        fields = cast(dict[str, dict[str, object]], document["fields"])
        value = fields[field]
        if "integerValue" in value:
            return int(str(value["integerValue"]))
        return str(next(iter(value.values())))

    @classmethod
    def _matches_filters(
        cls, document: dict[str, object], where: dict[str, object] | None
    ) -> bool:
        if where is None:
            return True
        composite = cast(dict[str, object], where["compositeFilter"])
        filters = cast(list[dict[str, object]], composite["filters"])
        for item in filters:
            field_filter = cast(dict[str, object], item["fieldFilter"])
            field = str(cast(dict[str, object], field_filter["field"])["fieldPath"])
            actual = cls._field_value(document, field)
            expected = cls._field_value({"fields": {"value": field_filter["value"]}}, "value")
            if field_filter["op"] == "EQUAL" and actual != expected:
                return False
        return True

    @classmethod
    def _is_after(
        cls,
        document: dict[str, object],
        start_values: list[str | int],
        orderings: list[dict[str, Any]],
    ) -> bool:
        for index, ordering in enumerate(orderings):
            actual = cls._field_value(document, str(ordering["field"]["fieldPath"]))
            expected = start_values[index]
            if actual == expected:
                continue
            descending = ordering["direction"] == "DESCENDING"
            if isinstance(actual, str) and isinstance(expected, str):
                return actual < expected if descending else actual > expected
            if isinstance(actual, int) and isinstance(expected, int):
                return actual < expected if descending else actual > expected
            return False
        return False


@pytest.fixture
def firestore_emulator() -> Iterator[tuple[str, _LocalFirestoreState]]:
    state = _LocalFirestoreState()
    _FirestoreEmulatorHandler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FirestoreEmulatorHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_firestore_rest_adapter_retries_reset_write_race(
    firestore_emulator: tuple[str, _LocalFirestoreState],
) -> None:
    emulator_host, state = firestore_emulator
    first_store = FirestoreRestStore(
        host=emulator_host, project_id="local-project", database_id="local-db",
        cursor_secret=TEST_CURSOR_SECRET,
    )
    reset_store = FirestoreRestStore(
        host=emulator_host, project_id="local-project", database_id="local-db",
        cursor_secret=TEST_CURSOR_SECRET,
    )
    owner = OwnerContext(uid=OpaqueIdentifier("verified-user"))
    first = PaperRepositories(first_store, owner)
    reset = PaperRepositories(reset_store, owner)
    control_key = first.control_key()
    generation_key = first.generation_key(OpaqueIdentifier("g1"))

    first_store.run(
        lambda transaction: first.write_in_transaction(
            transaction,
            key=control_key,
            record=_control("g1"),
            schema_version=1,
            expected_state_version=None,
        ),
        max_attempts=3,
    )
    attempts = 0

    def stale_write(transaction: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        first.write_in_transaction(
            transaction,
            key=generation_key,
            record=Record(generation="g1", value=1),
            schema_version=1,
            expected_state_version=None,
        )
        if attempts == 1:
            reset.transact(
                lambda reset_transaction: reset.write_in_transaction(
                    reset_transaction,
                    key=control_key,
                    record=_control("g2"),
                    schema_version=1,
                    expected_state_version=0,
                )
            )

    with pytest.raises(GenerationConflict, match="not the active"):
        first.transact(stale_write)

    assert attempts == 2
    assert first_store.get(generation_key) is None
    assert state.documents["paper_portfolios/verified-user"][1]["name"] == (
        "projects/local-project/databases/local-db/documents/paper_portfolios/verified-user"
    )


def test_firestore_rest_adapter_queries_indexed_fields_and_preserves_order(
    firestore_emulator: tuple[str, _LocalFirestoreState],
) -> None:
    emulator_host, state = firestore_emulator
    store = FirestoreRestStore(
        host=emulator_host, project_id="local-project", database_id="local-db",
        cursor_secret=TEST_CURSOR_SECRET,
    )
    collection = "paper_portfolios/verified-user/generations/g1/orders"
    documents = (
        ("order-a", "g1", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("order-b", "g1", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("order-c", "g1", datetime(2025, 12, 1, tzinfo=timezone.utc)),
        ("order-d", "g1", datetime(2025, 11, 1, tzinfo=timezone.utc)),
    )

    def seed(transaction: Transaction) -> None:
        for order_id, generation, accepted_at in documents:
            store.put_in_transaction(
                transaction,
                VersionedDocument(
                    key=DocumentKey(collection, order_id),
                    schema_version=1,
                    state_version=0,
                    record=HistoryRecord(
                        generation=generation,
                        status="pending",
                        accepted_at=accepted_at,
                        order_id=order_id,
                    ),
                ),
            )

    store.run(seed, max_attempts=1)
    page = store.page(
        collection,
        filters=(("generation", "==", "g1"), ("status", "==", "pending")),
        order_by=(("accepted_at", "desc"), ("order_id", "desc")),
        limit=2,
        cursor=None,
    )

    assert [HistoryRecord.model_validate(item.model_dump()).order_id for item in page.items] == [
        "order-b",
        "order-a",
    ]
    assert page.next_cursor is not None
    assert page.keys == (
        DocumentKey(collection, "order-b"),
        DocumentKey(collection, "order-a"),
    )
    continuation = store.page(
        collection,
        filters=(("generation", "==", "g1"), ("status", "==", "pending")),
        order_by=(("accepted_at", "desc"), ("order_id", "desc")),
        limit=2,
        cursor=page.next_cursor,
    )
    assert [HistoryRecord.model_validate(item.model_dump()).order_id for item in continuation.items] == [
        "order-c",
        "order-d",
    ]
    assert continuation.next_cursor is None
    query = state.query_requests[0]
    assert query["parent"] == (
        "projects/local-project/databases/local-db/documents/"
        "paper_portfolios/verified-user/generations/g1"
    )
    structured = cast(dict[str, Any], query["structuredQuery"])
    assert structured["where"]["compositeFilter"]["filters"][0]["fieldFilter"]["field"] == {
        "fieldPath": "generation"
    }
    assert structured["where"]["compositeFilter"]["filters"][1]["fieldFilter"]["field"] == {
        "fieldPath": "status"
    }
    assert structured["limit"] == 3
    assert structured["orderBy"] == [
        {"field": {"fieldPath": "accepted_at"}, "direction": "DESCENDING"},
        {"field": {"fieldPath": "order_id"}, "direction": "DESCENDING"},
    ]
    continuation_query = state.query_requests[1]["structuredQuery"]
    assert continuation_query["startAt"]["before"] is False
    assert len(continuation_query["startAt"]["values"]) == 2


def test_firestore_rest_adapter_publication_name_cursor_uses_reference_value(
    firestore_emulator: tuple[str, _LocalFirestoreState],
) -> None:
    emulator_host, state = firestore_emulator
    store = FirestoreRestStore(
        host=emulator_host, project_id="local-project", database_id="local-db",
        cursor_secret=TEST_CURSOR_SECRET,
    )
    collection = "analysis_batches/b1/results"

    def seed(transaction: Transaction) -> None:
        for record_id, value in (("a", 1), ("b", 2)):
            store.put_in_transaction(
                transaction,
                VersionedDocument(
                    key=DocumentKey(collection, record_id),
                    schema_version=1,
                    state_version=0,
                    record=Record(generation="b1", value=value),
                ),
            )

    store.run(seed, max_attempts=1)
    first = store.page(
        collection,
        filters=(),
        order_by=(("__name__", "asc"),),
        limit=1,
        cursor=None,
    )
    assert first.next_cursor is not None
    second = store.page(
        collection,
        filters=(),
        order_by=(("__name__", "asc"),),
        limit=1,
        cursor=first.next_cursor,
    )
    assert [Record.model_validate(item.model_dump()).value for item in second.items] == [2]
    cursor_value = state.query_requests[1]["structuredQuery"]["startAt"]["values"][0]
    assert cursor_value == {
        "referenceValue": "projects/local-project/databases/local-db/documents/"
        "analysis_batches/b1/results/a"
    }


def test_firestore_rest_adapter_rejects_cursor_after_state_change(
    firestore_emulator: tuple[str, _LocalFirestoreState],
) -> None:
    emulator_host, _ = firestore_emulator
    store = FirestoreRestStore(
        host=emulator_host, project_id="local-project", database_id="local-db",
        cursor_secret=TEST_CURSOR_SECRET,
    )
    reset_store = FirestoreRestStore(
        host=emulator_host, project_id="local-project", database_id="local-db",
        cursor_secret=TEST_CURSOR_SECRET,
    )
    collection = "paper_portfolios/verified-user/generations/g1/orders"

    def seed(transaction: Transaction) -> None:
        for order_id, value in (("a", 1), ("b", 2)):
            store.put_in_transaction(
                transaction,
                VersionedDocument(
                    key=DocumentKey(collection, order_id),
                    schema_version=1,
                    state_version=0,
                    record=Record(generation="g1", value=value),
                ),
            )

    store.run(seed, max_attempts=1)
    first = store.page(
        collection,
        filters=(("generation", "==", "g1"),),
        order_by=(("value", "desc"), ("generation", "asc")),
        limit=1,
        cursor=None,
        cursor_context=("g1", 0),
    )
    assert first.next_cursor is not None
    reset_store.run(
        lambda transaction: reset_store.put_in_transaction(
            transaction,
            VersionedDocument(
                key=DocumentKey("paper_portfolios", "verified-user"),
                schema_version=1,
                state_version=1,
                record=_control("g1"),
            ),
        ),
        max_attempts=1,
    )
    with pytest.raises(CursorError, match="malformed"):
        store.page(
            collection,
            filters=(("generation", "==", "g1"),),
            order_by=(("value", "desc"), ("generation", "asc")),
            limit=1,
            cursor=first.next_cursor,
            cursor_context=("g1", 1),
        )


def test_firestore_rest_adapter_rejects_malformed_cursor(
    firestore_emulator: tuple[str, _LocalFirestoreState],
) -> None:
    emulator_host, _ = firestore_emulator
    store = FirestoreRestStore(host=emulator_host, cursor_secret=TEST_CURSOR_SECRET)
    with pytest.raises(CursorError, match="malformed"):
        store.page(
            "paper_portfolios/u/generations/g1/orders",
            filters=(("generation", "==", "g1"),),
            order_by=(("accepted_at", "desc"), ("order_id", "desc")),
            limit=2,
            cursor="definitely-not-a-cursor",
        )


def test_firestore_rest_adapter_expires_cursor_after_24_hours(
    firestore_emulator: tuple[str, _LocalFirestoreState],
) -> None:
    emulator_host, _ = firestore_emulator
    current_time = [datetime(2026, 9, 26, tzinfo=timezone.utc)]
    store = FirestoreRestStore(
        host=emulator_host,
        cursor_secret=TEST_CURSOR_SECRET,
        clock=lambda: current_time[0],
        project_id="local-project",
        database_id="local-db",
    )
    collection = "analysis_batches/b1/results"

    def seed(transaction: Transaction) -> None:
        for record_id in ("a", "b"):
            store.put_in_transaction(
                transaction,
                VersionedDocument(
                    key=DocumentKey(collection, record_id),
                    schema_version=1,
                    state_version=0,
                    record=Record(generation="b1", value=1),
                ),
            )

    store.run(seed, max_attempts=1)
    first = store.page(
        collection,
        filters=(),
        order_by=(("__name__", "asc"),),
        limit=1,
        cursor=None,
    )
    assert first.next_cursor is not None
    for field, value in (
        ("issued_at", "2026-09-26T01:00:00Z"),
        ("expiry_at", "2026-09-27T01:00:00Z"),
    ):
        payload = json.loads(base64.urlsafe_b64decode(first.next_cursor + "===").decode("utf-8"))
        payload[field] = value
        tampered = base64.urlsafe_b64encode(
            json.dumps(payload).encode("utf-8")
        ).rstrip(b"=").decode()
        with pytest.raises(CursorError, match="malformed"):
            store.page(
                collection,
                filters=(),
                order_by=(("__name__", "asc"),),
                limit=1,
                cursor=tampered,
            )
    current_time[0] += timedelta(hours=24)
    with pytest.raises(SnapshotExpired, match="snapshot_expired"):
        store.page(
            collection,
            filters=(),
            order_by=(("__name__", "asc"),),
            limit=1,
            cursor=first.next_cursor,
        )


def test_firestore_rest_server_timestamp_is_resolved_at_commit(
    firestore_emulator: tuple[str, _LocalFirestoreState],
) -> None:
    emulator_host, state = firestore_emulator
    store = FirestoreRestStore(host=emulator_host, cursor_secret=TEST_CURSOR_SECRET)
    key = DocumentKey("execution_price_revisions", "revision-1")
    placeholder = datetime(2000, 1, 1, tzinfo=timezone.utc)

    store.run(
        lambda transaction: store.put_with_server_timestamps_in_transaction(
            transaction,
            VersionedDocument(
                key,
                1,
                0,
                TimestampRecord(value=7, committed_at=placeholder),
            ),
            fields=("committed_at",),
        ),
        max_attempts=1,
    )

    stored = store.get(key)
    assert stored is not None
    assert stored.record.model_dump()["committed_at"] == state.commit_time
    assert stored.record.model_dump()["committed_at"] != placeholder


def test_history_composite_index_matches_repository_query() -> None:
    index_file = Path(__file__).parents[2] / "firestore.indexes.json"
    declaration = json.loads(index_file.read_text())
    assert declaration["indexes"] == [
        {
            "collectionGroup": "orders",
            "queryScope": "COLLECTION",
            "fields": [
                {"fieldPath": "generation", "order": "ASCENDING"},
                {"fieldPath": "accepted_at", "order": "DESCENDING"},
                {"fieldPath": "order_id", "order": "DESCENDING"},
            ],
        },
        {
            "collectionGroup": "orders",
            "queryScope": "COLLECTION",
            "fields": [
                {"fieldPath": "generation", "order": "ASCENDING"},
                {"fieldPath": "status", "order": "ASCENDING"},
                {"fieldPath": "accepted_at", "order": "DESCENDING"},
                {"fieldPath": "order_id", "order": "DESCENDING"},
            ],
        },
        {
            "collectionGroup": "executions",
            "queryScope": "COLLECTION",
            "fields": [
                {"fieldPath": "generation", "order": "ASCENDING"},
                {"fieldPath": "processed_at", "order": "DESCENDING"},
                {"fieldPath": "order_id", "order": "DESCENDING"},
            ],
        },
        {
            "collectionGroup": "cash_movements",
            "queryScope": "COLLECTION",
            "fields": [
                {"fieldPath": "generation", "order": "ASCENDING"},
                {"fieldPath": "occurred_at", "order": "DESCENDING"},
                {"fieldPath": "movement_id", "order": "DESCENDING"},
            ],
        },
    ]
