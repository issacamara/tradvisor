"""Signed opaque cursors for bounded API pagination."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
CURSOR_MAX_AGE = timedelta(hours=24)


class CursorError(ValueError):
    """A cursor is malformed, tampered with, expired, or bound elsewhere."""


@dataclass(frozen=True, slots=True)
class CursorClaims:
    scope: str
    owner_uid: str | None
    generation: str | None
    state_version: int | None
    batch_id: str | None
    last_key: str
    issued_at: datetime


def encode_cursor(claims: CursorClaims, secret: bytes) -> str:
    if not secret or not claims.last_key or claims.issued_at.tzinfo is None:
        raise CursorError("cursor claims are incomplete")
    payload = {
        "scope": claims.scope,
        "owner_uid": claims.owner_uid,
        "generation": claims.generation,
        "state_version": claims.state_version,
        "batch_id": claims.batch_id,
        "last_key": claims.last_key,
        "issued_at": claims.issued_at.astimezone(UTC).isoformat(),
    }
    encoded = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(secret, encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_b64(signature)}"


def decode_cursor(
    token: str,
    secret: bytes,
    *,
    now: datetime,
    scope: str,
    owner_uid: str | None = None,
    generation: str | None = None,
    state_version: int | None = None,
    batch_id: str | None = None,
) -> CursorClaims:
    try:
        encoded, supplied = token.split(".", 1)
        expected = hmac.new(secret, encoded.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(supplied)):
            raise CursorError("cursor signature is invalid")
        payload = json.loads(_unb64(encoded))
        claims = CursorClaims(
            scope=payload["scope"], owner_uid=payload.get("owner_uid"),
            generation=payload.get("generation"), state_version=payload.get("state_version"),
            batch_id=payload.get("batch_id"), last_key=payload["last_key"],
            issued_at=datetime.fromisoformat(payload["issued_at"]),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise CursorError("cursor is malformed") from error
    current = now.astimezone(UTC)
    if claims.issued_at.tzinfo is None or current - claims.issued_at.astimezone(UTC) > CURSOR_MAX_AGE:
        raise CursorError("cursor has expired")
    if claims.scope != scope or claims.owner_uid != owner_uid or claims.generation != generation or claims.state_version != state_version or claims.batch_id != batch_id:
        raise CursorError("cursor is bound to another read snapshot")
    return claims


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
