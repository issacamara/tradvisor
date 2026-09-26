"""Owner-scoped service seams for paper setup and preference mutations."""

from __future__ import annotations

from datetime import datetime

from backend.contracts.paper import PaperPreferences
from backend.contracts.scalars import FeeRatePct, StartingCash
from backend.paper.preferences import update_preferences
from backend.paper.setup import SetupPlan, setup_portfolio
from backend.store.repositories import PaperRepositories, WriteRequest
from backend.store.transactions import Transaction


def handle_setup(
    repositories: PaperRepositories,
    *,
    starting_cash: StartingCash,
    objective: str,
    fee_rate_pct: FeeRatePct,
    fee_zero_confirmed: bool,
    now: datetime,
) -> SetupPlan:
    """Apply the validated setup command through the atomic repository boundary."""

    plan, _ = setup_portfolio(
        repositories,
        starting_cash=starting_cash,
        objective=objective,
        fee_rate_pct=fee_rate_pct,
        fee_zero_confirmed=fee_zero_confirmed,
        now=now,
    )
    return plan


def handle_preferences(
    repositories: PaperRepositories,
    *,
    objective: str,
    fee_rate_pct: FeeRatePct,
    expected_version: int,
    fee_zero_confirmed: bool,
    now: datetime,
) -> PaperPreferences:
    """Version and persist preferences without touching active portfolio cash or orders."""

    current_document = repositories.get_preferences()
    current = None if current_document is None else current_document.record
    updated = update_preferences(
        current,
        objective=objective,
        fee_rate_pct=fee_rate_pct,
        now=now,
        expected_version=expected_version,
        fee_zero_confirmed=fee_zero_confirmed,
    )

    def transact(transaction: Transaction) -> None:
        repositories.write_many_in_transaction(
            transaction,
            requests=(
                WriteRequest(
                    key=repositories.preferences_key(),
                    record=updated,
                    schema_version=1,
                    expected_state_version=(
                        None if current_document is None else current_document.state_version
                    ),
                ),
            ),
        )

    repositories.transact(transact)
    return updated


__all__ = ["handle_preferences", "handle_setup"]
