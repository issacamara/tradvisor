from pathlib import Path


DOCUMENT = Path("docs/validation/release.md")


def test_release_record_is_explicitly_no_go_until_missing_gates_are_resolved() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    assert "NO-GO pending owner acceptance" in text
    for phrase in ("Financial rule effectiveness", "Accessibility", "Restore/recovery", "Performance and placement", "Cost"):
        assert phrase in text
    assert "schedule activation" in text
    assert "not authorized" in text


def test_release_record_keeps_activation_requests_separate() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for phrase in ("Deploy the static frontend/API", "Seed or copy data/users/secrets", "Activate ingestion/publication schedules", "Run isolated restore drill"):
        assert phrase in text
    assert "/Users/" not in text
