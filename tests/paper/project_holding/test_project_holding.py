from datetime import date, datetime, timezone

from backend.contracts.paper import PaperPosition
from backend.contracts.scalars import NonNegativeMoney
from backend.paper.holding_advice import FrozenExitPolicy
from backend.paper.project_holding import advance_holding


def test_closed_or_late_projection_does_not_regress_position() -> None:
    position = PaperPosition(
        generation="g1", symbol="ABC", quantity=1, reserved_sell_quantity=0,
        remaining_gross_cost=NonNegativeMoney(amount="100", currency="XOF"),
        purchase_fees=NonNegativeMoney(amount="0", currency="XOF"),
        opening_session=date(2026, 1, 1), high_water_close=NonNegativeMoney(amount="120", currency="XOF"),
        evaluated_through_session=date(2026, 1, 5), trail_activated=True, exit_policy_ref="other-policy",
    )
    projection = advance_holding(
        position, active_generation="g1", current_state_version=3,
        inputs=type("Inputs", (), {"symbol": "ABC", "snapshot_id": "s1", "sessions": ()})(),
        ema20=type("Series", (), {"input_snapshot_id": "s1", "period": 20, "points": ()})(),
        ema50=type("Series", (), {"input_snapshot_id": "s1", "period": 50, "points": ()})(),
        rsi14=type("Series", (), {"input_snapshot_id": "s1", "period": 14, "points": ()})(),
        evaluation_session=date(2026, 1, 4), policy=FrozenExitPolicy("exit-policy-v1"),
    )
    assert projection.position == position
