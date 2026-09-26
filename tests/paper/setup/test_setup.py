from datetime import datetime, timezone

import pytest

from backend.contracts.scalars import StartingCash
from backend.paper.preferences import update_preferences
from backend.paper.service import handle_preferences, handle_setup
from backend.paper.setup import SetupError, create_setup_plan, setup_portfolio
from backend.store.repositories import OwnerContext, PaperRepositories, VersionConflict
from tests.store.test_repositories import FakeStore


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


@pytest.mark.parametrize("amount", ["100000", "100000000"])
def test_setup_accepts_inclusive_cash_boundaries(amount: str) -> None:
    plan = create_setup_plan(
        owner_uid="owner-1",
        starting_cash=cash(amount),
        objective="growth",
        fee_rate_pct="0.25",
        fee_zero_confirmed=False,
        now=NOW,
    )
    assert plan.summary.starting_cash.amount == f"{amount}.000000"


def test_setup_rejects_fractional_cash() -> None:
    with pytest.raises(ValueError, match="whole XOF"):
        cash("100000.500000")


def test_setup_commits_opening_records_atomically_and_rejects_duplicate() -> None:
    store = FakeStore()
    repositories = PaperRepositories(store, OwnerContext(uid="owner-1"))
    first, movement = setup_portfolio(
        repositories,
        starting_cash=cash("100000"),
        objective="growth",
        fee_rate_pct="0.25",
        fee_zero_confirmed=False,
        now=NOW,
    )
    assert repositories.get_control() is not None
    assert repositories.get_preferences() is not None
    assert repositories.get_summary(first.generation) is not None
    assert repositories.get_cash_movement(first.generation, movement.movement_id) is not None
    committed_paths = set(store.documents)

    with pytest.raises(SetupError, match="already configured"):
        setup_portfolio(
            repositories,
            starting_cash=cash("200000"),
            objective="dividend",
            fee_rate_pct="0.25",
            fee_zero_confirmed=False,
            now=NOW,
        )
    assert set(store.documents) == committed_paths


def test_service_handlers_use_repository_boundaries() -> None:
    store = FakeStore()
    repositories = PaperRepositories(store, OwnerContext(uid="owner-1"))
    plan = handle_setup(
        repositories,
        starting_cash=cash("100000"),
        objective="growth",
        fee_rate_pct="0.25",
        fee_zero_confirmed=False,
        now=NOW,
    )
    updated = handle_preferences(
        repositories,
        objective="dividend",
        fee_rate_pct="0.25",
        expected_version=0,
        fee_zero_confirmed=False,
        now=NOW,
    )
    assert plan.control.active_generation == plan.generation
    assert updated.preference_version == 1
    assert repositories.get_preferences().record.objective == "dividend"  # type: ignore[union-attr]


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
