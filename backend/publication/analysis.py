"""Immutable analytical serving copies and batch-pinned publication reads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import quote, unquote

from pydantic import BaseModel, ConfigDict

from backend.analysis.batch import AnalyticalBatch, StockCalculation
from backend.store.repositories import (
    DocumentKey,
    MAX_PAGE_SIZE,
    Page,
    PublicationRepositories,
    RepositoryError,
    TransactionalStore,
    VersionedDocument,
)
from backend.store.transactions import Transaction, run_transaction

PUBLICATION_SCHEMA_VERSION = 1
PUBLICATION_TRANSACTION_ATTEMPTS = 5
MANIFEST_COLLECTION = "publication_manifests"
ACTIVE_PUBLICATION_KEY = DocumentKey("publication_state", "current")


class PublicationError(RuntimeError):
    """A serving copy cannot be safely published or read."""


class IncompletePublication(PublicationError):
    """The persisted immutable copy does not match its canonical manifest."""


class ServingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: str
    value: Any = None
    reason_codes: tuple[str, ...] = ()


class ServingStock(BaseModel):
    """One immutable, batch-scoped result for a catalog symbol."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: str
    catalog_id: str
    effective_session: str
    input_snapshot_id: str
    rule_version: str
    revision: int
    symbol: str
    outputs: tuple[ServingOutput, ...]


class ManifestAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: str
    reason_codes: tuple[str, ...]


class ManifestSymbol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    availability: tuple[ManifestAvailability, ...]


