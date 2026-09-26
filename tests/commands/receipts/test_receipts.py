from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import pytest
from pydantic import BaseModel

from backend.commands.receipts import (
    ReceiptError,
    ReceiptOutcome,
    execute_with_receipt,
    fingerprint_request,
    parse_idempotency_key,
    validate_first_submission_window,
)
from backend.contracts.envelopes import CommandMetadata, IdempotencyKey
from backend.contracts.paper import PaperCommandReceipt, PortfolioControl
from backend.contracts.routes import SetupPortfolioRequest
from backend.contracts.scalars import OpaqueIdentifier
from backend.store.repositories import (
    DocumentKey,
    OwnerContext,
    Page,
    PaperRepositories,
    VersionedDocument,
)
from backend.store.transactions import Transaction

UTC = timezone.utc
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
OWNER = OpaqueIdentifier("owner-1")
RECOVERY = OpaqueIdentifier("recovery-current")


class CounterRecord(BaseModel):
    value: int


@dataclass
class FakeTransaction:
    writes: dict[str, VersionedDocument[BaseModel]] = field(default_factory=dict)


class FakeStore:
    def __init__(self, *, race_receipt: bool = False) -> None:
        self.documents: dict[str, VersionedDocument[BaseModel]] = {}
        self.events: list[str] = []
        self.callbacks: list[Callable[[Transaction], Any]] = []
        self.race_receipt = race_receipt
        self.counter_key = DocumentKey("test_mutations", "one")

    def get(self, key: DocumentKey) -> VersionedDocument[BaseModel] | None:
        return self.documents.get(key.path)

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
        raise AssertionError("receipt handling must not query collections")

    def run(
        self, callback: Callable[[Transaction], Any], *, max_attempts: int
    ) -> Any:
        self.callbacks.append(callback)
        first = FakeTransaction()
        callback(first)
        if self.race_receipt:
            self.race_receipt = False
            competing = FakeTransaction()
            callback(competing)
            self.documents.update(competing.writes)
            retried = FakeTransaction()
            result = callback(retried)
            self.documents.update(retried.writes)
            return result
        result = callback(first)
        self.documents.update(first.writes)
        return result

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        self.events.append(key.path)
        assert isinstance(transaction, FakeTransaction)
        return transaction.writes.get(key.path, self.documents.get(key.path))

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None:
        assert isinstance(transaction, FakeTransaction)
        transaction.writes[document.key.path] = document


def make_repositories(store: FakeStore) -> PaperRepositories:
    repositories = PaperRepositories(store, OwnerContext(uid=OWNER))
    control_key = repositories.control_key()
    store.documents[control_key.path] = VersionedDocument(
        key=control_key,
        schema_version=1,
        state_version=0,
        record=PortfolioControl(
            owner_uid=OWNER,
            active_generation=OpaqueIdentifier("generation-1"),
            configured_fee_rate_pct="0",
            state_version=0,
            preference_version=0,
            recovery_id=RECOVERY,
            updated_at=NOW,
        ),
    )
    return repositories


def key_at(instant: datetime, suffix: str = "a" * 32) -> IdempotencyKey:
    millis = int(instant.timestamp() * 1000)
    return parse_idempotency_key(f"{millis:013d}.{suffix}")


def command(key: IdempotencyKey, *, recovery: str = str(RECOVERY)) -> CommandMetadata:
    return CommandMetadata(
        idempotency_key=key,
        recovery_id=recovery,
        content_length=32,
        issued_at=NOW,
        expected_generation="generation-1",
        expected_state_version=0,
    )


def request(fee: str, starting_cash: str = "1000000") -> SetupPortfolioRequest:
    return SetupPortfolioRequest.model_validate(
        {
            "command": {
                "idempotency_key": key_at(NOW),
                "recovery_id": RECOVERY,
                "content_length": 32,
                "issued_at": NOW,
            },
            "starting_cash": {"amount": starting_cash, "currency": "XOF"},
            "fee_rate_pct": fee,
        }
    )


def receipt_record(
    repositories: PaperRepositories,
    key: IdempotencyKey,
    *,
    fingerprint: str = "a" * 64,
    accepted_at: datetime = NOW - timedelta(days=1),
    recovery_id: str = str(RECOVERY),
    generation: str | None = "generation-1",
) -> VersionedDocument[BaseModel]:
    record = PaperCommandReceipt(
        owner_uid=OWNER,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        recovery_id=recovery_id,
        operation="place_order",
        outcome_id="outcome-1",
        generation=generation,
        state_version=1,
        http_status=201,
        accepted_at=accepted_at,
        expires_at=accepted_at + timedelta(days=30),
    )
    return VersionedDocument(
        key=repositories.receipt_key(key),
        schema_version=1,
        state_version=0,
        record=record,
    )


def test_key_parser_and_clock_bounds_are_inclusive() -> None:
    exactly_old = key_at(NOW - timedelta(minutes=5))
    exactly_future = key_at(NOW + timedelta(seconds=60), "b" * 32)
    validate_first_submission_window(exactly_old, NOW)
    validate_first_submission_window(exactly_future, NOW)

    with pytest.raises(ReceiptError, match="outside its submission window") as expired:
        validate_first_submission_window(key_at(NOW - timedelta(minutes=5, milliseconds=1)), NOW)
    assert expired.value.code == "command_window_expired"

    with pytest.raises(ReceiptError) as ahead:
        validate_first_submission_window(
            key_at(NOW + timedelta(seconds=60, milliseconds=1)), NOW
        )
    assert ahead.value.code == "command_clock_ahead"

    with pytest.raises(ReceiptError) as malformed:
        parse_idempotency_key("1700000000000." + "A" * 32)
    assert malformed.value.status_code == 422


