"""Authenticated Python Firestore SDK adapter for production application use.

``FirestoreRestStore`` remains the dependency-free local-emulator adapter. This
module uses the Google Cloud Python server SDK and Application Default
Credentials when a client is not injected by the application composition root.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict

from backend.store.firestore import (
    FirestoreConflict,
    _decode_cursor,
    _encode_cursor,
    _firestore_value,
    _python_value,
)
from backend.store.repositories import DocumentKey, Page, TransactionalStore, VersionedDocument
from backend.store.transactions import Transaction


class _SdkStoredRecord(BaseModel):
    model_config = ConfigDict(extra="allow")


class FirestoreSdkStore(TransactionalStore):
    """Production-capable store backed by an authenticated Firestore SDK client."""

    def __init__(
        self,
        *,
        project_id: str,
        database_id: str = "(default)",
        cursor_secret: str,
        client: Any | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._project_id = project_id
        self._database_id = database_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if not cursor_secret:
            raise ValueError("Firestore SDK adapter requires a cursor signing secret")
        self._cursor_secret = cursor_secret
        if client is None:
            try:
                firestore = importlib.import_module("google.cloud.firestore")
            except ImportError as error:
                raise RuntimeError(
                    "FirestoreSdkStore requires the backend[firestore] extra"
                ) from error
            client = firestore.Client(project=project_id, database=database_id)
        self._client = client

    def run(self, callback: Callable[[Transaction], Any], *, max_attempts: int) -> Any:
        try:
            google_exceptions = importlib.import_module("google.api_core.exceptions")
        except ImportError as error:
            raise RuntimeError("FirestoreSdkStore requires google-cloud-firestore") from error
        retryable = (
            google_exceptions.Aborted,
            google_exceptions.Conflict,
            google_exceptions.DeadlineExceeded,
            google_exceptions.ServiceUnavailable,
        )
        for attempt in range(max_attempts):
            transaction = self._client.transaction()
            try:
                result = callback(transaction)
                transaction.commit()
                return result
            except retryable as error:
                if attempt + 1 == max_attempts:
                    raise FirestoreConflict("Firestore transaction retry budget exhausted") from error
        raise FirestoreConflict("Firestore transaction retry budget exhausted")

    def get(self, key: DocumentKey) -> VersionedDocument[BaseModel] | None:
        return self._decode_snapshot(key, self._client.document(key.path).get())

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
        firestore = importlib.import_module("google.cloud.firestore")

        query = self._client.collection(collection)
        for field, operator, value in filters:
            query = query.where(field_path=field, op_string=operator, value=value)
        for field, direction in order_by:
            field_path: Any = (
                firestore.FieldPath.document_id() if field == "__name__" else field
            )
            query = query.order_by(
                field_path,
                direction=(
                    firestore.Query.DESCENDING
                    if direction == "desc"
                    else firestore.Query.ASCENDING
                ),
            )
        if cursor is not None:
            encoded_values = _decode_cursor(
                cursor,
                collection,
                filters,
                order_by,
                cursor_context,
                self._clock(),
                self._cursor_secret,
            )
            cursor_values: dict[Any, Any] = {}
            for (field, _), encoded in zip(order_by, encoded_values, strict=True):
                cursor_value: Any = _python_value(encoded)
                if field == "__name__":
                    reference_path = str(cursor_value).split("/documents/", 1)[-1]
                    cursor_value = self._client.document(reference_path)
                cursor_values[field] = cursor_value
            query = query.start_at(cursor_values, before=False)
        documents = list(query.limit(limit + 1).stream())
        page_documents = documents[:limit]
        next_cursor = None
        if len(documents) > limit and page_documents:
            last = page_documents[-1]
            data = last.to_dict()
            values: list[dict[str, Any]] = []
            for field, _ in order_by:
                if field == "__name__":
                    values.append({"referenceValue": self._resource_name(last.reference.path)})
                else:
                    values.append(_firestore_value(data[field]))
            next_cursor = _encode_cursor(
                collection,
                filters,
                order_by,
                values,
                cursor_context,
                self._clock(),
                self._cursor_secret,
            )
        items = tuple(
            decoded
            for document in page_documents
            for decoded in [self._decode_snapshot(DocumentKey(collection, document.id), document)]
            if decoded is not None
        )
        return Page(tuple(item.record for item in items), next_cursor)

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        snapshots = self._sdk_transaction(transaction).get(self._client.document(key.path))
        snapshot = next(iter(snapshots), None)
        if snapshot is None:
            return None
        return self._decode_snapshot(key, snapshot)

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None:
        self._sdk_transaction(transaction).set(
            self._client.document(document.key.path), self._encode_document(document)
        )

    def _resource_name(self, path: str) -> str:
        return f"projects/{self._project_id}/databases/{self._database_id}/documents/{path}"

    @staticmethod
    def _sdk_transaction(transaction: Transaction) -> Any:
        if not hasattr(transaction, "get") or not hasattr(transaction, "set"):
            raise TypeError("FirestoreSdkStore requires its own SDK transaction handle")
        return transaction

    @staticmethod
    def _encode_document(document: VersionedDocument[BaseModel]) -> dict[str, Any]:
        return {
            "_schema_version": document.schema_version,
            "_document_state_version": document.state_version,
            **document.record.model_dump(mode="python"),
        }

    @staticmethod
    def _decode_snapshot(key: DocumentKey, snapshot: Any) -> VersionedDocument[BaseModel] | None:
        if not snapshot.exists:
            return None
        fields = cast(dict[str, Any], snapshot.to_dict())
        record = {
            field: _python_value(_firestore_value(value))
            for field, value in fields.items()
            if field not in {"_schema_version", "_document_state_version"}
        }
        return VersionedDocument(
            key=key,
            schema_version=int(fields["_schema_version"]),
            state_version=int(fields["_document_state_version"]),
            record=_SdkStoredRecord.model_validate(record),
        )
