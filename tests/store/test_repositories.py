from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pytest
from pydantic import BaseModel

from backend.contracts.scalars import OpaqueIdentifier
from backend.store.repositories import DocumentKey, Page, PublicationRepositories, RepositoryError, VersionedDocument


class Result(BaseModel):
    value: int


@dataclass
class Store:
    documents: dict[str, VersionedDocument[BaseModel]] = field(default_factory=dict)
    queries: list[dict[str, object]] = field(default_factory=list)

    def get_in_transaction(self, _transaction: object, key: DocumentKey) -> VersionedDocument[BaseModel] | None:
        return self.documents.get(key.path)

    def put_in_transaction(self, _transaction: object, document: VersionedDocument[BaseModel]) -> None:
        self.documents[document.key.path] = document

    def page(
        self, collection: str, *, filters: tuple[tuple[str, str, str], ...],
        order_by: tuple[tuple[str, Literal["asc", "desc"]], ...], limit: int,
        cursor: str | None, cursor_context: tuple[str, int] | None = None,
    ) -> Page[BaseModel]:
        self.queries.append({"collection": collection, "filters": filters, "order_by": order_by, "limit": limit, "cursor": cursor})
        return Page((), None)


def test_publication_results_are_immutable_and_bounded_by_batch() -> None:
    store = Store()
    repositories = PublicationRepositories(store)  # type: ignore[arg-type]
    batch_id = OpaqueIdentifier("batch/one")
    record_id = OpaqueIdentifier("ABJC")
    first = repositories.write_result(object(), batch_id=batch_id, record_id=record_id, record=Result(value=7), schema_version=1)
    repeated = repositories.write_result(object(), batch_id=batch_id, record_id=record_id, record=Result(value=7), schema_version=1)

    assert first == repeated
    with pytest.raises(RepositoryError, match="immutable"):
        repositories.write_result(object(), batch_id=batch_id, record_id=record_id, record=Result(value=8), schema_version=1)

    repositories.list_results(batch_id, limit=10)
    assert store.queries == [{"collection": "analysis_batches/batch%2Fone/results", "filters": (), "order_by": (("__name__", "asc"),), "limit": 10, "cursor": None}]
