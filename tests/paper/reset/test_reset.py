from datetime import datetime, timezone

from backend.contracts.routes import ResetPortfolioRequest
from backend.contracts.scalars import StartingCash
from backend.paper.reset import reset_portfolio
from backend.paper.setup import setup_portfolio
from backend.store.repositories import OwnerContext, PaperRepositories
from tests.store.test_repositories import FakeStore


NOW = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)


def _request(generation: str, recovery_id: str, state_version: int) -> ResetPortfolioRequest:
    return ResetPortfolioRequest.model_validate({
        "command": {
            "idempotency_key": f"1767607200000.{'a' * 32}",
            "recovery_id": recovery_id,
            "content_length": 100,
            "issued_at": NOW,
            "expected_generation": generation,
            "expected_state_version": state_version,
        },
        "expected_generation": generation,
        "expected_state_version": state_version,
        "starting_cash": {"amount": "200000", "currency": "XOF"},
    })


def test_reset_switches_generation_and_replays_same_receipt() -> None:
    store = FakeStore()
    repositories = PaperRepositories(store, OwnerContext(uid="owner-1"))
    setup_portfolio(
        repositories,
        starting_cash=StartingCash(amount="100000", currency="XOF"),
        objective="growth",
        fee_rate_pct="0.5",
        fee_zero_confirmed=False,
        now=NOW,
    )
    control = repositories.get_control()
    assert control is not None and control.record.active_generation is not None
    request = _request(str(control.record.active_generation), str(control.record.recovery_id), control.record.state_version)
    first = reset_portfolio(repositories, request, now=NOW, generation="generation-new")
    second = reset_portfolio(
        repositories, request, now=NOW, generation="generation-other", recovery_id="recovery-other"
    )
    assert first.generation == "generation-new"
    assert second.receipt.replayed
    current = repositories.get_control()
    assert current is not None
    assert current.record.active_generation == "generation-new"