class ServingManifest(BaseModel):
    """Durable manifest copied alongside the immutable result documents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str
    effective_session: str
    input_snapshot_id: str
    rule_version: str
    revision: int
    batch_id: str
    supersedes_batch_id: str | None
    symbols: tuple[ManifestSymbol, ...]
    content_sha256: str
    result_count: int


class ActivePublication(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: str
    catalog_id: str
    effective_session: str
    input_snapshot_id: str
    rule_version: str
    revision: int
    content_sha256: str


class PublicationReady(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: str
    content_sha256: str
    result_count: int


class AnalyticalPublisher:
    """Copy canonical results, verify completeness, then switch one pointer."""

    def __init__(self, store: TransactionalStore) -> None:
        self._store = store
        self._results = PublicationRepositories(store)

    def publish(self, batch: AnalyticalBatch) -> ActivePublication:
        """Idempotently copy a complete batch and make it active after readback."""

        manifest = self._manifest(batch)
        self._write_manifest(batch.batch_id, manifest)
        for stock in batch.stocks:
            result = self._serving_stock(batch, stock)

            def write_result(transaction: Transaction) -> None:
                self._results.write_result(
                    transaction,
                    batch_id=batch.batch_id,
                    record_id=result.symbol,
                    record=result,
                    schema_version=PUBLICATION_SCHEMA_VERSION,
                )

            try:
                run_transaction(
                    self._store,
                    write_result,
                    max_attempts=PUBLICATION_TRANSACTION_ATTEMPTS,
                )
            except RepositoryError as error:
                raise PublicationError(
                    "immutable serving result conflicts with its retry"
                ) from error

        self._verify_complete(batch, manifest)
        self._mark_ready(batch.batch_id, manifest)
        return self._promote(batch)

    def active_publication(self) -> ActivePublication | None:
        stored = self._store.get(ACTIVE_PUBLICATION_KEY)
        if stored is None:
            return None
        try:
            return ActivePublication.model_validate(stored.record.model_dump(mode="python"))
        except (TypeError, ValueError) as error:
            raise PublicationError("active publication pointer is malformed") from error

    def read_batch(
        self, batch_id: str, *, limit: int, cursor: str | None = None
    ) -> Page[ServingStock]:
        """Read a bounded page from exactly one immutable batch."""

        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        ready = self._store.get(self._ready_key(batch_id))
        if ready is None:
            raise PublicationError("batch is not a complete published serving copy")
        try:
            marker = PublicationReady.model_validate(ready.record.model_dump(mode="python"))
        except (TypeError, ValueError) as error:
            raise PublicationError("publication readiness marker is malformed") from error
        if marker.batch_id != batch_id:
            raise PublicationError("publication readiness marker belongs to another batch")
        stored_manifest = self._store.get(self._manifest_key(batch_id))
        if stored_manifest is None:
            raise PublicationError("complete publication manifest is missing")
        try:
            manifest = ServingManifest.model_validate(
                stored_manifest.record.model_dump(mode="python")
            )
        except (TypeError, ValueError) as error:
            raise PublicationError("publication manifest is malformed") from error
        if (marker.content_sha256, marker.result_count) != (
            manifest.content_sha256,
            manifest.result_count,
        ):
            raise PublicationError("publication readiness marker does not match its manifest")
        return self._read_results(batch_id, limit=limit, cursor=cursor)

    def _read_results(
        self, batch_id: str, *, limit: int, cursor: str | None = None
    ) -> Page[ServingStock]:
        page = self._results.list_results(batch_id, limit=limit, cursor=cursor)
        records: list[ServingStock] = []
        for record in page.items:
            try:
                serving = ServingStock.model_validate(record.model_dump(mode="python"))
            except (TypeError, ValueError) as error:
                raise PublicationError("serving result record is malformed") from error
            if serving.batch_id != batch_id:
                raise PublicationError("batch-pinned read returned a result from another batch")
            records.append(serving)
        if len(records) != len(page.keys):
            raise PublicationError("serving page did not preserve result document keys")
        for key in page.keys:
            if key.collection != self._results.result_key(batch_id, "_probe").collection:
                raise PublicationError("serving page returned a key from another batch")
        return Page(tuple(records), page.next_cursor, page.keys)

    def _write_manifest(self, batch_id: str, manifest: ServingManifest) -> None:
        key = self._manifest_key(batch_id)

        def write(transaction: Transaction) -> None:
            current = self._store.get_in_transaction(transaction, key)
            if current is not None:
                if (
                    current.schema_version != PUBLICATION_SCHEMA_VERSION
                    or current.record.model_dump(mode="json") != manifest.model_dump(mode="json")
                ):
                    raise RepositoryError("published manifests are immutable")
                return
            self._store.put_in_transaction(
                transaction,
                VersionedDocument(key, PUBLICATION_SCHEMA_VERSION, 0, manifest),
            )

        try:
            run_transaction(self._store, write, max_attempts=PUBLICATION_TRANSACTION_ATTEMPTS)
        except RepositoryError as error:
            raise PublicationError(
                "immutable publication manifest conflicts with its retry"
            ) from error

    def _verify_complete(self, batch: AnalyticalBatch, expected: ServingManifest) -> None:
        stored_manifest = self._store.get(self._manifest_key(batch.batch_id))
        if (
            stored_manifest is None
            or stored_manifest.record.model_dump(mode="json") != expected.model_dump(mode="json")
        ):
            raise IncompletePublication("persisted manifest does not match the canonical batch")

        expected_by_symbol = {
            result.symbol: result
            for result in (self._serving_stock(batch, stock) for stock in batch.stocks)
        }
        actual_by_symbol: dict[str, ServingStock] = {}
        cursor: str | None = None
        while True:
            page = self._read_results(batch.batch_id, limit=MAX_PAGE_SIZE, cursor=cursor)
            for key, result in zip(page.keys, page.items, strict=True):
                symbol = unquote(key.document_id)
                if symbol in actual_by_symbol or symbol != result.symbol:
                    raise IncompletePublication(
                        "serving results contain duplicate or mismatched symbols"
                    )
                actual_by_symbol[symbol] = result
            cursor = page.next_cursor
            if cursor is None:
                break

        if actual_by_symbol.keys() != expected_by_symbol.keys():
            raise IncompletePublication(
                "serving result symbols do not match the canonical manifest"
            )
        for symbol, expected_result in expected_by_symbol.items():
            if actual_by_symbol[symbol].model_dump(mode="json") != expected_result.model_dump(
                mode="json"
            ):
                raise IncompletePublication(
                    f"serving result for {symbol} differs from canonical evidence"
                )
        if len(actual_by_symbol) != expected.result_count:
            raise IncompletePublication(
                "serving result count does not match the canonical manifest"
            )
        manifest_by_symbol = {entry.symbol: entry for entry in expected.symbols}
        if manifest_by_symbol.keys() != expected_by_symbol.keys():
            raise IncompletePublication("manifest symbols do not match canonical results")
        for symbol, result in actual_by_symbol.items():
            actual_availability = tuple(
                ManifestAvailability(
                    name=output.name,
                    status=output.status,
                    reason_codes=output.reason_codes,
                )
                for output in result.outputs
            )
            if actual_availability != manifest_by_symbol[symbol].availability:
                raise IncompletePublication(
                    f"serving availability for {symbol} differs from manifest"
                )

    def _mark_ready(self, batch_id: str, manifest: ServingManifest) -> None:
        key = self._ready_key(batch_id)
        marker = PublicationReady(
            batch_id=batch_id,
            content_sha256=manifest.content_sha256,
            result_count=manifest.result_count,
        )

        def write(transaction: Transaction) -> None:
            current = self._store.get_in_transaction(transaction, key)
            if current is not None:
                if (
                    current.schema_version != PUBLICATION_SCHEMA_VERSION
                    or current.record.model_dump(mode="json") != marker.model_dump(mode="json")
                ):
                    raise RepositoryError("publication readiness markers are immutable")
                return
            self._store.put_in_transaction(
                transaction,
                VersionedDocument(key, PUBLICATION_SCHEMA_VERSION, 0, marker),
            )

        try:
            run_transaction(self._store, write, max_attempts=PUBLICATION_TRANSACTION_ATTEMPTS)
        except RepositoryError as error:
            raise PublicationError(
                "publication readiness marker conflicts with its retry"
            ) from error

    def _promote(self, batch: AnalyticalBatch) -> ActivePublication:
        candidate = ActivePublication(
            batch_id=batch.batch_id,
            catalog_id=batch.catalog_id,
            effective_session=batch.effective_session,
            input_snapshot_id=batch.input_snapshot_id,
            rule_version=batch.rule_version,
            revision=batch.revision,
            content_sha256=batch.manifest.content_sha256,
        )

        def promote(transaction: Transaction) -> ActivePublication:
            current = self._store.get_in_transaction(transaction, ACTIVE_PUBLICATION_KEY)
            if current is not None:
                active = ActivePublication.model_validate(current.record.model_dump(mode="python"))
                if active == candidate:
                    return active
                if batch.effective_session < active.effective_session:
                    raise PublicationError("an older batch cannot replace the active publication")
                if batch.effective_session == active.effective_session:
                    if (
                        batch.supersedes_batch_id != active.batch_id
                        or batch.revision <= active.revision
                    ):
                        raise PublicationError(
                            "same-session correction must supersede the active batch"
                        )
            elif batch.revision > 1:
                raise PublicationError(
                    "a correction cannot be promoted without its active predecessor"
                )
            self._store.put_in_transaction(
                transaction,
                VersionedDocument(
                    ACTIVE_PUBLICATION_KEY,
                    PUBLICATION_SCHEMA_VERSION,
                    (0 if current is None else current.state_version + 1),
                    candidate,
                ),
            )
            return candidate

        return run_transaction(
            self._store, promote, max_attempts=PUBLICATION_TRANSACTION_ATTEMPTS
        )

    @staticmethod
    def _manifest_key(batch_id: str) -> DocumentKey:
        return DocumentKey(
            f"analysis_batches/{quote(batch_id, safe='')}/{MANIFEST_COLLECTION}", "manifest"
        )

    @staticmethod
    def _ready_key(batch_id: str) -> DocumentKey:
        return DocumentKey(
            f"analysis_batches/{quote(batch_id, safe='')}/{MANIFEST_COLLECTION}", "ready"
        )

    @staticmethod
    def _manifest(batch: AnalyticalBatch) -> ServingManifest:
        return ServingManifest(
            catalog_id=batch.manifest.catalog_id,
            effective_session=batch.manifest.effective_session,
            input_snapshot_id=batch.manifest.input_snapshot_id,
            rule_version=batch.manifest.rule_version,
            revision=batch.manifest.revision,
            batch_id=batch.manifest.batch_id,
            supersedes_batch_id=batch.manifest.supersedes_batch_id,
            symbols=tuple(
                ManifestSymbol(
                    symbol=entry.symbol,
                    availability=tuple(
                        ManifestAvailability(
                            name=availability.name,
                            status=availability.status,
                            reason_codes=availability.reason_codes,
                        )
                        for availability in entry.availability
                    ),
                )
                for entry in batch.manifest.symbols
            ),
            content_sha256=batch.manifest.content_sha256,
            result_count=len(batch.manifest.symbols),
        )

    @staticmethod
    def _serving_stock(batch: AnalyticalBatch, stock: StockCalculation) -> ServingStock:
        return ServingStock(
            batch_id=batch.batch_id,
            catalog_id=batch.catalog_id,
            effective_session=batch.effective_session,
            input_snapshot_id=batch.input_snapshot_id,
            rule_version=batch.rule_version,
            revision=batch.revision,
            symbol=stock.symbol,
            outputs=tuple(
                ServingOutput(
                    name=output.name,
                    status=output.status,
                    value=None if output.value is None else _thaw(output.value),
                    reason_codes=output.reason_codes,
                )
                for output in stock.outputs
            ),
        )


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return cast(Any, value)
