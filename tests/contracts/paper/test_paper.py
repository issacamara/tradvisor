"""Focused tests for the paper records and resource-only REST contracts."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.contracts.analysis import Provenance
from backend.contracts.envelopes import CommandMetadata
from backend.contracts.paper import (
    CalendarCorrectionEvidence,
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
    canonical_command_fingerprint,
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


def command(**overrides: object) -> CommandMetadata:
    values: dict[str, object] = {
        "idempotency_key": "1758542400000.0123456789abcdef0123456789abcdef",
        "recovery_id": "recovery-1",
        "content_length": 128,
        "issued_at": NOW,
    }
    values.update(overrides)
    return CommandMetadata.model_validate(values)


def test_setup_order_reset_and_preferences_have_only_approved_client_fields() -> None:
    assert SetupPortfolioRequest(command=command(), starting_cash=StartingCash(amount="1000000", currency="XOF"), fee_rate_pct="0.5").fee_rate_pct == "0.5"
    assert ResetPortfolioRequest(command=command(expected_generation="generation-1", expected_state_version=2), expected_generation="generation-1", expected_state_version=2, starting_cash=StartingCash(amount="100000", currency="XOF")).starting_cash.amount == "100000.000000"
    assert CreatePaperOrderRequest(
        command=command(expected_generation="generation-1", expected_state_version=2), expected_generation="generation-1", expected_state_version=2, recommendation_ref="recommendation-1",
        batch_id="batch-1", symbol="NSI", side="sell", quantity=3, acknowledge_keep_override=True,
    ).quantity == 3
    assert PatchPreferencesRequest(command=command(), expected_preference_version=2, objective="dividend").objective == "dividend"
    with pytest.raises(ValidationError):
        SetupPortfolioRequest.model_validate({"starting_cash": {"amount": "100000", "currency": "XOF"}, "fee_rate_pct": "0", "cash": {"amount": "1", "currency": "XOF"}})
    with pytest.raises(ValidationError):
        CreatePaperOrderRequest.model_validate({"expected_generation": "generation-1", "expected_state_version": 0, "recommendation_ref": "rec-1", "batch_id": "batch-1", "symbol": "NSI", "side": "buy", "quantity": 1, "status": "executed"})
    with pytest.raises(ValidationError):
        ResetPortfolioRequest.model_validate({"expected_generation": "generation-1", "expected_state_version": 0, "starting_cash": {"amount": "100000", "currency": "XOF"}, "admission": "allow"})
    with pytest.raises(ValidationError):
        PatchPreferencesRequest.model_validate({"expected_preference_version": 0, "objective": "growth", "generation": "generation-2"})
    for request_type in (PatchPreferencesRequest, SetupPortfolioRequest, CreatePaperOrderRequest, ResetPortfolioRequest):
        assert "command" in request_type.model_json_schema()["required"]
    with pytest.raises(ValidationError):
        CreatePaperOrderRequest(
            command=command(expected_generation="generation-2", expected_state_version=2),
            expected_generation="generation-1", expected_state_version=2, recommendation_ref="recommendation-1",
            batch_id="batch-1", symbol="NSI", side="buy", quantity=3,
        )


def test_mutation_metadata_fences_stale_recovery_and_replay() -> None:
    current = command(expected_generation="generation-1", expected_state_version=2)
    stale = command(recovery_id="recovery-0", expected_generation="generation-1", expected_state_version=2)
    request = ResetPortfolioRequest(
        command=current, expected_generation="generation-1", expected_state_version=2,
        starting_cash=StartingCash(amount="100000", currency="XOF"),
    )
    fingerprint = canonical_command_fingerprint("POST", "/v1/paper/reset", request)
    assert current.matches_recovery("recovery-1")
    assert not stale.matches_recovery("recovery-1")
    with pytest.raises(ValidationError):
        command(request_fingerprint=fingerprint)
    with pytest.raises(ValidationError):
        CommandMetadata.model_validate(current.model_dump(exclude={"recovery_id"}))
    receipt = PaperCommandReceipt(
        owner_uid="user-1", idempotency_key=current.idempotency_key,
        request_fingerprint=fingerprint, recovery_id=current.recovery_id, operation="reset",
        outcome_id="generation-1", generation="generation-1", state_version=0, http_status=200,
        accepted_at=NOW, expires_at=NOW + timedelta(days=30),
    )
    assert receipt.matches_replay(current, fingerprint, "recovery-1")
    assert not receipt.matches_replay(stale, fingerprint, "recovery-1")
    assert not receipt.matches_replay(current, fingerprint, "recovery-2")
    assert not receipt.matches_replay(current, "0" * 64, "recovery-1")


def test_fingerprint_uses_parsed_canonical_intent_and_route() -> None:
    first = SetupPortfolioRequest(
        command=command(), starting_cash=StartingCash(amount="1000000", currency="XOF"), fee_rate_pct="0.500",
    )
    equivalent = SetupPortfolioRequest(
        command=command(content_length=200, issued_at=NOW + timedelta(seconds=1)),
        starting_cash=StartingCash(amount="1000000.000000", currency="XOF"), fee_rate_pct="0.5",
    )
    fingerprint = canonical_command_fingerprint("POST", "/v1/paper/portfolio", first)
    assert fingerprint == canonical_command_fingerprint("POST", "/v1/paper/portfolio", equivalent)
    with pytest.raises(ValueError):
        canonical_command_fingerprint("PATCH", "/v1/paper/portfolio", first)
    with pytest.raises(ValueError):
        canonical_command_fingerprint("POST", "/v1/paper/reset", first)
    changed_fee = first.model_copy(update={"fee_rate_pct": "0.6"})
    changed_cash = first.model_copy(update={"starting_cash": StartingCash(amount="2000000", currency="XOF")})
    changed_recovery = first.model_copy(update={"command": command(recovery_id="recovery-2")})
    for changed in (changed_fee, changed_cash, changed_recovery):
        assert fingerprint != canonical_command_fingerprint("POST", "/v1/paper/portfolio", changed)
    receipt = PaperCommandReceipt(
        owner_uid="user-1", idempotency_key=first.command.idempotency_key,
        request_fingerprint=fingerprint, recovery_id=first.command.recovery_id, operation="setup",
        outcome_id="generation-1", generation="generation-1", state_version=0, http_status=201,
        accepted_at=NOW, expires_at=NOW + timedelta(days=30),
    )
    assert receipt.matches_replay(equivalent.command, fingerprint, "recovery-1")
    assert not receipt.matches_replay(
        changed_fee.command,
        canonical_command_fingerprint("POST", "/v1/paper/portfolio", changed_fee),
        "recovery-1",
    )

    preference = PatchPreferencesRequest(command=command(), expected_preference_version=2, objective="growth")
    assert canonical_command_fingerprint("PATCH", "/v1/me/preferences", preference) != canonical_command_fingerprint(
        "PATCH", "/v1/me/preferences", preference.model_copy(update={"expected_preference_version": 3}),
    )

    order = CreatePaperOrderRequest(
        command=command(expected_generation="generation-1", expected_state_version=2),
        expected_generation="generation-1", expected_state_version=2, recommendation_ref="rec-1",
        batch_id="batch-1", symbol="NSI", side="sell", quantity=2,
    )
    order_fingerprint = canonical_command_fingerprint("POST", "/v1/paper/orders", order)
    assert order_fingerprint != canonical_command_fingerprint(
        "POST", "/v1/paper/orders", order.model_copy(update={"acknowledge_keep_override": True}),
    )
    changed_version = order.model_copy(update={
        "expected_state_version": 3,
        "command": command(expected_generation="generation-1", expected_state_version=3),
    })
    assert order_fingerprint != canonical_command_fingerprint("POST", "/v1/paper/orders", changed_version)


def test_preferences_and_receipts_preserve_versions_recovery_and_minimal_evidence() -> None:
    preference = PaperPreferences(objective="growth", fee_rate_pct="0", preference_version=4, updated_at=NOW)
    assert preference.model_dump(mode="json")["updated_at"] == "2026-09-22T12:00:00Z"
    receipt = PaperCommandReceipt(
        owner_uid="user-1", idempotency_key="1758542400000.0123456789abcdef0123456789abcdef",
        request_fingerprint="a" * 64, recovery_id="recovery-1", operation="setup",
        outcome_id="generation-1", generation="generation-1", state_version=0, http_status=201,
        accepted_at=NOW, expires_at=NOW + timedelta(days=30),
    )
    assert receipt.generation == "generation-1"
    with pytest.raises(ValidationError):
        PaperCommandReceipt.model_validate(receipt.model_dump() | {"expires_at": NOW + timedelta(days=29)})
    with pytest.raises(ValidationError):
        PaperCommandReceipt.model_validate(receipt.model_dump() | {"request_fingerprint": "client-value"})


def test_sell_order_retains_derived_advice_and_ledger_evidence() -> None:
    order = PaperOrder(
        order_id="order-1", owner_uid="user-1", generation="generation-1", recommendation_ref="rec-1", batch_id="batch-1",
        symbol="NSI", side="sell", quantity=2, accepted_at=NOW, intended_session=date(2026, 9, 23),
        accepted_calendar_version="calendar-v1", accepted_session_id="session-20260923", accepted_session_index=42,
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


def test_orders_retain_calendar_corrections_and_terminal_invariants() -> None:
    evidence = Provenance(source_id="calendar-source-1", collected_at=NOW, basis="actual")
    common: dict[str, object] = {
        "order_id": "order-1", "owner_uid": "user-1", "generation": "generation-1", "recommendation_ref": "rec-1", "batch_id": "batch-1", "symbol": "NSI", "side": "buy", "quantity": 2,
        "accepted_at": NOW, "intended_session": date(2026, 9, 23), "accepted_calendar_version": "calendar-v1", "accepted_session_id": "session-20260923", "accepted_session_index": 42,
        "grace_deadline_at": NOW + timedelta(days=2), "fee_rate_pct": "0.5", "reserved_cash": money("2000"), "state_version_at_acceptance": 3,
    }
    assert PaperOrder.model_validate(common | {"status": "executed"}).status == "executed"
    for status in ("rejected", "expired"):
        with pytest.raises(ValidationError):
            PaperOrder.model_validate(common | {"status": status})
        assert PaperOrder.model_validate(common | {"status": status, "terminal_reason": "calendar_corrected", "terminal_at": NOW}).status == status
    correction = CalendarCorrectionEvidence(
        original_calendar_version="calendar-v1", original_session_id="session-20260923",
        correcting_calendar_version="calendar-v2", correcting_session_id="session-20260924",
        corrected_at=NOW, source_evidence=(evidence,),
    )
    assert PaperOrder.model_validate(common | {"status": "rejected", "terminal_reason": "calendar_corrected", "terminal_at": NOW, "calendar_correction": correction}).calendar_correction == correction
    with pytest.raises(ValidationError):
        PaperOrder.model_validate(common | {"status": "executed", "calendar_correction": correction})


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
    errors = {(route.path, error.code) for route in PAPER_ROUTES for error in route.error_outcomes}
    assert ("/v1/paper/orders", "cursor_stale") in errors
    assert ("/v1/paper/orders", "snapshot_expired") in errors
    assert ("/v1/paper/reset", "recovery_mismatch") in errors
    assert ("/v1/paper/portfolio", "analysis_not_ready") in errors


def test_route_error_outcomes_match_api_contract() -> None:
    common_read = {
        (401, "unauthenticated"), (403, "admission_denied"), (429, "rate_limited"),
        (503, "service_unavailable"), (503, "admission_unavailable"),
    }
    common_mutation = common_read | {
        (409, "recovery_mismatch"), (409, "idempotency_conflict"),
        (409, "command_window_expired"), (409, "command_clock_ahead"),
        (409, "generation_superseded"), (413, "body_too_large"), (422, "validation_failed"),
    }
    expected = {
        ("GET", "/v1/me"): common_read,
        ("PATCH", "/v1/me/preferences"): common_mutation | {(409, "preference_version_mismatch")},
        ("GET", "/v1/paper/portfolio"): common_read | {(503, "analysis_not_ready")},
        ("POST", "/v1/paper/portfolio"): common_mutation | {(409, "already_initialized")},
        ("POST", "/v1/paper/orders"): common_mutation | {
            (404, "not_found"), (409, "generation_mismatch"), (409, "state_version_mismatch"),
            (409, "recommendation_stale"), (409, "insufficient_cash"), (409, "insufficient_shares"),
            (422, "override_acknowledgment_required"), (503, "calendar_unavailable"),
            (503, "analysis_not_ready"),
        },
        ("POST", "/v1/paper/reset"): common_mutation | {
            (409, "generation_mismatch"), (409, "state_version_mismatch"),
        },
    }
    paginated = common_read | {
        (409, "cursor_stale"), (410, "snapshot_expired"), (422, "validation_failed"),
    }
    for path in ("/v1/paper/orders", "/v1/paper/executions", "/v1/paper/cash-movements"):
        expected[("GET", path)] = paginated
    assert set(expected) == {(route.method, route.path) for route in PAPER_ROUTES}
    for route in PAPER_ROUTES:
        outcomes = {(error.status, error.code) for error in route.error_outcomes}
        assert outcomes == expected[(route.method, route.path)]
        assert len(outcomes) == len(route.error_outcomes)
