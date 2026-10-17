"""Fail-closed reconciliation of isolated restored state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

from backend.recovery.register import Reconciliation


@dataclass(frozen=True, slots=True)
class RestoredPendingOrder:
    order_id: str
    recovery_id: str
    status: str
    reserved_cash: int = 0
    reserved_shares: int = 0


@dataclass(frozen=True, slots=True)
class RestoreDecision:
    allowed: bool
    recovery_id: str
    rejected_orders: tuple[str, ...]
    reasons: tuple[str, ...]
    released_cash: int = 0
    released_shares: int = 0


def reconcile_restore(
    reconciliation: Reconciliation,
    *,
    current_recovery_id: str,
    subject: str | None = None,
    restored_orders: Iterable[RestoredPendingOrder],
) -> RestoreDecision:
    """Require complete inventory and reject each old pending order once."""
    if reconciliation.globally_blocked:
        return RestoreDecision(False, f"recovery-{uuid4().hex}", (), reconciliation.global_reasons)
    if subject is not None and subject in reconciliation.blocked_subjects:
        blocked_reasons = tuple(reason for owner, reason in reconciliation.subject_reasons if owner == subject)
        return RestoreDecision(False, f"recovery-{uuid4().hex}", (), blocked_reasons)
    fresh = f"recovery-{uuid4().hex}"
    rejected: list[str] = []
    reasons: list[str] = []
    released_cash = 0
    released_shares = 0
    for order in restored_orders:
        if order.status != "pending":
            continue
        rejected.append(order.order_id)
        reason = "stale_recovery" if order.recovery_id != current_recovery_id else "restored_pending"
        reasons.append(f"{order.order_id}:{reason}")
        released_cash += order.reserved_cash
        released_shares += order.reserved_shares
    return RestoreDecision(True, fresh, tuple(rejected), tuple(reasons), released_cash, released_shares)
