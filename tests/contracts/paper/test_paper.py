"""Focused tests for the paper records and resource-only REST contracts."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.contracts.analysis import Provenance
from backend.contracts.paper import (
    CashMovement,
    ExecutionPrice,
    PaperCommandReceipt,
    PaperOrder,
    PaperPreferences,
    PortfolioSummary,
)
from backend.contracts.routes import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    PAPER_ROUTES,
    CreatePaperOrderRequest,
    PageRequest,
    PatchPreferencesRequest,
    PortfolioResource,
    ResetPortfolioRequest,
    SetupPortfolioRequest,
)
from backend.contracts.scalars import NonNegativeMoney, SignedMoney, StartingCash

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)


def money(amount: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=amount, currency="XOF")


def summary() -> PortfolioSummary:
    return PortfolioSummary(
        generation="generation-1", starting_cash=StartingCash(amount="1000000", currency="XOF"),
        cash=money("1000000"), reserved_cash=money("0"), pending_order_count=0,
        state_version=0, created_at=NOW, active=True,
    )


def test_setup_order_reset_and_preferences_have_only_approved_client_fields() -> None:
    assert SetupPortfolioRequest(starting_cash=StartingCash(amount="1000000", currency="XOF"), fee_rate_pct="0.5").fee_rate_pct == "0.5"
    assert ResetPortfolioRequest(expected_generation="generation-1", expected_state_version=2, starting_cash=StartingCash(amount="100000", currency="XOF")).starting_cash.amount == "100000.000000"
    assert CreatePaperOrderRequest(
        expected_generation="generation-1", expected_state_version=2, recommendation_ref="recommendation-1",
        batch_id="batch-1", symbol="NSI", side="sell", quantity=3, acknowledge_keep_override=True,
    ).quantity == 3
    assert PatchPreferencesRequest(expected_preference_version=2, objective="dividend").objective == "dividend"
    with pytest.raises(ValidationError):
        SetupPortfolioRequest.model_validate({"starting_cash": {"amount": "100000", "currency": "XOF"}, "fee_rate_pct": "0", "cash": {"amount": "1", "currency": "XOF"}})
    with pytest.raises(ValidationError):
        CreatePaperOrderRequest.model_validate({"expected_generation": "generation-1", "expected_state_version": 0, "recommendation_ref": "rec-1", "batch_id": "batch-1", "symbol": "NSI", "side": "buy", "quantity": 1, "status": "executed"})
    with pytest.raises(ValidationError):
        ResetPortfolioRequest.model_validate({"expected_generation": "generation-1", "expected_state_version": 0, "starting_cash": {"amount": "100000", "currency": "XOF"}, "admission": "allow"})
    with pytest.raises(ValidationError):
        PatchPreferencesRequest.model_validate({"expected_preference_version": 0, "objective": "growth", "generation": "generation-2"})


def test_preferences_and_receipts_preserve_versions_recovery_and_minimal_evidence() -> None:
    preference = PaperPreferences(objective="growth", fee_rate_pct="0", preference_version=4, updated_at=NOW)
    assert preference.model_dump(mode="json")["updated_at"] == "2026-09-22T12:00:00Z"
    receipt = PaperCommandReceipt(
        owner_uid="user-1", idempotency_key="1758542400000.0123456789abcdef0123456789abcdef",
        request_fingerprint="fingerprint-1", recovery_id="recovery-1", operation="setup",
        outcome_id="generation-1", generation="generation-1", state_version=0, http_status=201,
        accepted_at=NOW, expires_at=NOW + timedelta(days=30),
    )
    assert receipt.generation == "generation-1"
    with pytest.raises(ValidationError):
        PaperCommandReceipt.model_validate(receipt.model_dump() | {"expires_at": NOW + timedelta(days=29)})


def test_sell_order_retains_derived_advice_and_ledger_evidence() -> None:
    order = PaperOrder(
        order_id="order-1", owner_uid="user-1", generation="generation-1", recommendation_ref="rec-1", batch_id="batch-1",
        symbol="NSI", side="sell", quantity=2, accepted_at=NOW, intended_session=date(2026, 9, 23),
        grace_deadline_at=NOW + timedelta(days=2), fee_rate_pct="0.5", reserved_sell_quantity=2, status="pending",
        state_version_at_acceptance=3, advice_action_at_acceptance="keep", advice_evaluation_session=date(2026, 9, 22),
        exit_policy_ref="exit-policy-1", is_advice_override=True, acknowledged_keep_override=True,
    )
    assert order.is_advice_override
    evidence = Provenance(source_id="price-source-1", collected_at=NOW, basis="actual")
    price = ExecutionPrice(price_revision_id="price-revision-1", symbol="NSI", session_date=date(2026, 9, 23), close=money("1000"), validated_available_at=NOW, source_evidence=(evidence,))
    assert price.source_evidence[0].source_id == "price-source-1"
    movement = CashMovement(movement_id="opening-generation-1", owner_uid="user-1", generation="generation-1", movement_type="opening_cash", signed_amount=SignedMoney(amount="1000000", currency="XOF"), occurred_at=NOW, processed_at=NOW)
    assert movement.execution_id is None
    with pytest.raises(ValidationError):
        PaperOrder.model_validate(order.model_dump() | {"acknowledged_keep_override": False})


def test_portfolio_and_history_pagination_are_bounded_and_snapshot_aware() -> None:
    assert PageRequest().limit == DEFAULT_PAGE_LIMIT
    assert PageRequest(limit=MAX_PAGE_LIMIT).limit == MAX_PAGE_LIMIT
    with pytest.raises(ValidationError):
        PageRequest(limit=MAX_PAGE_LIMIT + 1)
    unconfigured = PortfolioResource(setup_state="setup_required", summary=None, positions=(), valuation_batch_id=None, valuation_session=None, valuation_status="not_available")
    assert unconfigured.positions == ()
    with pytest.raises(ValidationError):
        PortfolioResource(setup_state="configured", summary=None, positions=(), valuation_batch_id=None, valuation_session=None, valuation_status="not_available")


def test_resource_routes_include_only_read_setup_order_reset_and_preference_operations() -> None:
    routes = {(route.method, route.path, route.success_status) for route in PAPER_ROUTES}
    assert ("POST", "/v1/paper/portfolio", 201) in routes
    assert ("POST", "/v1/paper/orders", 201) in routes
    assert ("POST", "/v1/paper/reset", 200) in routes
    assert ("PATCH", "/v1/me/preferences", 200) in routes
    forbidden = {"/v1/paper/balance", "/v1/paper/positions", "/v1/admission", "/v1/paper/executions"}
    assert not forbidden & {route.path for route in PAPER_ROUTES if route.mutation}
