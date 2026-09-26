from datetime import datetime, timedelta, timezone

import pytest

from backend.read_api.cursors import CursorClaims, CursorError, decode_cursor, encode_cursor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_cursor_is_signed_and_snapshot_bound() -> None:
    token = encode_cursor(CursorClaims("analysis", None, None, None, "b1", "k1", NOW), b"secret")
    assert decode_cursor(token, b"secret", now=NOW, scope="analysis", batch_id="b1").last_key == "k1"
    with pytest.raises(CursorError):
        decode_cursor(token, b"wrong", now=NOW, scope="analysis", batch_id="b1")


def test_cursor_expiry_and_context_are_rejected() -> None:
    token = encode_cursor(CursorClaims("paper", "u1", "g1", 2, None, "k", NOW), b"secret")
    with pytest.raises(CursorError):
        decode_cursor(token, b"secret", now=NOW + timedelta(hours=24, seconds=1), scope="paper", owner_uid="u1", generation="g1", state_version=2)
    with pytest.raises(CursorError):
        decode_cursor(token, b"secret", now=NOW, scope="paper", owner_uid="u2", generation="g1", state_version=2)
