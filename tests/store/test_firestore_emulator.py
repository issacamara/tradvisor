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


@pytest.fixture
def firestore_emulator() -> Iterator[str]:
    state = _LocalFirestoreState()
    _FirestoreEmulatorHandler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FirestoreEmulatorHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_firestore_rest_adapter_retries_reset_write_race(
    firestore_emulator: str,
) -> None:
    first_store = FirestoreRestStore(host=firestore_emulator)
    reset_store = FirestoreRestStore(host=firestore_emulator)
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
