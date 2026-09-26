"""Owner-scoped current-user reads for the authenticated API boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast
from urllib.parse import quote

from backend.contracts.paper import PaperPreferences, PortfolioControl


class CurrentUserUnavailable(RuntimeError):
    """Current profile state cannot be read or validated safely."""


@dataclass(frozen=True, slots=True)
class CurrentUserState:
    preferences: PaperPreferences
    portfolio_setup_state: Literal["setup_required", "configured"]
    recovery_id: str | None


class CurrentUserRepository(Protocol):
    async def get_current_user(self, owner_uid: str) -> CurrentUserState: ...


class FirestoreCurrentUserRepository:
    """Read the authenticated owner's preferences and portfolio control."""

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from google.cloud import firestore

            client = firestore.Client()
        self._client = client

    async def get_current_user(self, owner_uid: str) -> CurrentUserState:
        return await asyncio.to_thread(self._read_current_user, owner_uid)

    def _read_current_user(self, owner_uid: str) -> CurrentUserState:
        owner_segment = quote(owner_uid, safe="")
        preferences_record = self._read_record(f"users/{owner_segment}")
        if preferences_record is None:
            raise CurrentUserUnavailable("current preferences are unavailable")

        try:
            preferences = PaperPreferences.model_validate(preferences_record)
            control_record = self._read_record(f"paper_portfolios/{owner_segment}")
            if control_record is None:
                return CurrentUserState(
                    preferences=preferences,
                    portfolio_setup_state="setup_required",
                    recovery_id=None,
                )

            control = PortfolioControl.model_validate(control_record)
            if str(control.owner_uid) != owner_uid:
                raise CurrentUserUnavailable("portfolio owner does not match authentication")
            if control.preference_version != preferences.preference_version:
                raise CurrentUserUnavailable("current preference state is inconsistent")
            return CurrentUserState(
                preferences=preferences,
                portfolio_setup_state=(
                    "configured" if control.active_generation is not None else "setup_required"
                ),
                recovery_id=str(control.recovery_id),
            )
        except CurrentUserUnavailable:
            raise
        except Exception as error:
            raise CurrentUserUnavailable("current profile state is invalid") from error

    def _read_record(self, path: str) -> dict[str, Any] | None:
        try:
            snapshot = self._client.document(path).get()
            if not snapshot.exists:
                return None
            fields = snapshot.to_dict()
            if not isinstance(fields, dict):
                raise CurrentUserUnavailable("current profile record is invalid")
            schema_version = fields.get("_schema_version")
            state_version = fields.get("_document_state_version")
            if (
                not isinstance(schema_version, int)
                or isinstance(schema_version, bool)
                or schema_version < 1
                or not isinstance(state_version, int)
                or isinstance(state_version, bool)
                or state_version < 0
            ):
                raise CurrentUserUnavailable("current profile record version is invalid")
            return cast(
                dict[str, Any],
                {
                    key: value
                    for key, value in fields.items()
                    if key not in {"_schema_version", "_document_state_version"}
                },
            )
        except CurrentUserUnavailable:
            raise
        except Exception as error:
            raise CurrentUserUnavailable("current profile read failed") from error
