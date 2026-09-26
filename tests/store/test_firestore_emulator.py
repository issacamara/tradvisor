from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any, cast
from urllib.parse import parse_qs, unquote
from uuid import uuid4

import pytest
from pydantic import BaseModel

from backend.store.firestore import FirestoreRestStore
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
        host=emulator_host, project_id="local-project", database_id="local-db"
    )
    reset_store = FirestoreRestStore(
        host=emulator_host, project_id="local-project", database_id="local-db"
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
        host=emulator_host, project_id="local-project", database_id="local-db"
    )
    collection = "paper_portfolios/verified-user/generations/g1/orders"
    documents = (
        ("order-a", "g1", 1),
        ("order-b", "g1", 2),
        ("order-c", "g2", 3),
    )

    def seed(transaction: Transaction) -> None:
        for order_id, generation, value in documents:
            store.put_in_transaction(
                transaction,
                VersionedDocument(
                    key=DocumentKey(collection, order_id),
                    schema_version=1,
                    state_version=0,
                    record=Record(generation=generation, value=value),
                ),
            )

    store.run(seed, max_attempts=1)
    page = store.page(
        collection,
        filters=(("generation", "==", "g1"),),
        order_by=(("value", "desc"), ("generation", "asc")),
        limit=10,
        cursor=None,
    )

    assert [Record.model_validate(item.model_dump()).value for item in page.items] == [2, 1]
    query = state.query_requests[0]
    assert query["parent"] == (
        "projects/local-project/databases/local-db/documents/"
        "paper_portfolios/verified-user/generations/g1"
    )
    structured = cast(dict[str, Any], query["structuredQuery"])
    assert structured["where"]["compositeFilter"]["filters"][0]["fieldFilter"]["field"] == {
        "fieldPath": "generation"
    }
    assert structured["orderBy"] == [
        {"field": {"fieldPath": "value"}, "direction": "DESCENDING"},
        {"field": {"fieldPath": "generation"}, "direction": "ASCENDING"},
    ]
