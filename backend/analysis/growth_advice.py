"""Compose Growth scores, independent guards, and stable catalog rankings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal, Sequence

from backend.analysis.growth_core import GrowthCoreResult, TermResult
from backend.analysis.growth_risk import GrowthRiskResult, GrowthRiskSnapshot
from backend.contracts.analysis import NormalizedPrice, NormalizedSession

GuardStatus = Literal["pass", "fail", "unknown"]
AdviceState = Literal[
    "candidate", "watchlist", "low_score", "review_required", "insufficient_evidence"
]

_RULES_PATH = Path(__file__).with_name("rules") / "growth_v1.json"


@dataclass(frozen=True)
class GrowthRules:
    version: str
    dimension_points: tuple[tuple[str, Decimal], ...]
    candidate_minimum: Decimal
    watchlist_minimum: Decimal
    display_decimal_places: int
    report_max_age_months: int
    price_max_age_sessions: int
    max_net_debt_to_equity: Decimal
    min_current_ratio: Decimal
    min_capital_coverage: Decimal


def load_growth_rules(path: Path = _RULES_PATH) -> GrowthRules:
    """Load the versioned score weights and advisory thresholds."""

    with path.open(encoding="utf-8") as stream:
        raw = json.load(stream)
    advice = raw["advice"]
    guards = raw["guards"]
    return GrowthRules(
        version=raw["version"],
        dimension_points=tuple(
            (name, Decimal(str(points))) for name, points in raw["dimensions"].items()
        ),
        candidate_minimum=Decimal(str(advice["candidate_minimum"])),
        watchlist_minimum=Decimal(str(advice["watchlist_minimum"])),
        display_decimal_places=int(advice["display_decimal_places"]),
        report_max_age_months=int(guards["financial_report_max_age_months"]),
        price_max_age_sessions=int(guards["traded_price_max_age_sessions"]),
        max_net_debt_to_equity=Decimal(str(guards["non_financial_max_net_debt_to_equity"])),
        min_current_ratio=Decimal(str(guards["non_financial_min_current_ratio"])),
        min_capital_coverage=Decimal(str(guards["financial_institution_min_capital_coverage"])),
    )


@dataclass(frozen=True)
class GuardEvidence:
    code: str
    status: GuardStatus
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrowthAdviceInput:
    company_id: str
    symbol: str
    core: GrowthCoreResult
    risk: GrowthRiskResult
    risk_snapshot: GrowthRiskSnapshot
    analysis_time: datetime
    latest_report_known_at: datetime | None
    latest_report_published: bool | None
    prices: tuple[NormalizedPrice, ...]
    sessions: tuple[NormalizedSession, ...]
    event_monitoring: GuardEvidence


@dataclass(frozen=True)
class GrowthDimension:
    status: Literal["assessable", "unavailable"]
    points: Decimal | None
    maximum_points: Decimal
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class GrowthGuard:
    code: str
    status: GuardStatus
    observed: Decimal | date | None
    threshold: Decimal | date | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class GrowthAdvice:
    company_id: str
    symbol: str
    rule_version: str
    dimensions: tuple[tuple[str, GrowthDimension], ...]
    partial_points: Decimal
    overall_score: Decimal | None
    display_score: Decimal | None
    advisory_state: AdviceState
    guards: tuple[GrowthGuard, ...]
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class GrowthRankings:
    ranked: tuple[GrowthAdvice, ...]
    review_required: tuple[GrowthAdvice, ...]
    insufficient_evidence: tuple[GrowthAdvice, ...]
    items: tuple[GrowthAdvice, ...]


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _months_before(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_offset = divmod(month_index, 12)
    month = month_offset + 1
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (next_month - date.resolution).day
    return date(year, month, min(value.day, last_day))


def _growth_dimensions(
    core: GrowthCoreResult, risk: GrowthRiskResult, rules: GrowthRules
) -> tuple[tuple[str, GrowthDimension], ...]:
    terms: dict[str, TermResult] = {
        "activity_growth": core.activity_growth,
        "earnings_growth": core.earnings_growth,
        "profitability": core.profitability,
        "sector_resilience": risk.sector_resilience,
        "earnings_book_valuation": risk.earnings_book_valuation,
    }
    dimensions: list[tuple[str, GrowthDimension]] = []
    for name, maximum in rules.dimension_points:
        term = terms[name]
        if (term.status == "assessable") != (term.points is not None):
            raise ValueError(f"{name} status and points disagree")
        if term.points is not None and not Decimal(0) <= term.points <= maximum:
            raise ValueError(f"{name} points fall outside the approved dimension range")
        dimensions.append((
            name,
            GrowthDimension(
                status=term.status,
                points=term.points,
                maximum_points=maximum,
                evidence_refs=term.evidence_refs,
                reason_codes=term.reason_codes,
            ),
        ))
    return tuple(dimensions)


def _guard(
    code: str,
    status: GuardStatus,
    observed: Decimal | date | None = None,
    threshold: Decimal | date | None = None,
    evidence: Sequence[str] = (),
) -> GrowthGuard:
    return GrowthGuard(code, status, observed, threshold, _dedupe(evidence))


def _price_guard(
    prices: tuple[NormalizedPrice, ...],
    sessions: tuple[NormalizedSession, ...],
    analysis_time: datetime,
    max_age: int,
) -> GrowthGuard:
    known_prices = tuple(
        price for price in prices
        if price.revision.known_at <= analysis_time
        and (price.validated_available_at is None or price.validated_available_at <= analysis_time)
    )
    if not known_prices:
        return _guard("actual_traded_price_freshness", "unknown")
    traded_prices = tuple(price for price in known_prices if price.trade_status == "traded")
    if not traded_prices:
        return _guard("actual_traded_price_freshness", "unknown")
    latest_date = max(price.session_date for price in traded_prices)
    candidates = tuple(price for price in traded_prices if price.session_date == latest_date)
    refs = tuple(ref for price in candidates for ref in (price.revision.provenance.source_id,))
    if len(candidates) != 1:
        return _guard("actual_traded_price_freshness", "unknown", evidence=refs)
    price = candidates[0]
    session_by_date = {session.session_date: session for session in sessions}
    current_sessions = tuple(
        session for session in sessions
        if session.session_date <= analysis_time.date() and session.revision.known_at <= analysis_time
    )
    current = max(current_sessions, key=lambda session: session.session_date) if current_sessions else None
    traded = session_by_date.get(price.session_date)
    if (
        current is None or traded is None or current.session_index is None
        or traded.session_index is None or current.status == "unknown"
        or traded.status == "unknown"
    ):
        return _guard("actual_traded_price_freshness", "unknown", evidence=refs)
    if (
        price.trade_status != "traded" or price.basis != "actual"
        or price.close is None or Decimal(price.close.amount) <= 0
        or price.close_basis != "raw" or price.original_source_date != price.session_date
    ):
        return _guard("actual_traded_price_freshness", "fail", evidence=refs)
    age = current.session_index - traded.session_index
    if age < 0:
        return _guard("actual_traded_price_freshness", "unknown", evidence=refs)
    return _guard(
        "actual_traded_price_freshness",
        "pass" if age <= max_age else "fail",
        Decimal(age), Decimal(max_age), refs,
    )


def _suspension_guard(
    sessions: tuple[NormalizedSession, ...], analysis_time: datetime
) -> GrowthGuard:
    known_sessions = tuple(
        session for session in sessions
        if session.session_date <= analysis_time.date() and session.revision.known_at <= analysis_time
    )
    if not known_sessions:
        return _guard("suspension_status", "unknown")
    current = max(known_sessions, key=lambda session: session.session_date)
    refs = tuple(item.source_id for item in current.source_evidence)
    if current.status == "suspended":
        return _guard("suspension_status", "fail", current.session_date, evidence=refs)
    if current.status == "unknown":
        return _guard("suspension_status", "unknown", current.session_date, evidence=refs)
    return _guard("suspension_status", "pass", current.session_date, evidence=refs)


def _financial_guards(item: GrowthAdviceInput, rules: GrowthRules) -> list[GrowthGuard]:
    snapshot = item.risk_snapshot
    refs = snapshot.evidence_refs
    income, equity = snapshot.ordinary_owner_earnings, snapshot.equity
    income_state: GuardStatus = "unknown" if income is None else ("pass" if income > 0 else "fail")
    equity_state: GuardStatus = "unknown" if equity is None else ("pass" if equity > 0 else "fail")
    period_end = snapshot.period_end
    latest_known = item.latest_report_known_at
    if item.latest_report_published is not True or latest_known is None:
        report_state: GuardStatus = "unknown"
    elif latest_known > item.analysis_time or period_end > item.analysis_time.date():
        report_state = "unknown"
    else:
        cutoff = _months_before(item.analysis_time.date(), rules.report_max_age_months)
        report_state = "pass" if period_end >= cutoff else "fail"
    guards = [
        _guard("positive_latest_ordinary_owner_earnings", income_state, income, Decimal(0), refs),
        _guard("positive_latest_equity", equity_state, equity, Decimal(0), refs),
        _guard(
            "financial_report_freshness", report_state, period_end,
            _months_before(item.analysis_time.date(), rules.report_max_age_months), refs,
        ),
    ]

    if snapshot.category == "non_financial":
        balance = snapshot.balance_sheet
        matched = balance is not None and (
            balance.company_id == snapshot.company_id
            and balance.period_end == snapshot.period_end
            and balance.report_scope == snapshot.report_scope
            and balance.basis_id == snapshot.basis_id
        )
        if not matched or balance is None:
            guards.extend((
                _guard("net_debt_to_equity", "unknown", evidence=refs),
                _guard("current_ratio", "unknown", evidence=refs),
            ))
        else:
            debt, cash = balance.interest_bearing_debt, balance.unrestricted_cash
            current_assets, current_liabilities = balance.current_assets, balance.current_liabilities
            if (
                item.risk.sector_resilience.status != "assessable"
                or debt is None or cash is None or equity is None or equity <= 0
            ):
                guards.append(_guard("net_debt_to_equity", "unknown", evidence=refs + balance.evidence_refs))
            else:
                net_debt_equity = (debt - cash) / equity
                guards.append(_guard(
                    "net_debt_to_equity",
                    "pass" if net_debt_equity <= rules.max_net_debt_to_equity else "fail",
                    net_debt_equity, rules.max_net_debt_to_equity, refs + balance.evidence_refs,
                ))
            if (
                item.risk.sector_resilience.status != "assessable"
                or current_assets is None or current_liabilities is None
            ):
                guards.append(_guard("current_ratio", "unknown", evidence=refs + balance.evidence_refs))
            elif current_liabilities == 0:
                if current_assets > 0:
                    guards.append(_guard(
                        "current_ratio", "pass", None, rules.min_current_ratio,
                        refs + balance.evidence_refs,
                    ))
                else:
                    guards.append(_guard("current_ratio", "unknown", evidence=refs + balance.evidence_refs))
            else:
                current_ratio = current_assets / current_liabilities
                guards.append(_guard(
                    "current_ratio",
                    "pass" if current_ratio >= rules.min_current_ratio else "fail",
                    current_ratio, rules.min_current_ratio, refs + balance.evidence_refs,
                ))
    elif snapshot.category in ("bank", "insurer"):
        coverage = dict(item.risk.sector_resilience.details).get("minimum_regulatory_coverage")
        if item.risk.sector_resilience.status != "assessable" or not isinstance(coverage, Decimal):
            guards.append(_guard("regulatory_capital_coverage", "unknown", evidence=refs))
        else:
            guards.append(_guard(
                "regulatory_capital_coverage",
                "pass" if coverage >= rules.min_capital_coverage else "fail",
                coverage, rules.min_capital_coverage, item.risk.sector_resilience.evidence_refs,
            ))
    else:
        guards.append(_guard("sector_risk_inputs", "unknown", evidence=refs))
    guards.append(_guard(
        item.event_monitoring.code, item.event_monitoring.status,
        evidence=item.event_monitoring.evidence_refs,
    ))
    return guards


def compose_growth_advice(
    item: GrowthAdviceInput, rules: GrowthRules | None = None
) -> GrowthAdvice:
    """Compose dimensions and guard-aware Growth advice for one catalog company."""

    selected_rules = rules or load_growth_rules()
    if item.company_id != item.risk_snapshot.company_id:
        raise ValueError("Growth advice and risk snapshot must identify the same company")
    if item.analysis_time.tzinfo is None or item.analysis_time.utcoffset() != timezone.utc.utcoffset(item.analysis_time):
        raise ValueError("analysis_time must be an explicit UTC instant")
    dimensions = _growth_dimensions(item.core, item.risk, selected_rules)
    partial_points = sum(
        (dimension.points or Decimal(0) for _, dimension in dimensions), Decimal(0)
    )
    complete = all(dimension.status == "assessable" for _, dimension in dimensions)
    overall = partial_points if complete else None
    display = None if overall is None else overall.quantize(
        Decimal(1).scaleb(-selected_rules.display_decimal_places), rounding=ROUND_HALF_UP
    )
    guards = _financial_guards(item, selected_rules)
    guards.append(_price_guard(
        tuple(price for price in item.prices if price.symbol == item.symbol),
        item.sessions, item.analysis_time, selected_rules.price_max_age_sessions,
    ))
    guards.append(_suspension_guard(item.sessions, item.analysis_time))
    failed = any(guard.status == "fail" for guard in guards)
    unknown = any(guard.status == "unknown" for guard in guards)
    if failed:
        state: AdviceState = "review_required"
    elif unknown or overall is None:
        state = "insufficient_evidence"
    elif overall >= selected_rules.candidate_minimum:
        state = "candidate"
    elif overall >= selected_rules.watchlist_minimum:
        state = "watchlist"
    else:
        state = "low_score"
    reasons = _dedupe(
        [reason for _, dimension in dimensions for reason in dimension.reason_codes]
        + [guard.code for guard in guards if guard.status != "pass"]
    )
    return GrowthAdvice(
        item.company_id, item.symbol, selected_rules.version, dimensions,
        partial_points, overall, display, state, tuple(guards), reasons,
        ("event_surveillance_not_comprehensive_v1",),
    )


def rank_growth_catalog(
    companies: Sequence[GrowthAdviceInput], rules: GrowthRules | None = None
) -> GrowthRankings:
    """Retain every catalog company, separating scored and blocked advice states."""

    company_ids = [item.company_id for item in companies]
    symbols = [item.symbol for item in companies]
    if len(company_ids) != len(set(company_ids)) or len(symbols) != len(set(symbols)):
        raise ValueError("Growth catalog company IDs and symbols must be unique")
    advice = tuple(compose_growth_advice(item, rules) for item in companies)
    ranked = tuple(sorted(
        (item for item in advice if item.advisory_state in ("candidate", "watchlist", "low_score")),
        key=lambda item: (-(item.overall_score or Decimal(0)), item.symbol),
    ))
    review = tuple(sorted(
        (item for item in advice if item.advisory_state == "review_required"),
        key=lambda item: item.symbol,
    ))
    insufficient = tuple(sorted(
        (item for item in advice if item.advisory_state == "insufficient_evidence"),
        key=lambda item: item.symbol,
    ))
    all_items = tuple(sorted(advice, key=lambda item: item.symbol))
    if len(ranked) + len(review) + len(insufficient) != len(companies):
        raise AssertionError("every catalog company must appear in exactly one advice group")
    return GrowthRankings(ranked, review, insufficient, all_items)
