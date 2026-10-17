"""Small Firestore REST adapter used by the local emulator and SDK adapters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, cast
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict

from backend.store.repositories import DocumentKey, Page, TransactionalStore, VersionedDocument
from backend.store.transactions import Transaction


class FirestoreConflict(RuntimeError):
    """The Firestore transaction must be retried from a fresh snapshot."""


class CursorError(ValueError):
    """A continuation cursor is malformed or does not match this query."""


class SnapshotExpired(CursorError):
    """A continuation cursor is older than the retained snapshot window."""


class _StoredRecord(BaseModel):
    model_config = ConfigDict(extra="allow")


class _RestTransaction:
    def __init__(self, token: str) -> None:
        self.token = token
        self.writes: list[dict[str, Any]] = []


def _firestore_value(value: object) -> dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, datetime):
        return {"timestampValue": value.isoformat().replace("+00:00", "Z")}
    if isinstance(value, date):
        return {"stringValue": value.isoformat()}
    if isinstance(value, str):
        if "T" in value and value.endswith("Z"):
            return {"timestampValue": value}
        return {"stringValue": value}
    if isinstance(value, Mapping):
        return {
            "mapValue": {
                "fields": {str(key): _firestore_value(item) for key, item in value.items()}
            }
        }
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_firestore_value(item) for item in value]}}
    raise TypeError(f"unsupported document value: {type(value).__name__}")


def _python_value(value: Mapping[str, Any]) -> object:
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        timestamp = str(value["timestampValue"])
        return datetime.fromisoformat(
            timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
        )
    if "stringValue" in value:
        return value["stringValue"]
    if "referenceValue" in value:
        return value["referenceValue"]
    if "arrayValue" in value:
        return [_python_value(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {key: _python_value(item) for key, item in value["mapValue"].get("fields", {}).items()}
    raise ValueError("unsupported Firestore value")


def _encode_cursor(
    collection: str,
    filters: tuple[tuple[str, str, str], ...],
    order_by: tuple[tuple[str, Literal["asc", "desc"]], ...],
    values: list[dict[str, Any]],
    cursor_context: tuple[str, int] | None,
    now: datetime,
    secret: str,
) -> str:
    issued_at = now.astimezone(timezone.utc)
    expiry_at = issued_at + timedelta(hours=24)
    payload = {
        "v": 1,
        "collection": collection,
        "filters": [list(item) for item in filters],
        "order_by": [list(item) for item in order_by],
        "values": values,
        "context": None if cursor_context is None else list(cursor_context),
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expiry_at": expiry_at.isoformat().replace("+00:00", "Z"),
    }
    payload["signature"] = _cursor_signature(payload, secret)
    encoded = base64.urlsafe_b64encode(_cursor_json(payload)).rstrip(b"=").decode("ascii")
    if len(encoded) > 2048:
        raise CursorError("continuation cursor exceeds the maximum length")
    return encoded


def _decode_cursor(
    cursor: str,
    collection: str,
    filters: tuple[tuple[str, str, str], ...],
    order_by: tuple[tuple[str, Literal["asc", "desc"]], ...],
    cursor_context: tuple[str, int] | None,
    now: datetime,
    secret: str,
) -> list[dict[str, Any]]:
    try:
        if not cursor or len(cursor) > 2048:
            raise ValueError
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw)
        expected_filters = [list(item) for item in filters]
        expected_order = [list(item) for item in order_by]
        if (
            not isinstance(payload, dict)
            or payload.get("v") != 1
            or payload.get("collection") != collection
            or payload.get("filters") != expected_filters
            or payload.get("order_by") != expected_order
            or payload.get("context")
            != (None if cursor_context is None else list(cursor_context))
            or not isinstance(payload.get("issued_at"), str)
            or not isinstance(payload.get("expiry_at"), str)
            or not isinstance(payload.get("values"), list)
            or not isinstance(payload.get("signature"), str)
            or len(payload["values"]) != len(order_by)
        ):
            raise ValueError
        supplied_signature = str(payload["signature"])
        unsigned_payload = {key: value for key, value in payload.items() if key != "signature"}
        if not hmac.compare_digest(supplied_signature, _cursor_signature(unsigned_payload, secret)):
            raise ValueError
        values = payload["values"]
        issued_at = _parse_cursor_time(payload["issued_at"])
        expiry_at = _parse_cursor_time(payload["expiry_at"])
        current_time = now.astimezone(timezone.utc)
        if issued_at > current_time or expiry_at != issued_at + timedelta(hours=24):
            raise ValueError
        if current_time >= expiry_at:
            raise SnapshotExpired("snapshot_expired")
        for value in values:
            if not isinstance(value, dict) or len(value) != 1:
                raise ValueError
            _python_value(value)
        return cast(list[dict[str, Any]], values)
    except SnapshotExpired:
        raise
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise CursorError("malformed continuation cursor") from error


def _parse_cursor_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.astimezone(timezone.utc)


def _cursor_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _cursor_signature(payload: dict[str, Any], secret: str) -> str:
    if not secret:
        raise ValueError("cursor signing secret must not be empty")
    digest = hmac.new(secret.encode("utf-8"), _cursor_json(payload), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class FirestoreRestStore(TransactionalStore):
    """Firestore document/transaction adapter using the REST protocol."""

    def __init__(
        self,
        *,
        project_id: str | None = None,
        database_id: str | None = None,
        host: str | None = None,
        clock: Callable[[], datetime] | None = None,
        cursor_secret: str | None = None,
    ) -> None:
        configured_host = host or os.environ.get("FIRESTORE_EMULATOR_HOST")
        if not configured_host:
            raise ValueError("Firestore REST adapter requires an explicit local emulator host")
        if not configured_host.startswith(("http://", "https://")):
            configured_host = f"http://{configured_host}"
        self._root = configured_host.rstrip("/")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        configured_cursor_secret = cursor_secret or os.environ.get("FIRESTORE_CURSOR_SECRET")
        if not configured_cursor_secret:
            raise ValueError("Firestore REST adapter requires a cursor signing secret")
        self._cursor_secret = configured_cursor_secret
        self._project_id = str(project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "tradvisor-test"))
        self._database_id = str(
            database_id or os.environ.get("GOOGLE_CLOUD_FIRESTORE_DATABASE", "(default)")
        )
        self._documents_root = (
            f"/v1/projects/{quote(self._project_id, safe='')}/databases/"
            f"{quote(self._database_id, safe='()')}/documents/"
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
        return self._decode_document(self._request("GET", self._document_url(key)), key)

    def page(
        self,
        collection: str,
        *,
        filters: tuple[tuple[str, str, str], ...],
        order_by: tuple[tuple[str, Literal["asc", "desc"]], ...],
        limit: int,
        cursor: str | None,
        cursor_context: tuple[str, int] | None = None,
    ) -> Page[BaseModel]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        parts = collection.split("/")
        parent = "/".join(parts[:-1])
        structured: dict[str, Any] = {
            "from": [{"collectionId": parts[-1]}],
            "orderBy": [
                {"field": {"fieldPath": field}, "direction": direction.upper() + "ENDING"}
                for field, direction in order_by
            ],
            "limit": limit + 1,
        }
        operators = {
            "==": "EQUAL",
            ">": "GREATER_THAN",
            ">=": "GREATER_THAN_OR_EQUAL",
            "<": "LESS_THAN",
            "<=": "LESS_THAN_OR_EQUAL",
        }
        field_filters = [
            {
                "fieldFilter": {
                    "field": {"fieldPath": field},
                    "op": operators[operator],
                    "value": _firestore_value(value),
                }
            }
            for field, operator, value in filters
        ]
        if field_filters:
            structured["where"] = {"compositeFilter": {"op": "AND", "filters": field_filters}}
        if cursor is not None:
            structured["startAt"] = {
                "before": False,
                "values": _decode_cursor(
                    cursor,
                    collection,
                    filters,
                    order_by,
                    cursor_context,
                    self._clock(),
                    self._cursor_secret,
                ),
            }
        body: dict[str, Any] = {
            "parent": self._resource_name(parent),
            "structuredQuery": structured,
        }
        response = self._request_many(
            "POST", urljoin(self._root, self._documents_root.rstrip("/") + ":runQuery"), body
        )
        page_results = response[:limit]
        items = tuple(
            decoded
            for result in page_results
            for decoded in [
                self._decode_document(
                    result.get("document", {}),
                    DocumentKey(
                        collection,
                        result.get("document", {}).get("name", "").rsplit("/", 1)[-1],
                    ),
                )
            ]
            if decoded is not None
        )
        next_cursor = None
        if len(response) > limit and items:
            last_document = page_results[-1].get("document", {})
            last_fields = last_document.get("fields", {})
            ordered_values = []
            for field, _ in order_by:
                if field == "__name__":
                    ordered_values.append({"referenceValue": last_document["name"]})
                else:
                    ordered_values.append(cast(dict[str, Any], last_fields[field]))
            next_cursor = _encode_cursor(
                collection,
                filters,
                order_by,
                ordered_values,
                cursor_context,
                self._clock(),
                self._cursor_secret,
            )
        return Page(
            tuple(item.record for item in items),
            next_cursor,
            tuple(item.key for item in items),
        )

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

    def put_with_server_timestamps_in_transaction(
        self,
        transaction: Transaction,
        document: VersionedDocument[BaseModel],
        *,
        fields: tuple[str, ...],
    ) -> None:
        if not fields or len(fields) != len(set(fields)):
            raise ValueError("server timestamp fields must be nonempty and unique")
        record = document.record.model_dump(mode="python")
        if any(field not in record for field in fields):
            raise ValueError("server timestamp field must exist on the document")
        rest_transaction = self._rest_transaction(transaction)
        rest_transaction.writes.append(
            {
                "update": self._encode_document(document),
                "updateTransforms": [
                    {"fieldPath": field, "setToServerValue": "REQUEST_TIME"}
                    for field in fields
                ],
            }
        )

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

    def _resource_name(self, path: str) -> str:
        return (
            f"projects/{self._project_id}/databases/{self._database_id}/documents/"
            f"{quote(path, safe='/')}"
        )

    def _document_url(self, key: DocumentKey) -> str:
        return urljoin(self._root, self._documents_root + quote(key.path, safe="/"))

    @staticmethod
    def _rest_transaction(transaction: Transaction) -> _RestTransaction:
        if not isinstance(transaction, _RestTransaction):
            raise TypeError("FirestoreRestStore requires its own transaction handle")
        return transaction

    def _encode_document(self, document: VersionedDocument[BaseModel]) -> dict[str, Any]:
        record_fields = {
            key: _firestore_value(value)
            for key, value in document.record.model_dump(mode="python").items()
        }
        return {
            "name": self._resource_name(document.key.path),
            "fields": {
                "_schema_version": {"integerValue": str(document.schema_version)},
                "_document_state_version": {"integerValue": str(document.state_version)},
                **record_fields,
            },
        }

    @staticmethod
    def _decode_document(
        response: dict[str, Any], key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        if not response:
            return None
        fields = response["fields"]
        record = {
            field: _python_value(value)
            for field, value in fields.items()
            if field not in {"_schema_version", "_document_state_version"}
        }
        return VersionedDocument(
            key=key,
            schema_version=int(fields["_schema_version"]["integerValue"]),
            state_version=int(fields["_document_state_version"]["integerValue"]),
            record=_StoredRecord.model_validate(record),
        )

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return cast(dict[str, Any], self._request_payload(method, url, body))

    def _request_many(self, method: str, url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request_payload(method, url, body))

    @staticmethod
    def _request_payload(method: str, url: str, body: dict[str, Any] | None = None) -> object:
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
        return {} if not payload else json.loads(payload)
