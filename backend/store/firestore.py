"""Small Firestore REST adapter used by local emulator and future SDK adapters."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Literal, cast
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, quote
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from backend.store.repositories import (
    DocumentKey,
    Page,
    TransactionalStore,
    VersionedDocument,
)
from backend.store.transactions import Transaction


class FirestoreConflict(RuntimeError):
    """The Firestore transaction must be retried from a fresh snapshot."""


class _StoredRecord(BaseModel):
    model_config = ConfigDict(extra="allow")


class _RestTransaction:
    def __init__(self, token: str) -> None:
        self.token = token
        self.writes: list[dict[str, Any]] = []


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return {"__tradvisor_datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__tradvisor_date__": value.isoformat()}
    raise TypeError(f"unsupported document value: {type(value).__name__}")


def _restore_json_types(value: object) -> object:
    if isinstance(value, list):
        return [_restore_json_types(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"__tradvisor_datetime__"}:
            return datetime.fromisoformat(str(value["__tradvisor_datetime__"]))
        if set(value) == {"__tradvisor_date__"}:
            return date.fromisoformat(str(value["__tradvisor_date__"]))
        return {str(key): _restore_json_types(item) for key, item in value.items()}
    if isinstance(value, str) and "T" in value and value.endswith("Z"):
        return datetime.fromisoformat(value[:-1] + "+00:00")
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return value


class FirestoreRestStore(TransactionalStore):
    """Firestore document/transaction adapter using only the REST protocol.

    The adapter deliberately reads ``FIRESTORE_EMULATOR_HOST`` by default and
    does not create credentials. Production callers must supply an explicit
    host and project through their authenticated runtime adapter.
    """

    def __init__(self, *, project_id: str | None = None, host: str | None = None) -> None:
        configured_host = host or os.environ.get("FIRESTORE_EMULATOR_HOST")
        if not configured_host:
            raise ValueError("Firestore REST adapter requires an explicit local emulator host")
        if not configured_host.startswith("http://") and not configured_host.startswith("https://"):
            configured_host = f"http://{configured_host}"
        self._root = configured_host.rstrip("/")
        configured_project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "tradvisor-test")
        self._project_id = str(configured_project)
        self._documents_root = (
            f"/v1/projects/{quote(self._project_id, safe='')}/databases/(default)/documents/"
        )

    def run(self, callback: Callable[[Transaction], Any], *, max_attempts: int) -> Any:
        for attempt in range(max_attempts):
            token = self._begin_transaction()
            transaction = _RestTransaction(token)
            try:
                result = callback(transaction)
                self._commit(transaction)
                return result
            except FirestoreConflict:
                if attempt + 1 == max_attempts:
                    raise
        raise FirestoreConflict("transaction retry budget exhausted")

    def get(self, key: DocumentKey) -> VersionedDocument[BaseModel] | None:
        response = self._request("GET", self._document_url(key))
        return self._decode_document(response, key)

    def page(
        self,
        collection: str,
        *,
        filters: tuple[tuple[str, str, str], ...],
        order_by: tuple[tuple[str, Literal["asc", "desc"]], ...],
        limit: int,
        cursor: str | None,
    ) -> Page[BaseModel]:
        query = {"pageSize": str(limit)}
        if cursor is not None:
            query["pageToken"] = cursor
        response = self._request(
            "GET", self._collection_url(collection) + "?" + urlencode(query)
        )
        items = tuple(
            document
            for document in (
                self._decode_document(raw, DocumentKey(collection, raw["name"].rsplit("/", 1)[-1]))
                for raw in response.get("documents", [])
            )
            if document is not None
        )
        return Page(tuple(item.record for item in items), response.get("nextPageToken"))

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        rest_transaction = self._rest_transaction(transaction)
        response = self._request(
            "GET",
            self._document_url(key) + "?" + urlencode({"transaction": rest_transaction.token}),
        )
        return self._decode_document(response, key)

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None:
        rest_transaction = self._rest_transaction(transaction)
        rest_transaction.writes.append({"update": self._encode_document(document)})

    def _begin_transaction(self) -> str:
        response = self._request(
            "POST", urljoin(self._root, self._documents_root.rstrip("/") + ":beginTransaction"), {}
        )
        return cast(str, response["transaction"])

    def _commit(self, transaction: _RestTransaction) -> None:
        self._request(
            "POST",
            urljoin(self._root, self._documents_root.rstrip("/") + ":commit"),
            {"transaction": transaction.token, "writes": transaction.writes},
        )

    def _document_url(self, key: DocumentKey) -> str:
        return urljoin(self._root, self._documents_root + quote(key.path, safe="/"))

    def _collection_url(self, collection: str) -> str:
        return urljoin(self._root, self._documents_root + quote(collection, safe="/"))

    @staticmethod
    def _rest_transaction(transaction: Transaction) -> _RestTransaction:
        if not isinstance(transaction, _RestTransaction):
            raise TypeError("FirestoreRestStore requires its own transaction handle")
        return transaction

    @staticmethod
    def _encode_document(document: VersionedDocument[BaseModel]) -> dict[str, Any]:
        return {
            "name": document.key.path,
            "fields": {
                "schema_version": {"integerValue": str(document.schema_version)},
                "state_version": {"integerValue": str(document.state_version)},
                "record_json": {
                    "stringValue": json.dumps(
                        document.record.model_dump(mode="python"),
                        default=_json_default,
                        sort_keys=True,
                    )
                },
            },
        }

    @staticmethod
    def _decode_document(
        response: dict[str, Any], key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        if not response:
            return None
        fields = response["fields"]
        record = _restore_json_types(json.loads(fields["record_json"]["stringValue"]))
        return VersionedDocument(
            key=key,
            schema_version=int(fields["schema_version"]["integerValue"]),
            state_version=int(fields["state_version"]["integerValue"]),
            record=_StoredRecord.model_validate(record),
        )

    def _request(
        self, method: str, url: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        request = Request(
            url,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=5) as response:
                payload = response.read()
        except HTTPError as error:
            if error.code == 404:
                return {}
            if error.code == 409:
                raise FirestoreConflict("Firestore transaction conflict") from error
            raise
        return {} if not payload else cast(dict[str, Any], json.loads(payload))
