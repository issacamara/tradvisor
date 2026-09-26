"""Pure versioned preference updates for paper portfolios."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from backend.contracts.paper import PREFERENCE_OBJECTIVE, PaperPreferences
from backend.store.repositories import VersionConflict


def update_preferences(
    current: PaperPreferences | None,
    *,
    objective: str,
    fee_rate_pct: str,
    now: datetime,
    expected_version: int,
    fee_zero_confirmed: bool,
) -> PaperPreferences:
    """Create the next immutable preference value after an optimistic check."""

    actual = None if current is None else current.preference_version
    if actual != expected_version:
        raise VersionConflict(f"expected preference version {expected_version}, found {actual}")
    if fee_rate_pct == "0" and not fee_zero_confirmed:
        raise ValueError("zero fee requires explicit confirmation")
    return PaperPreferences(
        objective=cast(PREFERENCE_OBJECTIVE, objective),
        fee_rate_pct=fee_rate_pct,
        preference_version=expected_version + 1,
        updated_at=now,
    )
