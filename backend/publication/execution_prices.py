"""Transactional publication of immutable prices used by paper execution."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from typing import Protocol, TypeVar
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.contracts.analysis import (
    NormalizedPrice,
    NormalizedSession,
    Provenance,
    ReasonCode,
)
from backend.contracts.paper import ExecutionPrice
from backend.contracts.scalars import NonNegativeMoney, OpaqueIdentifier
from backend.store.repositories import DocumentKey, VersionedDocument
from backend.store.transactions import Transaction, TransactionRunner, run_transaction

EXECUTION_PRICE_SCHEMA_VERSION = 1
TRANSACTION_ATTEMPTS = 5
EXECUTION_CALENDAR_KEY = DocumentKey("execution_calendar_controls", "active")

RecordT = TypeVar("RecordT", bound=BaseModel)


class ExecutionPriceError(RuntimeError):
    """A price cannot be published or its publication evidence is inconsistent."""


class ImmutableRevisionConflict(ExecutionPriceError):
    """An immutable source revision ID was reused with different source content."""


class CalendarUnavailable(ExecutionPriceError):
    """The source session is not covered by the active verified calendar."""


class ServerTimestampStore(TransactionRunner, Protocol):
    def get(self, key: DocumentKey) -> VersionedDocument[BaseModel] | None: ...

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None: ...

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None: ...

    def put_with_server_timestamps_in_transaction(
        self,
        transaction: Transaction,
        document: VersionedDocument[BaseModel],
        *,
        fields: tuple[str, ...],
    ) -> None: ...


class PriceRevision(BaseModel):
    """Immutable execution evidence; availability is resolved by the store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    price_revision_id: OpaqueIdentifier
    source_revision_id: OpaqueIdentifier
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbol: OpaqueIdentifier
    session_date: date
    close: NonNegativeMoney
    price_basis_ref: OpaqueIdentifier
    sequence: int = Field(strict=True, ge=1)
    calendar_version: OpaqueIdentifier
    source_evidence: tuple[Provenance, ...]
    validated_available_at: datetime | None

    @field_validator("validated_available_at")
    @classmethod
    def validate_server_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value)
        ):
            raise ValueError("server commit timestamp must be UTC")
        return value


