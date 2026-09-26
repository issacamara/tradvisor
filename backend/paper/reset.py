"""Atomic, recovery-fenced replacement of a paper portfolio generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import uuid4

from backend.commands.receipts import ReceiptOutcome, ReceiptResult, execute_with_receipt, fingerprint_request
from backend.contracts.paper import CashMovement, PREFERENCE_OBJECTIVE, PaperPreferences, PortfolioControl, PortfolioSummary
from backend.contracts.routes import ResetPortfolioRequest
from backend.contracts.scalars import OpaqueIdentifier, SignedMoney
from backend.paper.setup import create_setup_plan
from backend.store.repositories import PaperRepositories, VersionConflict, WriteRequest
from backend.store.transactions import Transaction


class ResetError(ValueError):
    """Raised when a reset cannot safely replace the active generation."""


@dataclass(frozen=True, slots=True)
class ResetResult:
    generation: OpaqueIdentifier
    recovery_id: OpaqueIdentifier
    summary: PortfolioSummary
    receipt: ReceiptResult


def reset_portfolio(
    repositories: PaperRepositories,
    request: ResetPortfolioRequest,
    *,
    now: datetime,
    generation: OpaqueIdentifier | None = None,
    recovery_id: OpaqueIdentifier | None = None,
) -> ResetResult:
    """Commit a fresh generation while fencing every prior order and position.

    The receipt and all control/generation writes share one transaction. A retry
    therefore replays the same committed reset instead of creating another one.
    """

    fingerprint = fingerprint_request("POST", "/v1/paper/reset", request)
    selected_generation = generation or f"generation-{uuid4().hex}"
    store = repositories._store
    plan = None

    def apply(transaction: Transaction) -> ReceiptOutcome:
        nonlocal plan
        control_doc = store.get_in_transaction(transaction, repositories.control_key())
        preferences_doc = store.get_in_transaction(transaction, repositories.preferences_key())
        if control_doc is None or preferences_doc is None:
            raise ResetError("paper portfolio is not configured")
        control = cast(PortfolioControl, control_doc.record)
        selected_recovery = recovery_id or control.recovery_id
        if control.active_generation != request.expected_generation:
            raise ResetError("expected portfolio generation is no longer active")
        if control.state_version != request.expected_state_version:
            raise VersionConflict(
                f"expected state version {request.expected_state_version}, found {control.state_version}"
            )
        preferences = cast(PaperPreferences, preferences_doc.record)
        objective = cast(PREFERENCE_OBJECTIVE, str(preferences.objective))
        plan = create_setup_plan(
            owner_uid=repositories.owner_uid,
            starting_cash=request.starting_cash,
            objective=objective,
            fee_rate_pct=preferences.fee_rate_pct,
            fee_zero_confirmed=True,
            now=now,
            generation=selected_generation,
            recovery_id=selected_recovery,
        )
        next_control = plan.control.model_copy(
            update={
                "state_version": control.state_version + 1,
                "preference_version": control.preference_version,
            }
        )
        movement = CashMovement(
            movement_id=f"opening-{plan.generation}",
            owner_uid=plan.control.owner_uid,
            generation=plan.generation,
            movement_type="opening_cash",
            signed_amount=SignedMoney(amount=request.starting_cash.amount, currency="XOF"),
            occurred_at=now,
            processed_at=now,
        )
        # Advance the control document first in the transaction. The repository
        # then observes the new active generation before accepting its records.
        repositories.write_many_in_transaction(
            transaction,
            requests=(WriteRequest(repositories.control_key(), next_control, 1, control_doc.state_version),),
        )
        repositories.write_many_in_transaction(
            transaction,
            requests=(
                WriteRequest(repositories.generation_key(plan.generation), plan.summary, 1, None),
                WriteRequest(
                    repositories.cash_movement_key(plan.generation, movement.movement_id),
                    movement,
                    1,
                    None,
                ),
            ),
        )
        return ReceiptOutcome(
            operation=f"reset-{plan.generation}",
            outcome_id=plan.generation,
            generation=plan.generation,
            state_version=next_control.state_version,
            http_status=200,
        )

    receipt = execute_with_receipt(
        store,
        repositories,
        request.command,
        fingerprint,
        now=now,
        apply_mutation=apply,
    )
    if plan is None:
        replay_generation = receipt.receipt.generation
        if replay_generation is None:
            raise ResetError("reset replay did not identify its replacement generation")
        summary_doc = repositories.get_summary(replay_generation)
        control_doc = repositories.get_control()
        if summary_doc is None or control_doc is None:
            raise ResetError("reset replay could not load its committed replacement")
        return ResetResult(
            replay_generation,
            control_doc.record.recovery_id,
            summary_doc.record,
            receipt,
        )
    return ResetResult(plan.generation, plan.recovery_id, plan.summary, receipt)
