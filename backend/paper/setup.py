"""Validated paper-portfolio setup planning.

The planner is deliberately side-effect free; the API/storage adapter can apply
its records in one transaction after validating duplicate setup and versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import uuid4

from backend.contracts.paper import PREFERENCE_OBJECTIVE, PaperPreferences, PortfolioControl, PortfolioSummary
from backend.contracts.paper import CashMovement
from backend.contracts.scalars import SignedMoney
from backend.contracts.scalars import FeeRatePct, OpaqueIdentifier, StartingCash
from backend.store.repositories import DocumentKey, PaperRepositories, WriteRequest
from backend.store.transactions import Transaction


class SetupError(ValueError):
    """Raised when setup would violate the paper portfolio contract."""


@dataclass(frozen=True, slots=True)
class SetupPlan:
    generation: OpaqueIdentifier
    recovery_id: OpaqueIdentifier
    control: PortfolioControl
    preferences: PaperPreferences
    summary: PortfolioSummary


def setup_portfolio(
    repositories: PaperRepositories,
    *,
    starting_cash: StartingCash,
    objective: str,
    fee_rate_pct: FeeRatePct,
    fee_zero_confirmed: bool,
    now: datetime,
) -> tuple[SetupPlan, CashMovement]:
    """Atomically create control, preferences, opening balance, and summary."""

    plan = create_setup_plan(
        owner_uid=repositories.owner_uid,
        starting_cash=starting_cash,
        objective=objective,
        fee_rate_pct=fee_rate_pct,
        fee_zero_confirmed=fee_zero_confirmed,
        now=now,
    )
    movement = CashMovement(
        movement_id=f"opening-{plan.generation}",
        owner_uid=plan.control.owner_uid,
        generation=plan.generation,
        movement_type="opening_cash",
        signed_amount=SignedMoney(amount=starting_cash.amount, currency="XOF"),
        occurred_at=now,
        processed_at=now,
    )

    def transact(transaction: Transaction) -> None:
        existing = repositories._store.get_in_transaction(transaction, repositories.control_key())
        if existing is not None:
            raise SetupError("paper portfolio is already configured")
        repositories.write_many_in_transaction(
            transaction,
            requests=(
                _request(repositories.control_key(), plan.control),
                _request(repositories.preferences_key(), plan.preferences),
            ),
        )
        repositories.write_many_in_transaction(
            transaction,
            requests=(
                _request(repositories.generation_key(plan.generation), plan.summary),
                _request(repositories.cash_movement_key(plan.generation, movement.movement_id), movement),
            ),
        )

    repositories.transact(transact)
    return plan, movement


def _request(key: DocumentKey, record: object) -> WriteRequest:
    from pydantic import BaseModel

    if not isinstance(record, BaseModel):
        raise TypeError("setup record must be a Pydantic model")
    return WriteRequest(key=key, record=record, schema_version=1, expected_state_version=None)


def create_setup_plan(
    *,
    owner_uid: OpaqueIdentifier,
    starting_cash: StartingCash,
    objective: str,
    fee_rate_pct: FeeRatePct,
    fee_zero_confirmed: bool,
    now: datetime,
    generation: OpaqueIdentifier | None = None,
    recovery_id: OpaqueIdentifier | None = None,
) -> SetupPlan:
    """Build the three records required for an atomic first setup."""

    if fee_rate_pct == "0" and not fee_zero_confirmed:
        raise SetupError("zero fee requires explicit confirmation")
    if objective not in {"growth", "dividend"}:
        raise SetupError("objective must be growth or dividend")
    generation = generation or f"generation-{uuid4().hex}"
    recovery_id = recovery_id or f"recovery-{uuid4().hex}"
    preferences = PaperPreferences(
        objective=cast(PREFERENCE_OBJECTIVE, objective),
        fee_rate_pct=fee_rate_pct,
        preference_version=0,
        updated_at=now,
    )
    control = PortfolioControl(
        owner_uid=owner_uid,
        active_generation=generation,
        configured_fee_rate_pct=fee_rate_pct,
        state_version=0,
        preference_version=0,
        recovery_id=recovery_id,
        updated_at=now,
    )
    summary = PortfolioSummary(
        generation=generation,
        starting_cash=starting_cash,
        cash=starting_cash,
        reserved_cash=starting_cash.model_copy(update={"amount": "0.000000"}),
        pending_order_count=0,
        state_version=0,
        created_at=now,
        active=True,
    )
    return SetupPlan(generation, recovery_id, control, preferences, summary)
