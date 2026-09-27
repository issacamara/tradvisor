"""Read-only adapters that keep analytical and paper views bounded."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.contracts.paper import PaperPosition, PortfolioSummary
from backend.publication.analysis import AnalyticalPublisher, ServingStock
from backend.read_api.cursors import CursorClaims, CursorError, decode_cursor, encode_cursor
from backend.store.repositories import MAX_PAGE_SIZE, Page, PaperRepositories


class AnalysisPublisher(Protocol):
    def active_publication(self) -> Any:
        ...

    def read_batch(self, batch_id: str, *, limit: int, cursor: str | None = None) -> Page[ServingStock]:
        ...


@dataclass(frozen=True, slots=True)
class Valuation:
    batch_id: str | None
    session: str | None
    status: str
    values: dict[str, int]


@dataclass(frozen=True, slots=True)
class PortfolioRead:
    summary: PortfolioSummary
    positions: tuple[PaperPosition, ...]
    valuation: Valuation


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


def build_portfolio_read(
    repositories: PaperRepositories,
    *,
    generation: str,
    limit: int = MAX_PAGE_SIZE,
    valuation_batch_id: str | None = None,
    valuation_session: str | None = None,
    valuation_values: dict[str, int] | None = None,
) -> PortfolioRead:
    """Assemble an owner-scoped read; missing prices remain incomplete."""
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    summary = repositories.get_summary(generation)
    if summary is None:
        raise CursorError("portfolio generation is unavailable")
    positions = repositories._page(
        "positions", generation, PaperPosition, limit=limit, cursor=None,
        order_by=(("symbol", "asc"),), filters=(),
    ).items
    values = valuation_values or {}
    complete = all(position.symbol in values for position in positions)
    valuation = Valuation(
        batch_id=valuation_batch_id,
        session=valuation_session,
        status="complete" if complete and positions else "incomplete" if positions else "not_available",
        values=values,
    )
    return PortfolioRead(summary.record, tuple(positions), valuation)
