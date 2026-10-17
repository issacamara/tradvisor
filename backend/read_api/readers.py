"""Read-only adapters that keep analytical serving reads bounded."""

from __future__ import annotations

from typing import Any, Protocol

from backend.publication.analysis import AnalyticalPublisher, ServingStock
from backend.read_api.cursors import CursorClaims, CursorError, decode_cursor, encode_cursor
from backend.store.repositories import MAX_PAGE_SIZE, Page
class AnalysisPublisher(Protocol):
    def active_publication(self) -> Any:
        ...

    def read_batch(self, batch_id: str, *, limit: int, cursor: str | None = None) -> Page[ServingStock]:
        ...


def read_analysis_page(
    publisher: AnalysisPublisher,
    *,
    batch_id: str,
    limit: int,
    cursor: str | None,
    cursor_secret: bytes,
    now: Any,
) -> tuple[Page[ServingStock], str | None]:
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    store_cursor = None
    if cursor is not None:
        claims = decode_cursor(cursor, cursor_secret, now=now, scope="analysis", batch_id=batch_id)
        store_cursor = claims.last_key
    page = publisher.read_batch(batch_id, limit=limit, cursor=store_cursor)
    next_cursor = None
    if page.next_cursor is not None:
        next_cursor = encode_cursor(
            CursorClaims("analysis", None, None, None, batch_id, page.next_cursor, now), cursor_secret
        )
    return page, next_cursor
