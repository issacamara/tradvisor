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


def test_release_record_contains_public_evidence_for_all_twelve_factors() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for factor in (
        "1. Codebase",
        "2. Dependencies",
        "3. Config",
        "4. Backing services",
        "5. Build, release, run",
        "6. Processes",
        "7. Port binding",
        "8. Concurrency",
        "9. Disposability",
        "10. Development/production parity",
        "11. Logs",
        "12. Admin processes",
    ):
        assert factor in text
    assert "V1 CI run 38973133406" in text
    assert "0303f5f8a19e566ebdd8d96e3e53307c2058147b" in text


def test_release_record_maps_each_tf_requirement_to_merged_public_artifacts() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for requirement in ("R1 —", "R2 —", "R3 —", "R4 —", "R5 —", "R6 —", "R7 —"):
        assert requirement in text
    for pull_request in ("/pull/233", "/pull/234", "/pull/235", "/pull/236", "/pull/237", "/pull/238", "/pull/239", "/pull/240", "/pull/241", "/pull/243", "/pull/244", "/pull/245", "/pull/246", "/pull/247", "/pull/248"):
        assert pull_request in text
    lower_text = text.lower()
    assert "private infrastructure" in lower_text
    assert "production deployment" in lower_text