def test_fingerprint_normalizes_equivalent_decimal_spellings() -> None:
    first = request("1.250000", "1000000.000000")
    equivalent = request("1.25", "1000000")
    changed = request("1.250001", "1000000")

    first_hash = fingerprint_request("POST", "/v1/paper/portfolio", first)
    assert first_hash == fingerprint_request("POST", "/v1/paper/portfolio", equivalent)
    assert first_hash != fingerprint_request("POST", "/v1/paper/portfolio", changed)


def test_recovery_mismatch_precedes_receipt_lookup_and_mutation() -> None:
    store = FakeStore()
    repositories = make_repositories(store)
    key = key_at(NOW)
    store.documents[repositories.receipt_key(key).path] = receipt_record(repositories, key)

    with pytest.raises(ReceiptError) as mismatch:
        execute_with_receipt(
            store,
            repositories,
            command(key, recovery="recovery-old"),
            "a" * 64,
            now=NOW,
            apply_mutation=lambda _tx: pytest.fail("must not mutate"),
        )

    assert mismatch.value.code == "recovery_mismatch"
    assert store.events == [repositories.control_key().path]


def test_matching_receipt_replays_minimal_outcome_without_mutation() -> None:
    store = FakeStore()
    repositories = make_repositories(store)
    key = key_at(NOW - timedelta(days=1))
    store.documents[repositories.receipt_key(key).path] = receipt_record(repositories, key)

    result = execute_with_receipt(
        store,
        repositories,
        command(key),
        "a" * 64,
        now=NOW,
        apply_mutation=lambda _tx: pytest.fail("must not mutate"),
    )

    assert result.replayed
    assert result.receipt.replayed
    assert result.receipt.http_status == 201
    assert "request_fingerprint" not in result.receipt.model_dump()


def test_conflicting_payload_and_expired_receipt_are_rejected() -> None:
    store = FakeStore()
    repositories = make_repositories(store)
    key = key_at(NOW - timedelta(days=1))
    store.documents[repositories.receipt_key(key).path] = receipt_record(repositories, key)

    with pytest.raises(ReceiptError) as conflict:
        execute_with_receipt(
            store,
            repositories,
            command(key),
            "b" * 64,
            now=NOW,
            apply_mutation=lambda _tx: pytest.fail("must not mutate"),
        )
    assert conflict.value.code == "idempotency_conflict"

    expired_key = key_at(NOW - timedelta(days=30))
    store.documents[repositories.receipt_key(expired_key).path] = receipt_record(
        repositories,
        expired_key,
        accepted_at=NOW - timedelta(days=30),
    )
    with pytest.raises(ReceiptError) as expired:
        execute_with_receipt(
            store,
            repositories,
            command(expired_key),
            "a" * 64,
            now=NOW,
            apply_mutation=lambda _tx: pytest.fail("must not mutate"),
        )
    assert expired.value.code == "command_window_expired"


def test_superseded_generation_never_replays_outcome() -> None:
    store = FakeStore()
    repositories = make_repositories(store)
    control_key = repositories.control_key()
    current = store.documents[control_key.path]
    assert isinstance(current.record, PortfolioControl)
    store.documents[control_key.path] = VersionedDocument(
        key=control_key,
        schema_version=current.schema_version,
        state_version=current.state_version,
        record=current.record.model_copy(
            update={"active_generation": OpaqueIdentifier("generation-2")}
        ),
    )
    key = key_at(NOW - timedelta(days=1))
    store.documents[repositories.receipt_key(key).path] = receipt_record(repositories, key)

    with pytest.raises(ReceiptError) as superseded:
        execute_with_receipt(
            store,
            repositories,
            command(key),
            "a" * 64,
            now=NOW,
            apply_mutation=lambda _tx: pytest.fail("must not mutate"),
        )
    assert superseded.value.code == "generation_superseded"
    assert "outcome-1" not in str(superseded.value)


def test_purged_old_receipt_key_cannot_become_a_new_mutation() -> None:
    store = FakeStore()
    repositories = make_repositories(store)
    key = key_at(NOW - timedelta(days=31))
    mutated: list[bool] = []

    def mutate(_transaction: Transaction) -> ReceiptOutcome:
        mutated.append(True)
        return ReceiptOutcome(operation="place_order", http_status=201)

    with pytest.raises(ReceiptError) as expired:
        execute_with_receipt(
            store,
            repositories,
            command(key),
            "a" * 64,
            now=NOW,
            apply_mutation=mutate,
        )
    assert expired.value.code == "command_window_expired"
    assert mutated == []


def test_concurrent_duplicate_commits_only_one_business_write() -> None:
    store = FakeStore(race_receipt=True)
    repositories = make_repositories(store)
    key = key_at(NOW)

    def increment(transaction: Transaction) -> ReceiptOutcome:
        previous = store.get_in_transaction(transaction, store.counter_key)
        value = 0 if previous is None else CounterRecord.model_validate(
            previous.record.model_dump()
        ).value
        store.put_in_transaction(
            transaction,
            VersionedDocument(
                key=store.counter_key,
                schema_version=1,
                state_version=value,
                record=CounterRecord(value=value + 1),
            ),
        )
        return ReceiptOutcome(operation="place_order", http_status=201)

    result = execute_with_receipt(
        store,
        repositories,
        command(key),
        "a" * 64,
        now=NOW,
        apply_mutation=increment,
    )

    assert result.replayed
    committed = store.documents[store.counter_key.path]
    assert CounterRecord.model_validate(committed.record).value == 1
    assert len(
        [path for path in store.documents if path.startswith("paper_portfolios/owner-1/command_receipts/")]
    ) == 1
