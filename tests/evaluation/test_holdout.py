from decimal import Decimal
from pathlib import Path
import importlib.util
import sys

import pytest

spec = importlib.util.spec_from_file_location("holdout", Path(__file__).parents[2] / "evaluation" / "holdout.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["holdout"] = module
spec.loader.exec_module(module)
Observation = module.Observation
evaluate = module.evaluate


def test_holdout_reports_returns_drawdown_turnover_and_coverage() -> None:
    report = evaluate([
        Observation("2026-01-02", "AAA", "buy", Decimal("0.10"), Decimal("0.01"), True),
        Observation("2026-01-03", "AAA", "buy", Decimal("-0.05"), Decimal("0.01"), True),
    ], holdout_sessions=("2026-01-02", "2026-01-03"))
    assert report.return_total == Decimal("0.03")
    assert report.max_drawdown == Decimal("0.06")
    assert report.turnover == 2
    assert report.coverage == Decimal("1")
    assert report.look_ahead_blocked


def test_unknown_next_close_blocks_actionable_evaluation() -> None:
    with pytest.raises(ValueError, match="known-at"):
        evaluate([Observation("2026-01-02", "AAA", "buy", None, Decimal("0"), True)], holdout_sessions=("2026-01-02",))
