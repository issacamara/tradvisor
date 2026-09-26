from datetime import datetime, timezone

import pytest

from backend.contracts.scalars import StartingCash
from backend.paper.preferences import update_preferences
from backend.paper.setup import SetupError, create_setup_plan
from backend.store.repositories import VersionConflict


NOW = datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)


def cash(amount: str) -> StartingCash:
    return StartingCash(amount=amount, currency="XOF")


def test_setup_plan_preserves_exact_cash_and_starts_empty_reservations() -> None:
    plan = create_setup_plan(
        owner_uid="owner-1",
        starting_cash=cash("100000"),
        objective="growth",
        fee_rate_pct="0.25",
        fee_zero_confirmed=False,
        now=NOW,
    )

    assert plan.summary.starting_cash.amount == "100000.000000"
    assert plan.summary.cash == plan.summary.starting_cash
    assert plan.summary.reserved_cash.amount == "0.000000"
    assert plan.summary.pending_order_count == 0


def test_zero_fee_requires_explicit_selection_and_versions_are_serialized() -> None:
    with pytest.raises(SetupError, match="explicit confirmation"):
        create_setup_plan(
            owner_uid="owner-1",
            starting_cash=cash("100000"),
            objective="dividend",
            fee_rate_pct="0",
            fee_zero_confirmed=False,
            now=NOW,
        )

    plan = create_setup_plan(
        owner_uid="owner-1",
        starting_cash=cash("100000"),
        objective="dividend",
        fee_rate_pct="0",
        fee_zero_confirmed=True,
        now=NOW,
    )
    assert plan.control.preference_version == 0
    assert plan.preferences.preference_version == 0


def test_preference_update_rejects_stale_version_and_allows_next_version() -> None:
    plan = create_setup_plan(
        owner_uid="owner-1",
        starting_cash=cash("100000"),
        objective="growth",
        fee_rate_pct="0.25",
        fee_zero_confirmed=False,
        now=NOW,
    )
    with pytest.raises(VersionConflict):
        update_preferences(
            plan.preferences,
            objective="dividend",
            fee_rate_pct="0.25",
            now=NOW,
            expected_version=1,
            fee_zero_confirmed=False,
        )

    updated = update_preferences(
        plan.preferences,
        objective="dividend",
        fee_rate_pct="0.25",
        now=NOW,
        expected_version=0,
        fee_zero_confirmed=False,
    )
    assert updated.preference_version == 1
