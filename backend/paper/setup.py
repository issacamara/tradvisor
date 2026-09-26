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
from backend.contracts.scalars import FeeRatePct, OpaqueIdentifier, StartingCash


class SetupError(ValueError):
    """Raised when setup would violate the paper portfolio contract."""


@dataclass(frozen=True, slots=True)
class SetupPlan:
    generation: OpaqueIdentifier
    recovery_id: OpaqueIdentifier
    control: PortfolioControl
    preferences: PaperPreferences
    summary: PortfolioSummary


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
