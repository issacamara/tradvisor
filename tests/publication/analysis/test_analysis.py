from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from urllib.parse import quote

import pytest
from pydantic import BaseModel

from backend.analysis.batch import (
    AnalyticalBatch,
    CalculationOutput,
    StockCalculation,
    build_analytical_batch,
)
from backend.publication.analysis import (
    ACTIVE_PUBLICATION_KEY,
    AnalyticalPublisher,
    IncompletePublication,
    PublicationError,
    ServingStock,
)
from backend.store.repositories import DocumentKey, Page, VersionedDocument
from backend.store.transactions import Transaction


@dataclass
class MemoryTransaction:
    writes: dict[str, VersionedDocument[BaseModel]] = field(default_factory=dict)


class MemoryStore:
    def __init__(self) -> None:
        self.documents: dict[str, VersionedDocument[BaseModel]] = {}
        self.fail_result_write_number: int | None = None
        self.result_write_count = 0
        self.omit_next_page_result: str | None = None
        self.queries: list[str] = []

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
        del filters, order_by, cursor_context
        self.queries.append(collection)
        values = sorted(
            (value for value in self.documents.values() if value.key.collection == collection),
            key=lambda value: value.key.document_id,
        )
        if self.omit_next_page_result is not None:
            omitted = self.omit_next_page_result
            self.omit_next_page_result = None
            values = [value for value in values if value.key.document_id != omitted]
        offset = int(cursor or "0")
        selected = values[offset : offset + limit]
        next_cursor = str(offset + len(selected)) if offset + len(selected) < len(values) else None
        return Page(
            tuple(value.record for value in selected),
            next_cursor,
            tuple(value.key for value in selected),
        )

    def run(self, callback: Callable[[Transaction], Any], *, max_attempts: int) -> Any:
        del max_attempts
        transaction = MemoryTransaction()
        result = callback(transaction)
        self.documents.update(transaction.writes)
        return result

    def get_in_transaction(
        self, transaction: Transaction, key: DocumentKey
    ) -> VersionedDocument[BaseModel] | None:
        assert isinstance(transaction, MemoryTransaction)
        return transaction.writes.get(key.path, self.documents.get(key.path))

    def put_in_transaction(
        self, transaction: Transaction, document: VersionedDocument[BaseModel]
    ) -> None:
        assert isinstance(transaction, MemoryTransaction)
        if document.key.collection.endswith("/results"):
            self.result_write_count += 1
            if self.result_write_count == self.fail_result_write_number:
                raise RuntimeError("injected mid-copy failure")
        transaction.writes[document.key.path] = document


def _batch(
    session: str = "2026-09-24", *, revision: int = 1, supersedes: str | None = None
) -> AnalyticalBatch:
    return build_analytical_batch(
        catalog_id="brvm",
        effective_session=date.fromisoformat(session),
        input_snapshot_id=f"snapshot-{session}-{revision}",
        rule_version="analysis-v1",
        expected_symbols=("AAA", "BBB", "CCC"),
        expected_output_names=("growth", "swing"),
        stocks=(
            StockCalculation(
                "AAA",
                (
                    CalculationOutput("growth", "available", {"score": 72, "factors": [1, 2]}),
                    CalculationOutput("swing", "unavailable", reason_codes=("warming_up",)),
                ),
            ),
            StockCalculation(
                "BBB",
                (
                    CalculationOutput("growth", "unavailable", reason_codes=("missing_report",)),
                    CalculationOutput("swing", "available", {"action": "keep"}),
                ),
            ),
            StockCalculation(
                "CCC",
                (
                    CalculationOutput("growth", "unavailable", reason_codes=("missing_report",)),
                    CalculationOutput("swing", "unavailable", reason_codes=("missing_prices",)),
                ),
            ),
        ),
        inputs_ready=True,
        revision=revision,
        supersedes_batch_id=supersedes,
    )


