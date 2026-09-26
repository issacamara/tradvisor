from backend.recovery.register import Reconciliation
from backend.recovery.restore import RestoredPendingOrder, reconcile_restore


def test_restore_blocks_incomplete_inventory_and_rejects_stale_pending_once() -> None:
    blocked = reconcile_restore(
        Reconciliation(True, ("missing inventory",), frozenset(), ()),
        current_recovery_id="r1", restored_orders=(),
    )
    assert not blocked.allowed
    decision = reconcile_restore(
        Reconciliation(False, (), frozenset(), ()),
        current_recovery_id="r1",
        restored_orders=(RestoredPendingOrder("o1", "old", "pending"), RestoredPendingOrder("o2", "r1", "executed")),
    )
    assert decision.allowed
    assert decision.rejected_orders == ("o1",)
    assert decision.recovery_id != "r1"
