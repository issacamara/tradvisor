from pathlib import Path


DOCUMENT = Path("docs/validation/cost.md")


def test_cost_review_separates_idle_and_scheduled_drivers() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for phrase in ("Idle behavior", "Scheduled/active driver", "BigQuery", "Firestore", "Cloud Storage", "Logging/monitoring"):
        assert phrase in text


def test_cost_review_does_not_make_unverified_cost_promises() -> None:
    text = DOCUMENT.read_text(encoding="utf-8").lower()
    assert "not a promise" in text
    assert "free-tier eligibility" in text
    assert "pending owner acceptance" in text
    assert "five-euro target passed" in text
    assert "paid query executed" in text
    assert "/users/" not in text
