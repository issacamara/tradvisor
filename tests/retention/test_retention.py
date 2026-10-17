from datetime import datetime, timedelta, timezone

from backend.jobs.retention import RetentionItem, plan_cleanup


def test_retention_preserves_active_unknown_and_recent_records() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = plan_cleanup((
        RetentionItem("old", "reset", now - timedelta(days=8)),
        RetentionItem("active", "reset", now - timedelta(days=20), active=True),
        RetentionItem("unknown", "reset", now - timedelta(days=20), cleanup_known=False),
    ), now=now)
    assert decision.deletable == ("old",)
    assert {item for item, _ in decision.protected} == {"active", "unknown"}
