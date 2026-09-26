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


def reconcile_restore(
    reconciliation: Reconciliation,
    *,
    current_recovery_id: str,
    restored_orders: Iterable[RestoredPendingOrder],
) -> RestoreDecision:
    """Require complete inventory and reject each old pending order once."""
    if reconciliation.globally_blocked:
        return RestoreDecision(False, f"recovery-{uuid4().hex}", (), reconciliation.global_reasons)
    fresh = f"recovery-{uuid4().hex}"
    rejected: list[str] = []
    reasons: list[str] = []
    for order in restored_orders:
        if order.status != "pending":
            continue
        if order.recovery_id != current_recovery_id:
            rejected.append(order.order_id)
            reasons.append(f"{order.order_id}:stale_recovery")
    return RestoreDecision(True, fresh, tuple(rejected), tuple(reasons))
