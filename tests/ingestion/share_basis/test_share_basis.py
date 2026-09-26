from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "archive" / "legacy-ingestion" / "scripts" / "share_basis.py"
SPEC = importlib.util.spec_from_file_location("share_basis", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
share_basis = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = share_basis
SPEC.loader.exec_module(share_basis)


def observation(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "ABC",
        "session_date": "2024-01-02",
        "open": "100",
        "high": "110",
        "low": "90",
        "close": "105",
        "volume": "1200",
        "known_at": "2024-01-03T08:00:00Z",
    }
    row.update(updates)
    return row


def event(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "ABC",
        "event_type": "split",
        "effective_date": "2024-02-01",
        "known_at": "2024-01-10T12:00:00Z",
        "evidence_ref": "issuer-notice-42",
        "new_shares_per_old_share": "2",
    }
    row.update(updates)
    return row


def normalize(rows: list[dict[str, object]], events: list[dict[str, object]], **kwargs: object):
    return share_basis.normalize_share_basis(
        rows,
        events,
        target_date=kwargs.get("target_date", "2024-03-01"),
        known_at=kwargs.get("known_at", "2024-03-02T00:00:00Z"),
    )


def test_split_adjusts_prices_and_volume_coherently_and_preserves_originals() -> None:
    raw = observation()
    result = normalize([raw], [event()])[0]

    assert result.status == "comparable"
    assert result.advice_eligible is True
    assert result.price_factor == Decimal("0.5")
    assert result.volume_factor == Decimal("2")
    assert (result.open, result.high, result.low, result.close, result.volume) == (
        Decimal("50"), Decimal("55"), Decimal("45"), Decimal("52.5"), Decimal("2400")
    )
    assert result.original.open == Decimal("100")
    assert result.original.volume == Decimal("1200")
    assert raw["open"] == "100" and raw["volume"] == "1200"
    assert result.applied_events[0].evidence_ref == "issuer-notice-42"
    assert result.applied_events[0].known_at == datetime(2024, 1, 10, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("event_type", ["split", "bonus"])
def test_supported_event_types_apply_evidenced_ratio(event_type: str) -> None:
    result = normalize([observation()], [event(event_type=event_type, new_shares_per_old_share="1.5")])[0]

    assert result.price_factor == Decimal(2) / Decimal(3)
    assert result.volume_factor == Decimal("1.5")


def test_rights_or_complex_event_withholds_affected_advice_and_values() -> None:
    result = normalize(
        [observation()],
        [event(event_type="rights_issue", new_shares_per_old_share=None)],
    )[0]

    assert result.status == "unsupported_basis"
    assert result.advice_eligible is False
    assert result.unavailable_reason == "unsupported_corporate_action"
    assert result.close is None and result.volume is None
    assert result.applied_events[0].evidence_ref == "issuer-notice-42"


def test_event_is_applied_only_after_effective_date_and_when_known() -> None:
    row = observation()
    before_effective = normalize([row], [event()], target_date="2024-01-31")[0]
    not_yet_known = normalize(
        [row], [event(known_at="2024-04-01T00:00:00Z")], known_at="2024-03-01T00:00:00Z"
    )[0]

    assert before_effective.close == Decimal("105")
    assert before_effective.applied_events == ()
    assert not_yet_known.close == Decimal("105")
    assert not_yet_known.applied_events == ()


def test_cash_dividend_does_not_change_price_or_volume_basis() -> None:
    result = normalize([observation()], [event(event_type="cash_dividend", new_shares_per_old_share=None)])[0]

    assert result.status == "comparable"
    assert result.advice_eligible is True
    assert result.close == Decimal("105")
    assert result.volume == Decimal("1200")
    assert result.applied_events[0].event_type == "cash_dividend"


def test_reverse_split_and_multiple_events_preserve_evidence_and_compose_factors() -> None:
    result = normalize(
        [observation()],
        [
            event(event_type="split", new_shares_per_old_share="1/2"),
            event(
                event_type="bonus",
                effective_date="2024-02-15",
                new_shares_per_old_share="3/2",
                evidence_ref="issuer-notice-43",
            ),
        ],
    )[0]

    assert result.price_factor == Decimal(4) / Decimal(3)
    assert result.volume_factor == Decimal(3) / Decimal(4)
    assert result.close == Decimal("140")
    assert [item.evidence_ref for item in result.applied_events] == [
        "issuer-notice-42", "issuer-notice-43"
    ]


def test_split_event_does_not_change_observations_on_or_after_effective_date() -> None:
    result = normalize(
        [observation(session_date="2024-02-01")], [event()]
    )[0]

    assert result.close == Decimal("105")
    assert result.volume == Decimal("1200")
    assert result.applied_events == ()


def test_rejects_split_without_verified_factor() -> None:
    with pytest.raises(share_basis.ShareBasisError, match="require an evidenced share ratio"):
        share_basis.normalize_event(event(new_shares_per_old_share=None))


def test_observation_is_unavailable_before_its_known_at_time() -> None:
    result = normalize(
        [observation()], [], known_at="2024-01-02T00:00:00Z"
    )[0]

    assert result.status == "not_yet_known"
    assert result.advice_eligible is False
    assert result.close is None
    assert result.original.close == Decimal("105")
