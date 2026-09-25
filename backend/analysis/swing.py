"""Versioned Swing trend-confirmation strategy composition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

from backend.analysis.atr import AtrSeries
from backend.analysis.ema import EmaSeries
from backend.analysis.inputs import AnalyticalInputSnapshot
from backend.analysis.liquidity import CurrentTradeGate, LiquidityResult
from backend.analysis.rsi import RsiSeries

GuardStatus = Literal["pass", "fail", "unknown"]
SwingDecision = Literal["buy", "not_buy", "unavailable"]
_RULES_PATH = Path(__file__).with_name("rules") / "swing_v1.json"


@dataclass(frozen=True)
class SwingRules:
    version: str
    strategy_id: str
    alignment_points: Decimal
    direction_points: Decimal
    rsi_points: Decimal
    extension_points: Decimal
    buy_minimum: Decimal
    display_decimal_places: int
    alignment_saturation_atr: Decimal
    direction_saturation_atr: Decimal
    rsi_curve: tuple[tuple[Decimal, Decimal], ...]
    extension_full_credit_atr: Decimal
    extension_zero_credit_atr: Decimal
    liquidity_window_sessions: int
    minimum_median_xof: Decimal
    minimum_traded_sessions: int


@dataclass(frozen=True)
class SwingStrategyInput:
    snapshot: AnalyticalInputSnapshot
    ema20: EmaSeries
    ema50: EmaSeries
    rsi14: RsiSeries
    atr14: AtrSeries
    liquidity: LiquidityResult
    current_trade: CurrentTradeGate


@dataclass(frozen=True)
class SwingGuard:
    code: str
    status: GuardStatus
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class SwingScore:
    alignment: Decimal
    direction: Decimal
    rsi: Decimal
    extension: Decimal
    total: Decimal
    display_total: Decimal


@dataclass(frozen=True)
class SwingResult:
    strategy_id: str
    rule_version: str
    rule_reference: str
    input_snapshot_id: str
    session_id: str
    decision: SwingDecision
    score: SwingScore | None
    threshold: Decimal
    guards: tuple[SwingGuard, ...]
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    indicator_rule_refs: tuple[str, ...]


def load_swing_rules(path: Path = _RULES_PATH) -> SwingRules:
    """Load the immutable V1 strategy definition."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    score = raw["score"]
    liquidity = raw["liquidity"]
    return SwingRules(
        version=raw["version"],
        strategy_id=raw["strategy_id"],
        alignment_points=Decimal(str(score["alignment_points"])),
        direction_points=Decimal(str(score["direction_points"])),
        rsi_points=Decimal(str(score["rsi_points"])),
        extension_points=Decimal(str(score["extension_points"])),
        buy_minimum=Decimal(str(score["buy_minimum"])),
        display_decimal_places=int(score["display_decimal_places"]),
        alignment_saturation_atr=Decimal(str(score["alignment_saturation_atr"])),
        direction_saturation_atr=Decimal(str(score["direction_saturation_atr"])),
        rsi_curve=tuple(
            (Decimal(str(value)), Decimal(str(points)))
            for value, points in score["rsi_curve"]
        ),
        extension_full_credit_atr=Decimal(str(score["extension_full_credit_atr"])),
        extension_zero_credit_atr=Decimal(str(score["extension_zero_credit_atr"])),
        liquidity_window_sessions=int(liquidity["window_sessions"]),
        minimum_median_xof=Decimal(str(liquidity["minimum_median_xof"])),
        minimum_traded_sessions=int(liquidity["minimum_traded_sessions"]),
    )


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _clamp(value: Decimal) -> Decimal:
    return min(Decimal(1), max(Decimal(0), value))