class SymbolSessionControl(BaseModel):
    """Mutable read fence shared by revision writers and execution workers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: OpaqueIdentifier
    session_date: date
    publication_version: int = Field(strict=True, ge=1)
    revision_sequence: int = Field(strict=True, ge=1)
    current_revision_id: OpaqueIdentifier
    calendar_version: OpaqueIdentifier


class CalendarControl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    active_version: OpaqueIdentifier
    publication_version: int = Field(strict=True, ge=1)


class CalendarSessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    calendar_version: OpaqueIdentifier
    session: NormalizedSession


class RevisionValidity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    price_revision_id: OpaqueIdentifier
    valid: bool
    version: int = Field(strict=True, ge=1)
    latest_event_id: OpaqueIdentifier | None
    changed_at: datetime | None


class ValidityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: OpaqueIdentifier
    price_revision_id: OpaqueIdentifier
    valid: bool
    reason_code: ReasonCode
    created_at: datetime | None


class ExecutionPricePublisher:
    """Publish verified source revisions without depending on analytical batch timing."""

    def __init__(self, store: ServerTimestampStore) -> None:
        self._store = store

    def publish_calendar_session(self, session: NormalizedSession) -> CalendarControl:
        """Store one immutable verified session and atomically make its version active."""

        key = self._calendar_session_key(session.calendar_version, session.session_date)
        record = CalendarSessionRecord(calendar_version=session.calendar_version, session=session)

        def write(transaction: Transaction) -> CalendarControl:
            existing = self._store.get_in_transaction(transaction, key)
            if existing is not None:
                stored = self._validate(existing, CalendarSessionRecord, "calendar session")
                if stored.model_dump(mode="json") != record.model_dump(mode="json"):
                    raise ImmutableRevisionConflict("calendar session is immutable")

            current_doc = self._store.get_in_transaction(transaction, EXECUTION_CALENDAR_KEY)
            current = (
                None
                if current_doc is None
                else self._validate(current_doc, CalendarControl, "calendar control")
            )
            if (
                existing is not None
                and current is not None
                and current.active_version == session.calendar_version
            ):
                return current
            if existing is None:
                self._store.put_in_transaction(
                    transaction,
                    VersionedDocument(key, EXECUTION_PRICE_SCHEMA_VERSION, 0, record),
                )
            if current is not None and current.active_version == session.calendar_version:
                return current
            next_control = CalendarControl(
                active_version=session.calendar_version,
                publication_version=1 if current is None else current.publication_version + 1,
            )
            self._store.put_in_transaction(
                transaction,
                VersionedDocument(
                    EXECUTION_CALENDAR_KEY,
                    EXECUTION_PRICE_SCHEMA_VERSION,
                    next_control.publication_version,
                    next_control,
                ),
            )
            return next_control

        return run_transaction(self._store, write, max_attempts=TRANSACTION_ATTEMPTS)

    def publish(self, price: NormalizedPrice, *, source_revision_id: str) -> PriceRevision:
        """Publish one genuine raw close, preserving its first commit timestamp on retry."""

        self._validate_source(price)
        source_available_at = price.validated_available_at
        if source_available_at is None:
            raise ExecutionPriceError("source price lacks verified source availability evidence")
        source_id = OpaqueIdentifier(source_revision_id)
        source_sha256 = self._source_hash(price)
        revision_id = self._revision_id(price, source_id)
        revision_key = self._revision_key(revision_id)
        control_key = self._symbol_session_control_key(price.symbol, price.session_date)
        validity_key = self._validity_key(revision_id)

        def write(transaction: Transaction) -> PriceRevision:
            existing_revision = self._store.get_in_transaction(transaction, revision_key)
            if existing_revision is not None:
                existing = self._validate(existing_revision, PriceRevision, "price revision")
                if existing.source_sha256 != source_sha256:
                    raise ImmutableRevisionConflict(
                        "source revision ID was reused with different price evidence"
                    )
                return existing

            calendar_doc = self._store.get_in_transaction(transaction, EXECUTION_CALENDAR_KEY)
            if calendar_doc is None:
                raise CalendarUnavailable("no verified execution calendar is active")
            calendar = self._validate(calendar_doc, CalendarControl, "calendar control")
            session_key = self._calendar_session_key(
                calendar.active_version, price.session_date
            )
            session_doc = self._store.get_in_transaction(transaction, session_key)
            if session_doc is None:
                raise CalendarUnavailable("active calendar does not cover the price session")
            session_record = self._validate(
                session_doc, CalendarSessionRecord, "calendar session"
            )
            session = session_record.session
            if (
                session.calendar_version != calendar.active_version
                or session.session_date != price.session_date
                or session.status != "trading"
            ):
                raise CalendarUnavailable("price date is not a verified trading session")

            current_doc = self._store.get_in_transaction(transaction, control_key)
            current = (
                None
                if current_doc is None
                else self._validate(current_doc, SymbolSessionControl, "symbol/session control")
            )
            sequence = 1 if current is None else current.revision_sequence + 1
            publication_version = 1 if current is None else current.publication_version + 1
            close = price.close
            if close is None:
                raise ExecutionPriceError("execution price close is missing")
            draft = PriceRevision(
                price_revision_id=revision_id,
                source_revision_id=source_id,
                source_sha256=source_sha256,
                symbol=price.symbol,
                session_date=price.session_date,
                close=close,
                price_basis_ref=price.price_basis_ref,
                sequence=sequence,
                calendar_version=calendar.active_version,
                source_evidence=(price.revision.provenance,),
                validated_available_at=None,
            )
            next_control = SymbolSessionControl(
                symbol=price.symbol,
                session_date=price.session_date,
                publication_version=publication_version,
                revision_sequence=sequence,
                current_revision_id=revision_id,
                calendar_version=calendar.active_version,
            )
            initial_validity = RevisionValidity(
                price_revision_id=revision_id,
                valid=True,
                version=1,
                latest_event_id=None,
                changed_at=None,
            )
            execution_price = ExecutionPrice(
                price_revision_id=revision_id,
                symbol=price.symbol,
                session_date=price.session_date,
                close=close,
                validated_available_at=source_available_at,
                source_evidence=(price.revision.provenance,),
            )
            self._store.put_with_server_timestamps_in_transaction(
                transaction,
                VersionedDocument(
                    revision_key, EXECUTION_PRICE_SCHEMA_VERSION, sequence, draft
                ),
                fields=("validated_available_at",),
            )
            self._store.put_with_server_timestamps_in_transaction(
                transaction,
                VersionedDocument(
                    self._execution_price_key(revision_id),
                    EXECUTION_PRICE_SCHEMA_VERSION,
                    0,
                    execution_price,
                ),
                fields=("validated_available_at",),
            )
            self._store.put_in_transaction(
                transaction,
                VersionedDocument(
                    validity_key, EXECUTION_PRICE_SCHEMA_VERSION, 1, initial_validity
                ),
            )
            self._store.put_in_transaction(
                transaction,
                VersionedDocument(
                    control_key,
                    EXECUTION_PRICE_SCHEMA_VERSION,
                    publication_version,
                    next_control,
                ),
            )
            return draft

        try:
            run_transaction(self._store, write, max_attempts=TRANSACTION_ATTEMPTS)
        except (ImmutableRevisionConflict, CalendarUnavailable):
            raise
        except Exception:
            # A commit may have succeeded while its response was lost. Reconcile by stable ID.
            persisted = self._store.get(revision_key)
            if persisted is None:
                raise
            resolved = self._validate(persisted, PriceRevision, "price revision")
            if resolved.source_sha256 != source_sha256:
                raise ImmutableRevisionConflict(
                    "committed revision conflicts with the retried source evidence"
                )
            return self._require_resolved_timestamp(resolved)

        persisted = self._store.get(revision_key)
        if persisted is None:
            raise ExecutionPriceError("committed price revision could not be read back")
        resolved = self._validate(persisted, PriceRevision, "price revision")
        if resolved.source_sha256 != source_sha256:
            raise ImmutableRevisionConflict("committed revision differs from its source evidence")
        return self._require_resolved_timestamp(resolved)

    def invalidate(
        self,
        price_revision_id: str,
        *,
        event_id: str,
        reason_code: str,
    ) -> RevisionValidity:
        """Append an invalidation event and advance validity and session read controls."""

        revision_id = OpaqueIdentifier(price_revision_id)
        event_identifier = OpaqueIdentifier(event_id)
        event_key = self._event_key(event_identifier)
        reason = OpaqueIdentifier(reason_code)
        revision_key = self._revision_key(revision_id)
        revision_doc = self._store.get(revision_key)
        if revision_doc is None:
            raise ExecutionPriceError("cannot invalidate an unknown price revision")
        revision = self._validate(revision_doc, PriceRevision, "price revision")
        validity_key = self._validity_key(revision_id)
        control_key = self._symbol_session_control_key(revision.symbol, revision.session_date)

        def write(transaction: Transaction) -> RevisionValidity:
            stored_revision = self._store.get_in_transaction(transaction, revision_key)
            if stored_revision is None:
                raise ExecutionPriceError("price revision disappeared during invalidation")
            self._validate(stored_revision, PriceRevision, "price revision")
            existing_event_doc = self._store.get_in_transaction(transaction, event_key)
            if existing_event_doc is not None:
                event = self._validate(existing_event_doc, ValidityEvent, "validity event")
                if (
                    event.price_revision_id != revision_id
                    or event.valid
                    or event.reason_code != reason
                ):
                    raise ImmutableRevisionConflict("validity event ID was reused")
                current_validity_doc = self._store.get_in_transaction(transaction, validity_key)
                if current_validity_doc is None:
                    raise ExecutionPriceError("validity event has no current validity record")
                return self._validate(current_validity_doc, RevisionValidity, "revision validity")

            validity_doc = self._store.get_in_transaction(transaction, validity_key)
            if validity_doc is None:
                raise ExecutionPriceError("price revision has no validity control")
            validity = self._validate(validity_doc, RevisionValidity, "revision validity")
            if not validity.valid:
                raise ImmutableRevisionConflict("revision is already invalid under another event")
            control_doc = self._store.get_in_transaction(transaction, control_key)
            if control_doc is None:
                raise ExecutionPriceError("price revision has no symbol/session control")
            control = self._validate(control_doc, SymbolSessionControl, "symbol/session control")
            next_validity = RevisionValidity(
                price_revision_id=revision_id,
                valid=False,
                version=validity.version + 1,
                latest_event_id=event_identifier,
                changed_at=None,
            )
            event = ValidityEvent(
                event_id=event_identifier,
                price_revision_id=revision_id,
                valid=False,
                reason_code=reason,
                created_at=None,
            )
            next_control = control.model_copy(
                update={"publication_version": control.publication_version + 1}
            )
            self._store.put_with_server_timestamps_in_transaction(
                transaction,
                VersionedDocument(
                    event_key, EXECUTION_PRICE_SCHEMA_VERSION, 1, event
                ),
                fields=("created_at",),
            )
            self._store.put_with_server_timestamps_in_transaction(
                transaction,
                VersionedDocument(
                    validity_key,
                    EXECUTION_PRICE_SCHEMA_VERSION,
                    next_validity.version,
                    next_validity,
                ),
                fields=("changed_at",),
            )
            self._store.put_in_transaction(
                transaction,
                VersionedDocument(
                    control_key,
                    EXECUTION_PRICE_SCHEMA_VERSION,
                    next_control.publication_version,
                    next_control,
                ),
            )
            return next_validity

        try:
            run_transaction(self._store, write, max_attempts=TRANSACTION_ATTEMPTS)
        except (ImmutableRevisionConflict, ExecutionPriceError):
            raise
        except Exception:
            persisted_event = self._store.get(event_key)
            if persisted_event is None:
                raise
            event = self._validate(persisted_event, ValidityEvent, "validity event")
            if (
                event.event_id != event_identifier
                or event.price_revision_id != revision_id
                or event.valid
                or event.reason_code != reason
            ):
                raise ImmutableRevisionConflict("validity event ID was reused")
        persisted_validity = self._store.get(validity_key)
        if persisted_validity is None:
            raise ExecutionPriceError("invalidated revision validity could not be read back")
        return self._validate(persisted_validity, RevisionValidity, "revision validity")

    def read_control(self, symbol: str, session_date: date) -> SymbolSessionControl | None:
        document = self._store.get(self._symbol_session_control_key(symbol, session_date))
        return None if document is None else self._validate(document, SymbolSessionControl, "symbol/session control")

    def read_validity(self, price_revision_id: str) -> RevisionValidity | None:
        document = self._store.get(self._validity_key(price_revision_id))
        return None if document is None else self._validate(document, RevisionValidity, "revision validity")

    @staticmethod
    def _validate_source(price: NormalizedPrice) -> None:
        if price.close_basis != "raw":
            raise ExecutionPriceError("execution prices require a verified raw close")
        if price.trade_status != "traded" or price.basis != "actual":
            raise ExecutionPriceError("execution prices require an actual genuine trade")
        if price.close is None or price.volume is None or price.volume < 1:
            raise ExecutionPriceError("execution prices require an exact close and positive volume")
        if price.validated_available_at is None:
            raise ExecutionPriceError("source price lacks verified source availability evidence")
        if price.session_date != price.original_source_date:
            raise ExecutionPriceError("source session differs from the original source date")

    @staticmethod
    def _source_hash(price: NormalizedPrice) -> str:
        evidence = price.model_dump(
            mode="json",
            exclude={
                "validated_available_at": True,
                "revision": {
                    "known_at": True,
                    "provenance": {"collected_at": True},
                },
            },
        )
        evidence["close_basis"] = price.close_basis
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _revision_id(price: NormalizedPrice, source_revision_id: str) -> str:
        identity = f"{price.symbol}\0{price.session_date.isoformat()}\0{source_revision_id}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _require_resolved_timestamp(revision: PriceRevision) -> PriceRevision:
        if revision.validated_available_at is None:
            raise ExecutionPriceError("server commit timestamp was not resolved after commit")
        return revision

    @staticmethod
    def _validate(
        document: VersionedDocument[BaseModel], model: type[RecordT], label: str
    ) -> RecordT:
        try:
            return model.model_validate_json(document.record.model_dump_json())
        except (TypeError, ValueError) as error:
            raise ExecutionPriceError(f"stored {label} is malformed") from error

    @staticmethod
    def _calendar_session_key(calendar_version: str, session_date: date) -> DocumentKey:
        identity = f"{calendar_version}\0{session_date.isoformat()}"
        return DocumentKey("execution_calendar_sessions", hashlib.sha256(identity.encode()).hexdigest())

    @staticmethod
    def _revision_key(revision_id: str) -> DocumentKey:
        return DocumentKey("execution_price_revisions", quote(revision_id, safe=""))

    @staticmethod
    def _execution_price_key(revision_id: str) -> DocumentKey:
        return DocumentKey("execution_prices", quote(revision_id, safe=""))

    @staticmethod
    def _symbol_session_control_key(symbol: str, session_date: date) -> DocumentKey:
        identity = f"{symbol}\0{session_date.isoformat()}"
        return DocumentKey("execution_price_controls", hashlib.sha256(identity.encode()).hexdigest())

    @staticmethod
    def _validity_key(revision_id: str) -> DocumentKey:
        return DocumentKey("execution_price_validity", quote(revision_id, safe=""))

    @staticmethod
    def _event_key(event_id: str) -> DocumentKey:
        return DocumentKey("execution_price_validity_events", quote(event_id, safe=""))
