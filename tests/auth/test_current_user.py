from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from backend.auth.current_user import CurrentUserUnavailable, FirestoreCurrentUserRepository

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


class Snapshot:
    def __init__(self, fields: dict[str, Any] | None) -> None:
        self.exists = fields is not None
        self._fields = fields

    def to_dict(self) -> dict[str, Any] | None:
        return self._fields


class Document:
    def __init__(self, snapshot: Snapshot) -> None:
        self._snapshot = snapshot

    def get(self) -> Snapshot:
        return self._snapshot


class Client:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents
        self.paths: list[str] = []

    def document(self, path: str) -> Document:
        self.paths.append(path)
        return Document(Snapshot(self.documents.get(path)))


def stored(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "_schema_version": 1,
        "_document_state_version": 0,
        **record,
    }


def preferences(version: int = 2) -> dict[str, Any]:
    return stored(
        {
            "objective": "growth",
            "fee_rate_pct": "0.250000",
            "preference_version": version,
            "updated_at": NOW,
        }
    )


def control(version: int = 2) -> dict[str, Any]:
    return stored(
        {
            "owner_uid": "user-1",
            "active_generation": "generation-1",
            "configured_fee_rate_pct": "0.250000",
            "state_version": 4,
            "preference_version": version,
            "recovery_id": "recovery-1",
            "updated_at": NOW,
        }
    )


def test_firestore_current_user_read_is_owner_scoped_and_configured() -> None:
    client = Client(
        {
            "users/user-1": preferences(),
            "paper_portfolios/user-1": control(),
        }
    )
    repository = FirestoreCurrentUserRepository(client)

    state = asyncio.run(repository.get_current_user("user-1"))

    assert state.preferences.preference_version == 2
    assert state.portfolio_setup_state == "configured"
    assert state.recovery_id == "recovery-1"
    assert client.paths == ["users/user-1", "paper_portfolios/user-1"]


def test_firestore_current_user_reports_setup_required_without_control() -> None:
    repository = FirestoreCurrentUserRepository(Client({"users/user-1": preferences()}))

    state = asyncio.run(repository.get_current_user("user-1"))

    assert state.portfolio_setup_state == "setup_required"
    assert state.recovery_id is None


@pytest.mark.parametrize(
    "documents",
    [
        {},
        {"users/user-1": preferences(), "paper_portfolios/user-1": control(version=3)},
        {
            "users/user-1": preferences(),
            "paper_portfolios/user-1": {
                **control(),
                "owner_uid": "other-user",
            },
        },
    ],
)
def test_firestore_current_user_fails_closed_on_missing_or_inconsistent_state(
    documents: dict[str, dict[str, Any]],
) -> None:
    repository = FirestoreCurrentUserRepository(Client(documents))

    with pytest.raises(CurrentUserUnavailable):
        asyncio.run(repository.get_current_user("user-1"))