def _rsi_contribution(value: Decimal, rules: SwingRules) -> Decimal:
    curve = rules.rsi_curve
    if value < curve[0][0] or value > curve[-1][0]:
        return Decimal(0)
    for (left_x, left_y), (right_x, right_y) in zip(curve, curve[1:]):
        if left_x <= value <= right_x:
            if left_y == right_y:
                return left_y
            return left_y + (value - left_x) * (right_y - left_y) / (right_x - left_x)
    return Decimal(0)


def _extension_contribution(value: Decimal, rules: SwingRules) -> Decimal:
    if value < 0:
        return Decimal(0)
    if value <= rules.extension_full_credit_atr:
        return rules.extension_points
    if value < rules.extension_zero_credit_atr:
        span = rules.extension_zero_credit_atr - rules.extension_full_credit_atr
        return rules.extension_points * (rules.extension_zero_credit_atr - value) / span
    return Decimal(0)


def _guard(code: str, status: GuardStatus, refs: tuple[str, ...], *reasons: str) -> SwingGuard:
    return SwingGuard(code, status, refs, tuple(dict.fromkeys(reasons)))


def evaluate_swing(
    item: SwingStrategyInput, *, rules: SwingRules | None = None
) -> SwingResult:
    """Score one snapshot and apply independent eligibility guards."""

    config = load_swing_rules() if rules is None else rules
    snapshot = item.snapshot
    if not snapshot.sessions:
        return _unavailable(item, config, "history_incomplete")

    series = (item.ema20, item.ema50, item.rsi14, item.atr14)
    if any(value.input_snapshot_id != snapshot.snapshot_id for value in series):
        raise ValueError("indicator series must share the strategy input snapshot")
    if item.liquidity.input_snapshot_id != snapshot.snapshot_id:
        raise ValueError("liquidity result must share the strategy input snapshot")
    if item.ema20.period != 20 or item.ema50.period != 50:
        raise ValueError("strategy requires the approved EMA20 and EMA50 series")

    current = snapshot.sessions[-1]
    selected = []
    for points in (item.ema20.points, item.ema50.points, item.rsi14.points, item.atr14.points):
        matching = [point for point in points if point.session_id == current.session_id]
        if len(matching) != 1:
            return _unavailable(item, config, "indicator_point_missing")
        selected.append(matching[0])
    ema_fast, ema_slow, rsi, atr = selected

    previous_points = [
        point for point in item.ema20.points
        if point.session_index == current.session_index - 5
    ]
    required_points = (ema_fast, ema_slow, rsi, atr)
    values = (
        _decimal(ema_fast.value), _decimal(ema_slow.value),
        _decimal(rsi.value), _decimal(atr.value),
    )
    if (
        any(point.status != "assessable" for point in required_points)
        or any(value is None for value in values)
        or not previous_points
        or previous_points[-1].status != "assessable"
        or previous_points[-1].value is None
    ):
        return _unavailable(item, config, "required_indicator_unavailable")

    fast, slow, rsi_value, atr_value = values
    assert fast is not None and slow is not None and rsi_value is not None and atr_value is not None
    if atr_value <= 0:
        return _unavailable(item, config, "atr_not_positive")
    close = (
        None
        if current.close_micros is None
        else Decimal(current.close_micros) / Decimal(1_000_000)
    )
    previous_fast = _decimal(previous_points[-1].value)
    if close is None or previous_fast is None:
        return _unavailable(item, config, "required_indicator_unavailable")

    alignment_ratio = (fast - slow) / atr_value
    direction_ratio = (fast - previous_fast) / atr_value
    extension_ratio = (close - fast) / atr_value
    alignment = config.alignment_points * _clamp(alignment_ratio / config.alignment_saturation_atr)
    direction = config.direction_points * _clamp(direction_ratio / config.direction_saturation_atr)
    rsi_points = _rsi_contribution(rsi_value, config)
    extension = _extension_contribution(extension_ratio, config)
    total = alignment + direction + rsi_points + extension
    quantum = Decimal(1).scaleb(-config.display_decimal_places)
    display_total = total.quantize(quantum, rounding=ROUND_HALF_UP)

    refs = tuple(dict.fromkeys((
        str(snapshot.snapshot_id), str(current.session_id),
        *item.liquidity.evidence_refs, *item.current_trade.evidence_refs,
    )))
    liquidity_assessable = (
        item.liquidity.status == "assessable"
        and item.liquidity.median_xof is not None
        and item.liquidity.traded_session_count is not None
    )
    if liquidity_assessable:
        median = item.liquidity.median_xof
        traded_count = item.liquidity.traded_session_count
        assert median is not None and traded_count is not None
        liquidity_eligible = (
            median >= config.minimum_median_xof
            and traded_count >= config.minimum_traded_sessions
        )
        if item.liquidity.eligible is not None and item.liquidity.eligible != liquidity_eligible:
            raise ValueError("liquidity eligibility conflicts with the versioned strategy thresholds")
        liquidity_status: GuardStatus = "pass" if liquidity_eligible else "fail"
        liquidity_reasons = item.liquidity.reason_codes or (
            () if liquidity_eligible else ("liquidity_threshold_not_met",)
        )
    else:
        liquidity_status = "unknown"
        liquidity_reasons = item.liquidity.reason_codes or ("liquidity_evidence_unavailable",)

    guards = (
        _guard(
            "liquidity_eligibility",
            liquidity_status,
            tuple(map(str, item.liquidity.evidence_refs)),
            *liquidity_reasons,
        ),
        _guard(
            "current_trade_eligibility", item.current_trade.status,
            tuple(map(str, item.current_trade.evidence_refs)),
            *(item.current_trade.reason_codes or (
                () if item.current_trade.status == "pass" else ("current_trade_gate_not_passed",)
            )),
        ),
        _guard("ema20_above_ema50", "pass" if fast > slow else "fail", refs,
               *(() if fast > slow else ("ema20_not_above_ema50",))),
        _guard("close_at_or_above_ema20", "pass" if close >= fast else "fail", refs,
               *(() if close >= fast else ("close_below_ema20",))),
        _guard("ema20_rising_over_five_sessions", "pass" if fast > previous_fast else "fail", refs,
               *(() if fast > previous_fast else ("ema20_not_rising",))),
        _guard("extension_below_three_atr", "pass" if extension_ratio < config.extension_zero_credit_atr else "fail", refs,
               *(() if extension_ratio < config.extension_zero_credit_atr else ("extension_at_or_above_three_atr",))),
    )
    reason_codes = list(reason for guard in guards for reason in guard.reason_codes)
    if total < config.buy_minimum:
        reason_codes.append("score_below_buy_threshold")
    statuses = {guard.status for guard in guards}
    decision: SwingDecision
    if "fail" in statuses:
        decision = "not_buy"
    elif "unknown" in statuses:
        decision = "unavailable"
    elif total >= config.buy_minimum:
        decision = "buy"
    else:
        decision = "not_buy"

    return SwingResult(
        config.strategy_id, config.version, config.version, str(snapshot.snapshot_id),
        str(current.session_id), decision,
        SwingScore(alignment, direction, rsi_points, extension, total, display_total),
        config.buy_minimum, guards, tuple(dict.fromkeys(reason_codes)), refs,
        tuple(dict.fromkeys(str(series_item.rule_version) for series_item in series)),
    )


def _unavailable(item: SwingStrategyInput, rules: SwingRules, reason: str) -> SwingResult:
    snapshot_id = str(item.snapshot.snapshot_id)
    evidence = (snapshot_id,)
    return SwingResult(
        rules.strategy_id, rules.version, rules.version, snapshot_id,
        str(item.snapshot.sessions[-1].session_id) if item.snapshot.sessions else "",
        "unavailable", None, rules.buy_minimum,
        (_guard("required_indicators", "unknown", evidence, reason),),
        (reason,), evidence, (),
    )