def test_unavailable_outputs_are_copied_with_manifest_coverage_and_retry_is_idempotent() -> None:
    store = MemoryStore()
    publisher = AnalyticalPublisher(store)
    batch = _batch()

    active = publisher.publish(batch)
    writes_after_first_publish = len(store.documents)
    repeated = publisher.publish(batch)

    page = publisher.read_batch(batch.batch_id, limit=10)
    by_symbol = {item.symbol: item for item in page.items}
    unavailable = by_symbol["AAA"].outputs[1]
    assert unavailable.status == "unavailable"
    assert unavailable.reason_codes == ("warming_up",)
    assert by_symbol["AAA"].outputs[0].value == {"score": 72, "factors": [1, 2]}
    assert active == repeated
    assert len(store.documents) == writes_after_first_publish
    assert publisher.active_publication() == active


def test_mid_copy_failure_keeps_old_batch_active_and_retry_promotes_complete_batch() -> None:
    store = MemoryStore()
    publisher = AnalyticalPublisher(store)
    old_batch = _batch()
    old_active = publisher.publish(old_batch)
    new_batch = _batch("2026-09-25")
    store.fail_result_write_number = store.result_write_count + 2

    with pytest.raises(RuntimeError, match="mid-copy"):
        publisher.publish(new_batch)
    assert publisher.active_publication() == old_active
    with pytest.raises(PublicationError, match="not a complete"):
        publisher.read_batch(new_batch.batch_id, limit=1)

    store.fail_result_write_number = None
    new_active = publisher.publish(new_batch)
    assert new_active.batch_id == new_batch.batch_id
    assert publisher.active_publication() == new_active
    assert len(publisher.read_batch(new_batch.batch_id, limit=10).items) == 3


def test_incomplete_readback_never_promotes_and_a_complete_retry_can_promote() -> None:
    store = MemoryStore()
    publisher = AnalyticalPublisher(store)
    batch = _batch()
    store.omit_next_page_result = "BBB"

    with pytest.raises(IncompletePublication, match="symbols"):
        publisher.publish(batch)
    assert store.get(ACTIVE_PUBLICATION_KEY) is None
    with pytest.raises(PublicationError, match="not a complete"):
        publisher.read_batch(batch.batch_id, limit=1)

    active = publisher.publish(batch)
    assert active.batch_id == batch.batch_id


def test_batch_pinned_pages_remain_on_requested_version_after_promotion() -> None:
    store = MemoryStore()
    publisher = AnalyticalPublisher(store)
    first = _batch()
    second = _batch("2026-09-25")
    publisher.publish(first)
    publisher.publish(second)

    first_page = publisher.read_batch(first.batch_id, limit=1)
    second_page = publisher.read_batch(second.batch_id, limit=1)

    assert len(first_page.items) == len(second_page.items) == 1
    assert first_page.items[0].batch_id == first.batch_id
    assert second_page.items[0].batch_id == second.batch_id
    assert first_page.next_cursor is not None
    continued = publisher.read_batch(first.batch_id, limit=1, cursor=first_page.next_cursor)
    assert continued.items[0].batch_id == first.batch_id
    assert any(
        f"analysis_batches/{quote(first.batch_id, safe='')}/results" in query
        for query in store.queries
    )
    assert any(
        f"analysis_batches/{quote(second.batch_id, safe='')}/results" in query
        for query in store.queries
    )


def test_immutable_result_conflict_is_not_overwritten_or_promoted() -> None:
    store = MemoryStore()
    publisher = AnalyticalPublisher(store)
    batch = _batch()
    active = publisher.publish(batch)
    key = next(key for key in store.documents if key.endswith("/AAA"))
    old = store.documents[key]
    changed = ServingStock.model_validate(old.record.model_dump(mode="python"))
    changed.outputs[0].value["score"] = 99
    store.documents[key] = VersionedDocument(
        old.key, old.schema_version, old.state_version, changed
    )

    with pytest.raises(PublicationError, match="immutable"):
        publisher.publish(batch)
    assert publisher.active_publication() == active


def test_read_page_size_is_bounded() -> None:
    publisher = AnalyticalPublisher(MemoryStore())
    with pytest.raises(ValueError, match="limit"):
        publisher.read_batch("batch-id", limit=101)
